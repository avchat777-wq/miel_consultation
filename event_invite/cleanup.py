"""CLI cleanup for expired invitation records. Default is read-only dry-run."""
import argparse
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

def main():
    p = argparse.ArgumentParser(description="Remove expired event invitation records")
    p.add_argument("--db", type=Path, default=Path("event_invite/invites.sqlite3"))
    p.add_argument("--apply", action="store_true", help="Actually delete expired records")
    args = p.parse_args()
    if not args.db.is_file():
        print("Database not found; nothing to delete")
        return
    today = datetime.now(ZoneInfo("Asia/Barnaul")).date().isoformat()
    with closing(sqlite3.connect(str(args.db), timeout=5)) as db:
        count = db.execute(
            "SELECT COUNT(*) FROM invitations WHERE retention_until < ?", (today,)
        ).fetchone()[0]
        if args.apply:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM invitations WHERE retention_until < ?", (today,))
            db.commit()
    print(f"mode={'apply' if args.apply else 'dry-run'} expired_records={count} cutoff={today}")

if __name__ == "__main__":
    main()
