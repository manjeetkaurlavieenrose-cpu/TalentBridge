import io, os, re, shutil, tempfile, unittest
from app import create_app
from app.config import Config
from app import pipeline as pl

SKILLS = ["sql", "excel", "power bi", "python", "tableau", "research", "statistics", "data analysis", "react"]


class FakeAI:
    """Test double with the same interface as the real provider. Deterministic; records calls."""
    def __init__(self):
        self.calls, self.fail_with, self.hallucinate = [], None, False

    def call(self, tool, description, schema, system, user):
        self.calls.append(tool)
        if self.fail_with:
            raise self.fail_with
        return getattr(self, "_" + tool)(user)

    def _record_candidate_profile(self, user):
        text = user.split("<candidate_document>")[1].split("</candidate_document>")[0]
        low = text.lower()
        name = text.strip().splitlines()[0].strip()
        em = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
        sk = [{"name": s.title() if len(s) > 3 else s.upper(), "level": "demonstrated" if f"used {s}" in low else "listed",
               "proficiency": "unknown", "context": f"used {s} at work" if f"used {s}" in low else ""} for s in SKILLS if s in low]
        return {"full_name": name, "email": em.group(0) if em else None, "phone": "+91 98765 43210",
                "education": [{"degree": "BA History", "institution": "Delhi University", "graduation_year": 2023}],
                "work_history": [{"title": "Analyst", "company": "Acme", "start": "2021-01", "end": "2023-01", "description": "Built dashboards", "achievements": []},
                                 {"title": "Intern", "company": "Beta", "start": "2022-06", "end": "2022-12", "description": "Overlaps", "achievements": []}],
                "skills": sk, "projects": [], "certifications": [], "achievements": [], "portfolio_links": [], "languages": [],
                "strengths": ["analytical"], "gaps": [], "confidence": 0.9}

    def _record_application_analysis(self, user):
        return {"summary": "Reasonable fit.", "strengths": ["SQL"], "gaps": ["Power BI depth"], "risks": [],
                "requirements_check": [{"requirement": "Dashboard experience", "status": "partial", "evidence": "Built dashboards"}],
                "interview_questions": ["Tell us about a dashboard you built."], "confidence": 0.8}

    def _record_assessment(self, user):
        return {"title": "Retail sales analysis", "scenario": "A retailer wants to understand falling weekend sales across regions.", "minutes": 30,
                "questions": [{"id": "x", "prompt": "Which metrics would you check first and why?", "max_points": 50, "rubric": "Names metrics, justifies"},
                              {"id": "y", "prompt": "Describe how you would present findings.", "max_points": 50, "rubric": "Audience-aware"}]}

    def _record_evaluation(self, user):
        answers = re.findall(r"<candidate_answer>\n\[(q\d+)\]\n(.*?)\n</candidate_answer>", user, re.S)
        per = []
        for qid, txt in answers:
            words = txt.split()
            ev = ["a sentence the candidate never wrote"] if self.hallucinate else [" ".join(words[:5])]
            per.append({"question_id": qid, "score": 50.0 * min(len(words) / 40, 1), "rationale": "Based on length.", "evidence": ev})
        return {"per_question": per, "criteria": {k: 70 for k in ("relevance", "depth", "accuracy", "communication", "structure")},
                "strengths": ["clear"], "gaps": ["shallow"], "language_notes": [], "summary": "ok", "confidence": 0.85}


class Mailer:
    def __init__(self): self.sent = []
    def send(self, to, subject, body): self.sent.append((to, subject, body))


class Client:
    def __init__(self, app):
        self.c = app.test_client()
        self.csrf = None

    def _h(self, kw):
        h = kw.pop("headers", {})
        if self.csrf: h["X-CSRF-Token"] = self.csrf
        return h

    def get(self, url, **kw): return self.c.get("/api/v1" + url, headers=self._h(kw), **kw)
    def post(self, url, json=None, **kw): return self.c.post("/api/v1" + url, json=json, headers=self._h(kw), **kw)
    def put(self, url, json=None, **kw): return self.c.put("/api/v1" + url, json=json, headers=self._h(kw), **kw)
    def patch(self, url, json=None, **kw): return self.c.patch("/api/v1" + url, json=json, headers=self._h(kw), **kw)
    def delete(self, url, json=None, **kw): return self.c.delete("/api/v1" + url, json=json, headers=self._h(kw), **kw)

    def login(self, email, password="correct-horse-9"):
        r = self.post("/auth/login", {"email": email, "password": password})
        if r.status_code == 200: self.csrf = r.json["csrf_token"]
        return r


def make_pdf(text, pages=1):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for p in range(pages):
        y = 800
        for line in text.splitlines():
            c.drawString(50, y, line); y -= 14
        c.showPage()
    c.save()
    return buf.getvalue()


def blank_pdf():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); c = canvas.Canvas(buf); c.rect(50, 50, 300, 300, fill=1); c.showPage(); c.save()
    return buf.getvalue()


def make_docx(text):
    import docx
    d = docx.Document()
    for line in text.splitlines(): d.add_paragraph(line)
    b = io.BytesIO(); d.save(b); return b.getvalue()


def cv_text(name="Asha Verma", email="asha@example.com", extra="Used SQL and used Excel daily. Built dashboards in Power BI. Python and statistics."):
    return (f"{name}\n{email}\nExperience\nData Analyst at Acme 2021-2023. {extra}\n"
            "Education: BA History, Delhi University 2023.\nSkills: SQL, Excel, Power BI, Python, statistics, data analysis. "
            "Projects: sales dashboards and customer analysis for a retail client in Delhi, India.")


def test_db_url(tmp):
    """SQLite file per test by default. Set TB_TEST_DATABASE_URL=postgresql://... to run the same tests on PostgreSQL
    (the schema is wiped before each test, so point it at a database used only for tests)."""
    url = os.getenv("TB_TEST_DATABASE_URL")
    if not url:
        return f"sqlite:///{tmp}/t.db"
    import psycopg
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE"); c.execute("CREATE SCHEMA public")
    return url


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ai, self.mailer = FakeAI(), Mailer()
        cfg = Config(database_url=test_db_url(self.tmp), upload_dir=f"{self.tmp}/up", cookie_secure=False,
                     admin_email="admin@tb.test", admin_password="correct-horse-9", rl_global=(100000, 60), rl_login=(1000, 60),
                     rl_register=(1000, 60), rl_upload=(1000, 60), allowed_origins=["http://localhost:5000"])
        self.cfg = cfg
        self.app = create_app(cfg, ai=self.ai, mailer=self.mailer)
        self.ctx = self.app.ctx

    def tearDown(self):
        self.ctx.db.close(); shutil.rmtree(self.tmp, ignore_errors=True)

    def client(self): return Client(self.app)
    def work(self): return pl.run_pending(self.ctx)

    def admin(self):
        c = self.client(); assert c.login("admin@tb.test").status_code == 200; return c

    def candidate(self, email="asha@example.com", name="Asha Verma"):
        c = self.client()
        r = c.post("/auth/register/candidate", {"email": email, "password": "correct-horse-9", "full_name": name})
        assert r.status_code == 201, r.json
        assert c.login(email).status_code == 200
        return c

    def recruiter(self, email="rec@acme.test", org="Acme Hiring", approve=True, name="Rita Rao"):
        c = self.client()
        r = c.post("/auth/register/recruiter", {"email": email, "password": "correct-horse-9", "full_name": name, "organization": org})
        assert r.status_code == 201, r.json
        if approve:
            a = self.admin()
            uid = self.ctx.db.scalar("SELECT id FROM users WHERE email=?", (email,))
            assert a.post(f"/admin/users/{uid}/status", {"status": "active"}).status_code == 200
        assert c.login(email).status_code == 200 or not approve
        return c

    def upload(self, c, data, name="cv.pdf", path="/me/cvs"):
        return c.post(path, data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")

    def ready_candidate(self, email="asha@example.com", name="Asha Verma", **cvkw):
        c = self.candidate(email, name)
        r = self.upload(c, make_pdf(cv_text(name, email, **cvkw)))
        assert r.status_code == 201, r.json
        self.work()
        p = c.get("/me/profile").json
        assert p["cvs"][0]["stage"] == "ready", p
        assert c.patch("/me/profile", {"confirm": True}).status_code == 200
        return c

    def job(self, rec, **over):
        d = {"title": "Data Analyst", "required_skills": ["SQL", "Excel", "Data analysis"], "preferred_skills": ["Power BI"],
             "min_years": 2, "education_level": "bachelor", "custom_requirements": ["Dashboard experience"]}
        d.update(over)
        r = rec.post("/jobs", d); assert r.status_code == 201, r.json
        return r.json["id"]
