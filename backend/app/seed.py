"""Demo seeding for a laptop demo. NEVER run this against a real deployment: the passwords below are public.

seed_accounts(ctx)           demo admin + approved demo recruiter + three open positions (idempotent)
seed_candidates(app, dir)    six fictional candidates who register, upload a sample CV, apply and (mostly) complete their
                             assessments through the real API, so the recruiter dashboard has realistic, computed content
"""
import os
from .db import now, uid, jd
from .security import hash_password
from . import demo_data as D
from . import pipeline as pl


def seed_accounts(c):
    made = []
    a_email, a_pw = D.ACCOUNTS["admin"]
    r_email, r_pw, r_name, org_name = D.ACCOUNTS["recruiter"]
    t = now()
    admin = c.db.one("SELECT id FROM users WHERE email=?", (a_email,))
    if not admin:
        aid = uid()
        c.db.execute("INSERT INTO users (id,email,password_hash,role,status,created_at) VALUES (?,?,?,?,?,?)", (aid, a_email, hash_password(a_pw), "admin", "active", t))
        made.append("admin")
    else:
        aid = admin["id"]
    rec = c.db.one("SELECT id FROM users WHERE email=?", (r_email,))
    if not rec:
        org = c.db.one("SELECT id FROM organizations WHERE LOWER(name)=LOWER(?)", (org_name,))
        oid = org["id"] if org else uid()
        if not org:
            c.db.execute("INSERT INTO organizations (id,name,created_at) VALUES (?,?,?)", (oid, org_name, t))
        rid = uid()
        c.db.execute("INSERT INTO users (id,email,password_hash,role,status,created_at) VALUES (?,?,?,?,?,?)", (rid, r_email, hash_password(r_pw), "recruiter", "active", t))
        c.db.execute("INSERT INTO recruiters (id,user_id,organization_id,full_name,approved_by,approved_at) VALUES (?,?,?,?,?,?)", (uid(), rid, oid, r_name, aid, t))
        made.append("recruiter")
    else:
        rid = rec["id"]
    r = c.db.one("SELECT organization_id FROM recruiters WHERE user_id=?", (rid,))
    existing = {x["title"] for x in c.db.all("SELECT title FROM jobs WHERE organization_id=?", (r["organization_id"],))}
    if not existing or any(j["title"] not in existing for j in D.JOBS.values()):
        for j in (j for j in D.JOBS.values() if j["title"] not in existing):     # adds openings introduced in later versions
            c.db.execute("""INSERT INTO jobs (id,organization_id,created_by,title,kind,description,required_skills,preferred_skills,custom_requirements,
                min_years,education_level,task_brief,status,deadline,auto_assessment,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (uid(), r["organization_id"], rid, j["title"], j["kind"], j["description"], jd(j["required_skills"]), jd(j["preferred_skills"]),
                          jd(j["custom_requirements"]), j["min_years"], j["education_level"], j["task_brief"], "open", None, 1, t, t))
        made.append("jobs")
    return made


class _Api:
    def __init__(self, app):
        self.c, self.csrf = app.test_client(), None

    def _h(self):
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def get(self, u): return self.c.get("/api/v1" + u, headers=self._h())
    def post(self, u, json=None, **kw): return self.c.post("/api/v1" + u, json=json, headers=self._h(), **kw)
    def put(self, u, json=None): return self.c.put("/api/v1" + u, json=json, headers=self._h())
    def patch(self, u, json=None): return self.c.patch("/api/v1" + u, json=json, headers=self._h())

    def login(self, email, pw):
        r = self.post("/auth/login", {"email": email, "password": pw})
        if r.status_code != 200:
            raise RuntimeError(f"demo login failed for {email}: {r.status_code}")
        self.csrf = r.json["csrf_token"]


def seed_candidates(app, sample_dir):
    """Returns a list of human-readable lines describing what was created. Safe to call twice (skips existing emails)."""
    import io
    c = app.ctx
    out = []
    rec_email, rec_pw = D.ACCOUNTS["recruiter"][:2]
    rec = _Api(app)
    rec.login(rec_email, rec_pw)
    jobs = {j["title"]: j["id"] for j in rec.get("/jobs?limit=100").json["data"]}
    title_of = {k: v["title"] for k, v in D.JOBS.items()}
    for key, name, email, fname, applications in D.CANDIDATES:
        if c.db.one("SELECT 1 AS x FROM users WHERE email=?", (email,)):
            out.append(f"{name}: already present, skipped")
            continue
        path = os.path.join(sample_dir, fname)
        if not os.path.exists(path):
            out.append(f"{name}: sample file {fname} missing, skipped")
            continue
        cand = _Api(app)
        assert cand.post("/auth/register/candidate", {"email": email, "password": D.CANDIDATE_PASSWORD, "full_name": name}).status_code == 201
        cand.login(email, D.CANDIDATE_PASSWORD)
        with open(path, "rb") as f:
            r = cand.post("/me/cvs", data={"file": (io.BytesIO(f.read()), fname)}, content_type="multipart/form-data")
        assert r.status_code == 201, r.json
        pl.run_pending(c)
        prof = cand.get("/me/profile").json
        if prof["cvs"][0]["stage"] != "ready":
            out.append(f"{name}: CV did not process ({prof['cvs'][0]['error_message']})")
            continue
        cand.patch("/me/profile", {"confirm": True})
        for jkey, takes_test in applications:
            r = cand.post(f"/jobs/{jobs[title_of[jkey]]}/apply")
            assert r.status_code == 201, r.json
            pl.run_pending(c)
            aid = r.json["id"]
            if not takes_test:
                out.append(f"{name} -> {title_of[jkey]}: applied, assessment waiting")
                continue
            sid = next(a["open_assessment_id"] for a in cand.get("/me/applications").json["data"] if a["id"] == aid)
            cand.post(f"/assessments/{sid}/start")
            task = cand.get(f"/assessments/{sid}").json["task"]
            texts = D.ANSWERS[(key, jkey)]
            answers = {q["id"]: texts[i] for i, q in enumerate(task["questions"]) if i < len(texts)}
            # seeded attempts are given a realistic duration (otherwise every one would look pasted in seconds)
            from datetime import datetime, timezone, timedelta
            took = D.MINUTES_TAKEN.get((key, jkey), 26)
            c.db.execute("UPDATE assessments SET started_at=? WHERE id=?",
                         ((datetime.now(timezone.utc) - timedelta(minutes=took)).isoformat(timespec="microseconds"), sid))
            r = cand.post(f"/assessments/{sid}/submit", {"answers": answers})
            assert r.status_code == 200, r.json
            pl.run_pending(c)
            score = c.db.scalar("SELECT ev.overall FROM evaluations ev WHERE ev.assessment_id=?", (sid,))
            out.append(f"{name} -> {title_of[jkey]}: assessment scored {score}")
    return out
