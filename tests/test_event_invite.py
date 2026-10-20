"""Regression tests for the isolated invitation flow (no real customer data)."""
import importlib
from contextlib import closing
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class InviteFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            "EVENT_INVITE_DB": str(Path(self.tmp.name) / "test.sqlite3"),
            "EVENT_INVITE_COLLECTION_ENABLED": "false",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        import event_invite.app as app_module
        self.mod = importlib.reload(app_module)
        self.client = TestClient(self.mod.app)
        self.addCleanup(self.client.close)

    def test_admin_contacts_fail_closed_and_require_token(self):
        url = "/invite/admin/contacts"
        disabled = self.client.get(url)
        self.assertEqual(disabled.status_code, 503)
        self.assertEqual(disabled.headers.get("cache-control"), "no-store")
        token = "a" * 40
        with patch.dict(os.environ, {"EVENT_INVITE_ADMIN_TOKEN": token}):
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.get(url, headers={
                "X-Invite-Admin-Token": "wrong"}).status_code, 403)
            good = self.client.get(url, headers={"X-Invite-Admin-Token": token})
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.json(), {"count": 0, "contacts": []})
        self.assertEqual(good.headers.get("cache-control"), "no-store")

    def test_admin_contacts_do_not_leak_without_valid_token(self):
        from datetime import datetime, timezone
        token = "b" * 40
        phone = "+79990000000"
        with closing(self.mod.connect()) as db:
            db.execute(
                "INSERT INTO invitations (phone, created_at, consent_version, retention_until) "
                "VALUES (?, ?, ?, ?)",
                (phone, datetime.now(timezone.utc).isoformat(), "test", "2026-12-07"),
            )
            db.commit()
        url = "/invite/admin/contacts"
        with patch.dict(os.environ, {"EVENT_INVITE_ADMIN_TOKEN": token}):
            unauthorized = self.client.get(url)
            invalid = self.client.get(url, headers={"X-Invite-Admin-Token": "wrong"})
            authorized = self.client.get(
                url, headers={"X-Invite-Admin-Token": token}
            )
        for response in (unauthorized, invalid):
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(phone, response.text)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.json()["count"], 1)
        self.assertEqual(authorized.json()["contacts"][0]["phone"], phone)

    def test_disabled_collection_fails_closed(self):
        response = self.client.get("/invite/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("сбор телефонов выключен", response.text)
        self.assertNotIn('name="phone"', response.text)
        response = self.client.post("/invite/register", data={
            "phone": "+79990000000", "consent": "yes",
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Path(self.tmp.name, "test.sqlite3").exists())

    def test_consent_and_phone_required(self):
        with patch.object(self.mod, "COLLECTION_ENABLED", True):
            for payload in [
                {"phone": "+79990000000"},
                {"phone": "not a phone", "consent": "yes"},
            ]:
                with self.subTest(payload=payload):
                    response = self.client.post("/invite/register", data=payload,
                                                follow_redirects=False)
                    self.assertEqual(response.status_code, 422)
            self.assertFalse(Path(self.tmp.name, "test.sqlite3").exists())

    def test_repeat_submission_does_not_duplicate_contact(self):
        payload = {"phone": "+7 999 000 00 00", "consent": "yes"}
        with patch.object(self.mod, "COLLECTION_ENABLED", True):
            responses = [
                self.client.post("/invite/register", data=payload, follow_redirects=False)
                for _ in range(2)
            ]
        self.assertTrue(all(r.status_code == 303 for r in responses))
        import sqlite3
        with closing(sqlite3.connect(str(Path(self.tmp.name) / "test.sqlite3"))) as db:
            count = db.execute("SELECT COUNT(*) FROM invitations").fetchone()[0]
        self.assertEqual(count, 1)

    def test_expired_records_are_removed_on_request(self):
        import sqlite3
        db_path = str(Path(self.tmp.name) / "test.sqlite3")
        with closing(self.mod.connect()) as db:
            db.execute(
                "INSERT INTO invitations (phone, created_at, consent_version, retention_until) "
                "VALUES (?, ?, ?, ?)",
                ("+79990000000", "2026-10-01T00:00:00+00:00", "test", "2026-10-01"),
            )
            db.commit()
        response = self.client.get("/invite/")
        self.assertEqual(response.status_code, 200)
        with closing(sqlite3.connect(db_path)) as db:
            count = db.execute("SELECT COUNT(*) FROM invitations").fetchone()[0]
        self.assertEqual(count, 0)

    def test_success_saves_before_redirect(self):
        with patch.object(self.mod, "COLLECTION_ENABLED", True):
            response = self.client.post("/invite/register", data={
                "phone": "+7 999 000 00 00", "consent": "yes"
            }, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], self.mod.NETHOUSE_URL)
        import sqlite3
        with closing(sqlite3.connect(str(Path(self.tmp.name) / "test.sqlite3"))) as db:
            record = db.execute(
                "SELECT phone, retention_until FROM invitations"
            ).fetchone()
        self.assertEqual(record, ("+79990000000", "2026-12-07"))

    def test_consent_fingerprint_matches_displayed_document(self):
        import hashlib
        import sqlite3
        with patch.object(self.mod, "COLLECTION_ENABLED", True):
            response = self.client.post("/invite/register", data={
                "phone": "+79990000000", "consent": "yes"
            }, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with closing(sqlite3.connect(str(Path(self.tmp.name) / "test.sqlite3"))) as db:
            version, digest = db.execute(
                "SELECT consent_version, consent_sha256 FROM invitations"
            ).fetchone()
        self.assertEqual(version, self.mod.CONSENT_VERSION)
        self.assertEqual(digest, hashlib.sha256(
            self.client.get("/invite/consent").content
        ).hexdigest())

    def test_personal_agent_link_is_saved_and_reported(self):
        import sqlite3
        token = "c" * 40
        with patch.object(self.mod, "COLLECTION_ENABLED", True):
            page = self.client.get("/invite/?agent_id=603")
            self.assertEqual(page.status_code, 200)
            self.assertIn('name="agent_id" value="603"', page.text)
            response = self.client.post("/invite/register", data={
                "phone": "+79990000000",
                "consent": "yes",
                "agent_id": "603",
            }, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with closing(sqlite3.connect(str(Path(self.tmp.name) / "test.sqlite3"))) as db:
            row = db.execute(
                "SELECT agent_id, agent_name FROM invitations"
            ).fetchone()
        self.assertEqual(row, ("603", "Гехт Евгений"))
        with patch.dict(os.environ, {"EVENT_INVITE_ADMIN_TOKEN": token}):
            report = self.client.get(
                "/invite/admin/contacts",
                headers={"X-Invite-Admin-Token": token},
            )
        self.assertEqual(report.status_code, 200)
        contact = report.json()["contacts"][0]
        self.assertEqual(contact["agent_id"], "603")
        self.assertEqual(contact["agent_name"], "Гехт Евгений")

    def test_unknown_agent_id_is_ignored(self):
        import sqlite3
        with patch.object(self.mod, "COLLECTION_ENABLED", True):
            page = self.client.get("/invite/?agent_id=999999")
            self.assertNotIn('name="agent_id"', page.text)
            response = self.client.post("/invite/register", data={
                "phone": "+79990000000",
                "consent": "yes",
                "agent_id": "999999",
            }, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with closing(sqlite3.connect(str(Path(self.tmp.name) / "test.sqlite3"))) as db:
            row = db.execute(
                "SELECT agent_id, agent_name FROM invitations"
            ).fetchone()
        self.assertEqual(row, ("", ""))

    def test_existing_sqlite_schema_migrates_without_losing_rows(self):
        import sqlite3
        db_path = str(Path(self.tmp.name) / "test.sqlite3")
        with sqlite3.connect(db_path) as db:
            db.execute("""CREATE TABLE invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL, created_at TEXT NOT NULL,
                consent_version TEXT NOT NULL, retention_until TEXT NOT NULL
            )""")
            db.execute(
                "INSERT INTO invitations (phone,created_at,consent_version,retention_until) "
                "VALUES (?,?,?,?)",
                ("+79990000000", "2026-10-01T00:00:00+00:00", "old", "2026-12-07")
            )
        with closing(self.mod.connect()) as db:
            row = db.execute(
                "SELECT phone,consent_sha256,agent_id,agent_name FROM invitations"
            ).fetchone()
        self.assertEqual(row, ("+79990000000", "", "", ""))



if __name__ == "__main__":
    unittest.main()
