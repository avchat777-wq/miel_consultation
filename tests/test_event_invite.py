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


if __name__ == "__main__":
    unittest.main()
