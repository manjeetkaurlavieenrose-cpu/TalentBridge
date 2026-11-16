import os, time
from .support import *

# shared CI machines (and Windows file I/O) are slower than a laptop; TB_PERF_MS overrides the limit
LIMIT_MS = float(os.getenv("TB_PERF_MS", 1000 if os.name == "nt" or os.getenv("CI") else 400))
from app.db import jd, now


class PerformanceTests(Base):
    """Seeds directly in SQL, then checks the HTTP API stays paginated and fast. Thresholds are deliberately generous."""
    N = 10_000

    def timed(self, rec, url):
        t0 = time.perf_counter(); r = rec.get(url); dt = (time.perf_counter() - t0) * 1000
        self.assertEqual(r.status_code, 200, url); return r.json, dt

    def test_scaling(self):
        rec = self.recruiter(); jid = self.job(rec)
        rows, done = [], 0
        for n in (10, 100, 1000, self.N):
            self.seed_range(rec, jid, done, n); done = n
            j, ms1 = self.timed(rec, "/candidates?limit=25")
            self.assertEqual((len(j["data"]), j["total"]), (min(25, n), n))
            _, ms2 = self.timed(rec, "/candidates?q=candidate 0042&limit=25")
            _, ms3 = self.timed(rec, f"/candidates?sort=name&page={max(1, n // 25 // 2)}&limit=25")
            j4, ms4 = self.timed(rec, f"/jobs/{jid}/applications?sort=match&limit=25")
            self.assertLessEqual(len(j4["data"]), 25)
            scores = [r["match_score"] for r in j4["data"]]; self.assertEqual(scores, sorted(scores, reverse=True))
            rows.append((n, ms1, ms2, ms3, ms4))
            for ms in (ms1, ms2, ms3, ms4): self.assertLess(ms, LIMIT_MS, f"{n} rows: {ms:.0f} ms")
        print("\n  candidates  list   search  deep-page  ranked-applications   (ms)")
        for n, a, b, c, d in rows: print(f"  {n:>10}  {a:5.0f}  {b:6.0f}  {c:9.0f}  {d:19.0f}")
        # payload stays small no matter how big the table is
        r = rec.get("/candidates?limit=25"); self.assertLess(len(r.data), 25_000)

    def seed_range(self, rec, jid, lo, hi):
        db = self.ctx.db; t = now()
        org = db.scalar("SELECT organization_id FROM recruiters")
        skills = ["sql", "excel", "python", "power bi", "research", "tableau"]
        with db.tx():
          for i in range(lo, hi):
            db.execute("INSERT INTO candidates (id,managed_by_org_id,email,full_name,total_years,top_skills,profile_status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                         (f"c{i:06d}", org, f"user{i}@example.com", f"Candidate {i:05d}", i % 15, jd([skills[i % 6], skills[(i + 1) % 6]]), "confirmed", f"2026-01-01T00:00:00.{i:06d}+00:00", t))
            if i % 3 == 0:
                db.execute("INSERT INTO applications (id,job_id,candidate_id,status,match_score,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                             (f"a{i:06d}", jid, f"c{i:06d}", "cv_reviewed", (i * 7) % 100, t, t))
