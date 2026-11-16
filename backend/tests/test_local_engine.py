"""Tests for the local-first engine: real PDF/DOCX extraction, rule-based parsing, matching, question generation, scoring,
persistence, permissions and the optional Ollama / semantic paths. No network, no paid API. All people are fictional."""
import io, json, shutil, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from .support import Base, Client, test_db_url
from . import fixtures as F
from app import create_app, pipeline as pl, ai as ai_mod
from app.config import Config
from app import answer_scorer, cv_parser, similarity, question_bank
from app.local_ai import LocalAI


class LocalBase(Base):
    """Same harness as Base but with the real local engine instead of the FakeAI test double."""
    def setUp(self):
        super().setUp()
        self.ctx.db.close(); shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp = tempfile.mkdtemp()
        self.cfg = Config(database_url=test_db_url(self.tmp), upload_dir=f"{self.tmp}/up", cookie_secure=False, admin_email="admin@tb.test",
                          admin_password="correct-horse-9", rl_global=(100000, 60), rl_login=(1000, 60), rl_register=(1000, 60), rl_upload=(1000, 60),
                          allowed_origins=["http://localhost:5000"])
        self.app = create_app(self.cfg, mailer=self.mailer)
        self.ctx = self.app.ctx

    def jobs(self, rec):
        return {k: self.job(rec, auto_assessment=True, **j) for k, j in F.JOBS.items()}

    def candidate_with(self, text, email, name, maker=F.make_pdf, fname="cv.pdf"):
        c = self.candidate(email, name)
        r = self.upload(c, maker(text), fname)
        self.assertEqual(r.status_code, 201, r.json)
        self.work()
        p = c.get("/me/profile").json
        self.assertEqual(p["cvs"][0]["stage"], "ready", p["cvs"])
        self.assertEqual(c.patch("/me/profile", {"confirm": True}).status_code, 200)
        return c

    def apply_and_get(self, c, jid):
        r = c.post(f"/jobs/{jid}/apply"); self.assertEqual(r.status_code, 201, r.json)
        self.work()
        return r.json["id"]

    def take_test(self, c, aid, answers):
        sid = next(a["open_assessment_id"] for a in c.get("/me/applications").json["data"] if a["id"] == aid)
        self.assertTrue(sid, "assessment should have been sent automatically")
        self.assertEqual(c.post(f"/assessments/{sid}/start").status_code, 200)
        qs = c.get(f"/assessments/{sid}").json["task"]["questions"]
        r = c.post(f"/assessments/{sid}/submit", {"answers": {q["id"]: answers[i % len(answers)] for i, q in enumerate(qs)}})
        self.assertEqual(r.status_code, 200, r.json)
        self.work()
        return sid


class ExtractionTests(LocalBase):
    def test_pdf_and_docx_text_extracted(self):
        c = self.candidate_with(F.PRIYA, "p@example.com", "Priya Nair")
        cv = c.get("/me/profile").json["cvs"][0]
        txt = c.get(f"/cvs/{cv['id']}/text").json["text"]
        self.assertIn("RetailWorks Analytics", txt)
        d = self.candidate_with(F.MEERA, "m@example.com", "Meera Kapoor", F.make_docx, "cv.docx")
        t2 = d.get(f"/cvs/{d.get('/me/profile').json['cvs'][0]['id']}/text").json["text"]
        self.assertIn("GreenSprout", t2)

    def test_bad_uploads_rejected_with_clear_errors(self):
        c = self.candidate()
        self.assertEqual(self.upload(c, b"", "empty.pdf").status_code // 100, 4)
        self.assertEqual(self.upload(c, b"hello", "notes.txt").status_code // 100, 4)
        self.assertEqual(self.upload(c, b"MZ\x90\x00 not a pdf", "fake.pdf").status_code // 100, 4)
        r = c.post("/me/cvs", data={}, content_type="multipart/form-data")
        self.assertEqual(r.status_code // 100, 4)
        big = b"%PDF-1.4\n" + b"0" * (self.cfg.max_upload_bytes + 200000)
        self.assertEqual(self.upload(c, big, "big.pdf").status_code, 413)

    def test_scanned_pdf_reports_no_text_layer(self):
        c = self.candidate()
        r = self.upload(c, F.scanned_like_pdf(), "scan.pdf")
        self.assertEqual(r.status_code, 201)
        self.work()
        cv = c.get("/me/profile").json["cvs"][0]
        self.assertEqual(cv["stage"], "failed")
        self.assertIn("text", cv["error_message"].lower())

    def test_duplicate_upload_is_idempotent(self):
        c = self.candidate()
        data = F.make_pdf(F.PRIYA)
        self.assertEqual(self.upload(c, data).status_code, 201); self.work()
        r = self.upload(c, data)                      # the very same bytes again
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json["files"][0].get("duplicate"))
        self.assertEqual(len(c.get("/me/profile").json["cvs"]), 1)


class ParserTests(unittest.TestCase):
    def test_priya_profile(self):
        p = cv_parser.parse_cv(F.PRIYA)
        self.assertEqual(p["full_name"], "Priya Nair")
        self.assertEqual(p["email"], "priya.nair@example.com")
        names = {s["name"].lower() for s in p["skills"]}
        self.assertTrue({"sql", "excel", "power bi", "python"} <= names)
        self.assertEqual(len(p["work_history"]), 2)
        self.assertTrue(all(s["proficiency"] == "unknown" for s in p["skills"]))
        self.assertLessEqual(p["confidence"], 0.85)

    def test_three_cvs_give_three_different_profiles(self):
        ps = [cv_parser.parse_cv(t) for t in (F.PRIYA, F.ROHAN, F.MEERA)]
        self.assertEqual(len({p["full_name"] for p in ps}), 3)
        sk = [frozenset(s["name"].lower() for s in p["skills"]) for p in ps]
        self.assertEqual(len(set(sk)), 3)
        self.assertIn("docker", sk[1]); self.assertNotIn("docker", sk[0])
        self.assertIn("seo", sk[2])

    def test_unknown_stays_unknown(self):
        p = cv_parser.parse_cv("Some Person\nsome@example.com\n\nSkills\nPython\n")
        self.assertEqual(p["work_history"], [])
        self.assertEqual(p["skills"][0]["level"], "listed")      # listed on the CV, never claimed as demonstrated


class ScorerTests(unittest.TestCase):
    TASK = {"questions": [{"id": "q1", "prompt": "How would you find the top five customers by revenue last quarter?", "max_points": 100,
                           "rubric": "Mentions SQL join; filters by date; groups and sums revenue; validates the result",
                           "expected_points": [{"point": "joins and aggregates", "cues": ["join", "group", "sum", "revenue"]},
                                               {"point": "filters the period", "cues": ["date", "quarter", "filter", "where"]},
                                               {"point": "validates", "cues": ["check", "duplicate", "reconcile", "verify"]}]}]}

    def score(self, text):
        return answer_scorer.score_answers(self.TASK, {"q1": text})["per_question"][0]["score"]

    def test_scores_respond_to_content(self):
        good = ("I would join orders to customers, filter the order date to last quarter with a where clause, group by customer and sum the revenue. "
                "Then I would check for duplicate rows and reconcile the total with the finance report before sharing the five names.")
        mid = "I would join the tables and sum the revenue by customer."
        off = "I like long walks on the beach and cooking dinner for my family on weekends in autumn."
        g, m, o = self.score(good), self.score(mid), self.score(off)
        self.assertGreater(g, m); self.assertGreater(m, o)
        self.assertEqual(o, 0)
        self.assertGreater(g, 60)

    def test_blank_and_copy_and_keyword_dump(self):
        self.assertEqual(self.score(""), 0)
        copy = "How would you find the top five customers by revenue last quarter?"
        self.assertLess(self.score(copy), 15)
        dump = "join group sum revenue date quarter filter where check duplicate reconcile verify"
        self.assertLess(self.score(dump), 40)

    def test_deterministic(self):
        t = F.STRONG_ANALYST_ANSWER
        self.assertEqual(self.score(t), self.score(t))


class FullFlowTests(LocalBase):
    def setUp(self):
        super().setUp()
        self.rec = self.recruiter()
        self.jid = self.jobs(self.rec)

    def test_end_to_end_candidate_to_recruiter_and_persistence(self):
        c = self.candidate_with(F.PRIYA, "priya@example.com", "Priya Nair")
        prev = c.get(f"/me/match/{self.jid['analyst']}").json
        self.assertIn("score", prev)
        aid = self.apply_and_get(c, self.jid["analyst"])
        mine = c.get(f"/me/applications/{aid}").json
        self.assertGreater(mine["match"]["score"], 70)
        sid = self.take_test(c, aid, [F.STRONG_ANALYST_ANSWER])
        mine = c.get(f"/me/applications/{aid}").json
        self.assertIsNotNone(mine["evaluation"])
        # recruiter sees the same candidate, job and result
        lst = self.rec.get(f"/jobs/{self.jid['analyst']}/applications").json["data"]
        self.assertEqual([a["full_name"] for a in lst], ["Priya Nair"])
        detail = self.rec.get(f"/applications/{aid}").json
        self.assertTrue(detail["match"]["skills"])
        self.assertTrue(detail["match"]["limitations"])
        ev = self.ctx.db.one("SELECT overall, result, model FROM evaluations WHERE assessment_id=?", (sid,))
        self.assertGreater(ev["overall"], 30)
        self.assertTrue(ev["model"].startswith("local"))      # the evaluation records that rules, not a model, produced it
        # restart: a second app on the same database file shows the same data
        score = lst[0]["match_score"]
        self.ctx.db.close()
        app2 = create_app(self.cfg, mailer=self.mailer)
        r2 = Client(app2); self.assertEqual(r2.login("rec@acme.test").status_code, 200)
        again = r2.get(f"/jobs/{self.jid['analyst']}/applications").json["data"]
        self.assertEqual(again[0]["match_score"], score)
        self.assertEqual(r2.get(f"/applications/{aid}").status_code, 200)
        self.ctx = app2.ctx

    def test_different_cvs_get_different_matches_and_questions(self):
        a = self.candidate_with(F.PRIYA, "a@example.com", "Priya Nair")
        b = self.candidate_with(F.ROHAN, "b@example.com", "Rohan Mehta")
        aa, ab = self.apply_and_get(a, self.jid["analyst"]), self.apply_and_get(b, self.jid["analyst"])
        ra = {x["id"]: x for x in self.rec.get(f"/jobs/{self.jid['analyst']}/applications").json["data"]}
        self.assertGreater(ra[aa]["match_score"], ra[ab]["match_score"] + 20)
        def prompts(c, aid):
            sid = next(x["open_assessment_id"] for x in c.get("/me/applications").json["data"] if x["id"] == aid)
            c.post(f"/assessments/{sid}/start")
            return [q["prompt"] for q in c.get(f"/assessments/{sid}").json["task"]["questions"]]
        pa, pb = prompts(a, aa), prompts(b, ab)
        self.assertEqual(len(pa), 4); self.assertNotEqual(pa, pb)

    def test_two_jobs_same_candidate(self):
        r = self.candidate_with(F.ROHAN, "r@example.com", "Rohan Mehta")
        x, y = self.apply_and_get(r, self.jid["backend"]), self.apply_and_get(r, self.jid["analyst"])
        apps = {a["id"]: a for a in r.get("/me/applications").json["data"]}
        self.assertGreater(apps[x]["match_score"], apps[y]["match_score"] + 15)

    def test_double_apply_is_idempotent_and_auto_assessment_sent_once(self):
        c = self.candidate_with(F.PRIYA, "p@example.com", "Priya Nair")
        aid = self.apply_and_get(c, self.jid["analyst"])
        again = c.post(f"/jobs/{self.jid['analyst']}/apply")
        self.assertIn(again.status_code, (200, 201, 409))
        self.work()
        n = self.ctx.db.scalar("SELECT COUNT(*) FROM assessments WHERE application_id=?", (aid,))
        self.assertEqual(n, 1)

    def test_strong_beats_weak_and_off_topic(self):
        out = []
        for i, ans in enumerate((F.STRONG_ANALYST_ANSWER, F.WEAK_ANSWER, F.OFF_TOPIC_ANSWER)):
            c = self.candidate_with(F.PRIYA, f"p{i}@example.com", f"Priya {i}")
            aid = self.apply_and_get(c, self.jid["analyst"])
            sid = self.take_test(c, aid, [ans])
            out.append(self.ctx.db.scalar("SELECT overall FROM evaluations WHERE assessment_id=?", (sid,)))
        self.assertGreater(out[0], 30); self.assertGreater(out[0], out[1] + 25); self.assertGreater(out[0], out[2] + 25)
        self.assertLess(max(out[1], out[2]), 15)

    def test_confidence_is_capped_and_flagged_for_rule_based_scoring(self):
        c = self.candidate_with(F.PRIYA, "p@example.com", "Priya Nair")
        aid = self.apply_and_get(c, self.jid["analyst"])
        sid = self.take_test(c, aid, [F.STRONG_ANALYST_ANSWER])
        res = json.loads(self.ctx.db.scalar("SELECT result FROM evaluations WHERE assessment_id=?", (sid,)))
        self.assertLessEqual(res["confidence"], 0.7)
        self.assertIn("rule_based_scoring", res["flags"])


class RecruiterEndpointTests(LocalBase):
    def setUp(self):
        super().setUp()
        self.rec = self.recruiter(); self.jid = self.jobs(self.rec)
        self.ids = []
        # each account uploads its own CV (an account uploading someone else's CV is covered in test_regressions)
        for i, (t, n) in enumerate(((F.PRIYA, "Priya Nair"), (F.ROHAN, "Rohan Mehta"), (F.MEERA, "Meera Kapoor"))):
            c = self.candidate_with(t, f"c{i}@example.com", n)
            self.ids.append(self.apply_and_get(c, self.jid["analyst"]))

    def test_compare(self):
        r = self.rec.get(f"/jobs/{self.jid['analyst']}/compare?ids={','.join(self.ids)}")
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(len(r.json["applications"]), 3)
        self.assertEqual(self.rec.get(f"/jobs/{self.jid['analyst']}/compare?ids={self.ids[0]}").status_code, 400)
        self.assertEqual(self.rec.get(f"/jobs/{self.jid['backend']}/compare?ids={self.ids[0]},{self.ids[1]}").status_code, 404)

    def test_dashboard_summary_and_suggest_skills(self):
        d = self.rec.get("/dashboard/summary").json
        self.assertEqual(d["applications"]["total"], 3); self.assertEqual(d["jobs"]["open"], len(F.JOBS))
        s = self.rec.post("/jobs/suggest-skills", {"description": "You will write SQL, build Power BI dashboards and use Excel."}).json["skills"]
        self.assertTrue({"SQL", "Power BI", "Excel"} <= {x["name"] for x in s})

    def test_candidate_filters_and_stage_decision(self):
        self.assertEqual(self.rec.post(f"/applications/{self.ids[0]}/transition", {"to": "rejected"}).status_code, 200)
        self.assertEqual(self.rec.post(f"/applications/{self.ids[0]}/transition", {"to": "offer"}).status_code, 409)   # cannot skip stages
        self.assertEqual(self.rec.get(f"/applications/{self.ids[0]}").json["status"], "rejected")

    def test_job_edit_and_toggle_auto_assessment(self):
        r = self.rec.patch(f"/jobs/{self.jid['marketing']}", {"auto_assessment": False, "min_years": 2})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertFalse(self.rec.get(f"/jobs/{self.jid['marketing']}").json["auto_assessment"])


class PermissionTests(LocalBase):
    def setUp(self):
        super().setUp()
        self.rec = self.recruiter(); self.jid = self.jobs(self.rec)
        self.a = self.candidate_with(F.PRIYA, "a@example.com", "Priya Nair")
        self.b = self.candidate_with(F.ROHAN, "b@example.com", "Rohan Mehta")
        self.aid = self.apply_and_get(self.a, self.jid["analyst"])

    def test_candidate_cannot_use_recruiter_endpoints(self):
        for path in ("/dashboard/summary", "/candidates", f"/jobs/{self.jid['analyst']}/applications", f"/applications/{self.aid}"):
            self.assertIn(self.b.get(path).status_code, (403, 404), path)
        self.assertEqual(self.b.post("/jobs", {"title": "x"}).status_code, 403)

    def test_candidate_cannot_see_other_candidates_data(self):
        self.assertEqual(self.b.get(f"/me/applications/{self.aid}").status_code, 404)
        cv = self.a.get("/me/profile").json["cvs"][0]["id"]
        self.assertIn(self.b.get(f"/cvs/{cv}/text").status_code, (403, 404))
        self.assertEqual(len(self.b.get("/me/applications").json["data"]), 0)

    def test_other_organisation_cannot_see_my_applications(self):
        other = self.recruiter("rec2@other.test", "Other Co", name="Omar")
        self.assertEqual(other.get(f"/applications/{self.aid}").status_code, 404)
        self.assertEqual(other.get(f"/jobs/{self.jid['analyst']}/compare?ids={self.aid},{self.aid}").status_code, 404)

    def test_anonymous_and_missing_csrf(self):
        anon = self.client()
        self.assertEqual(anon.get("/me/applications").status_code, 401)
        c = self.client(); c.login("a@example.com")
        c.csrf = None
        self.assertIn(c.post(f"/jobs/{self.jid['analyst']}/apply").status_code, (400, 403))

    def test_api_error_shapes(self):
        r = self.rec.get("/applications/does-not-exist")
        self.assertEqual(r.status_code, 404); self.assertIn("error", r.json)
        self.assertEqual(self.rec.post("/jobs", {}).status_code, 422)


class ProviderTests(LocalBase):
    def test_default_provider_is_local_and_health_says_so(self):
        self.assertTrue(getattr(self.ctx.ai, "is_local", False))
        h = self.client().get("/health").json
        self.assertTrue(h["ai_provider"].startswith("local"))

    def test_ollama_unavailable_falls_back_to_rules_and_flags(self):
        cfg = Config(**{**self.cfg.__dict__, "ai_provider": "ollama", "ollama_url": "http://127.0.0.1:9", "ollama_timeout": 1})
        ai = ai_mod.get_provider(cfg)
        task = {"questions": [{"id": "q1", "prompt": "Explain joins.", "max_points": 100, "rubric": "join tables on keys",
                               "expected_points": [{"point": "join", "cues": ["join", "key"]}]}]}
        res = ai_mod.evaluate(ai, task, {"q1": "A join combines rows from two tables using a shared key column."}, {}, {})
        self.assertIn("model_unavailable_rules_used", res["flags"])
        self.assertGreater(res["overall"], 0)

    def test_ollama_mock_server_is_used(self):
        reply = {"score": 80, "rationale": "Good.", "evidence": ["join combines rows"]}     # local models score one question per call
        seen = []

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(self.path); self.rfile.read(int(self.headers.get("Content-Length", 0)))
                out = json.dumps({"message": {"content": json.dumps(reply)}, "response": json.dumps(reply)}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)
            def log_message(self, *a): pass
        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            cfg = Config(**{**self.cfg.__dict__, "ai_provider": "ollama", "ollama_url": f"http://127.0.0.1:{srv.server_port}", "ollama_timeout": 5})
            ai = ai_mod.get_provider(cfg)
            task = {"questions": [{"id": "q1", "prompt": "Explain joins.", "max_points": 100, "rubric": "join"}]}
            res = ai_mod.evaluate(ai, task, {"q1": "A join combines rows from two tables using a shared key."}, {}, {})
            self.assertTrue(seen)
            self.assertNotIn("model_unavailable_rules_used", res["flags"])
            self.assertTrue(res["engine"].startswith("ollama:"))
            self.assertEqual(res["per_question"][0]["score"], 80)
            self.assertLessEqual(res["confidence"], 0.9)
        finally:
            srv.shutdown()


class SimilarityTests(unittest.TestCase):
    def test_lexical_orders_sensibly(self):
        job = "SQL dashboards Power BI reporting stakeholders analysis"
        self.assertGreater(similarity.lexical(F.PRIYA, job)["score"], similarity.lexical(F.MEERA, job)["score"])

    def test_semantic_with_stub_encoder_and_fallback(self):
        class Stub:
            def encode(self, texts): return [[1.0, 0.0] if "sql" in t.lower() else [0.0, 1.0] for t in texts]
        self.assertEqual(similarity.compare(F.PRIYA, "SQL reporting", encoder=Stub())["method"], "semantic")
        class Broken:
            def encode(self, texts): raise RuntimeError("model missing")
        self.assertEqual(similarity.compare(F.PRIYA, "SQL reporting", encoder=Broken())["method"], "lexical")   # falls back, never fails
        self.assertEqual(similarity.compare(F.PRIYA, "SQL reporting", encoder=None)["method"], "lexical")


class DemoSeedTests(LocalBase):
    def test_seed_is_idempotent_and_scores_distinct(self):
        import os
        from app import seed
        seed.seed_accounts(self.ctx); seed.seed_accounts(self.ctx)
        self.assertEqual(self.ctx.db.scalar("SELECT COUNT(*) FROM jobs"), len(F.JOBS))
        sample = os.path.join(os.path.dirname(__file__), "..", "..", "sample_data")
        out = seed.seed_candidates(self.app, sample)
        self.assertTrue(any("assessment scored" in l for l in out), out)
        again = seed.seed_candidates(self.app, sample)
        self.assertTrue(all("skipped" in l for l in again), again)
        scores = [r["overall"] for r in self.ctx.db.all("SELECT overall FROM evaluations")]
        self.assertGreaterEqual(len(set(scores)), 3)


if __name__ == "__main__":
    unittest.main()
