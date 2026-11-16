#!/usr/bin/env python3
"""Copy all TalentBridge data from the SQLite file to an EMPTY PostgreSQL database. The SQLite file is only read.

    python3 scripts/sqlite_to_postgres.py --to postgresql://user@localhost:5432/talentbridge [--from data/talentbridge.db]

Creates the schema in PostgreSQL (same migrations the app uses), copies every table in dependency order, then checks
that every row count matches. Refuses to write into a database that already has candidates or users.
CV files stay where they are (data/uploads); keep UPLOAD_DIR pointing at the same folder.
Stop the app before running so nothing changes during the copy.
"""
import argparse, os, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
ORDER = ["organizations", "users", "recruiters", "candidates", "cvs", "jobs", "applications", "assessments", "assessment_responses",
         "evaluations", "matches", "match_history", "reviews", "activity_logs", "task_queue", "email_outbox", "rate_hits"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", default=os.path.join(ROOT, "data", "talentbridge.db"))
    ap.add_argument("--to", required=True)
    a = ap.parse_args()
    if not os.path.exists(a.src):
        sys.exit(f"No SQLite database at {a.src}")
    from app.db import DB
    pg = DB(a.to)
    pg.init_schema()
    if pg.scalar("SELECT COUNT(*) FROM users") or pg.scalar("SELECT COUNT(*) FROM candidates"):
        sys.exit("The PostgreSQL database already contains data. Use an empty database.")
    src = sqlite3.connect(f"file:{a.src}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    have = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    counts = {}
    with pg.tx():
        for t in ORDER:
            if t not in have:
                continue
            pg_cols = {r["column_name"] for r in pg.all("SELECT column_name FROM information_schema.columns WHERE table_name=?", (t,))}
            rows = src.execute(f"SELECT * FROM {t}").fetchall()
            cols = [c for c in (rows[0].keys() if rows else []) if c in pg_cols]
            for r in rows:
                pg.execute(f"INSERT INTO {t} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [r[c] for c in cols])
            counts[t] = len(rows)
    bad = [t for t, n in counts.items() if pg.scalar(f"SELECT COUNT(*) FROM {t}") != n]
    for t, n in counts.items():
        print(f"  {t:22s} {n}")
    if bad:
        sys.exit("Row counts differ for: " + ", ".join(bad))
    print("Copied and verified. Start the app with DATABASE_URL set to the PostgreSQL address (see README).")


if __name__ == "__main__":
    main()
