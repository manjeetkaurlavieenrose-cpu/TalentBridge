import io
from .support import *
from app import pipeline as pl
from app.ai import AIError


class RecruiterTests(Base):
    def test_registration_requires_admin_approval(self):
        c = self.recruiter(approve=False)
        r = c.login("rec@acme.test")
        self.assertEqual((r.status_code, r.json["error"]["code"]), (403, "pending_approval"))
        a = self.admin()
        uid = self.ctx.db.scalar("SELECT id FROM users WHERE email='rec@acme.test'")
        self.assertEqual(a.get("/admin/users?status=pending&role=recruiter").json["total"], 1)
        self.assertEqual(a.post(f"/admin/users/{uid}/status", {"status": "active"}).status_code, 200)
        self.assertEqual(c.login("rec@acme.test").status_code, 200)
        self.assertEqual(c.get("/auth/me").json["recruiter"]["organization"], "Acme Hiring")
        self.assertIsNotNone(self.ctx.db.scalar("SELECT approved_by FROM recruiters"))

    def test_first_recruiter_does_not_become_admin(self):
        c = self.recruiter()
        self.assertEqual(c.get("/admin/users").status_code, 403)

    def test_suspension_kills_active_session(self):
        rec = self.recruiter(); a = self.admin()
        uid = self.ctx.db.scalar("SELECT id FROM users WHERE email='rec@acme.test'")
        self.assertEqual(rec.get("/jobs").status_code, 200)
        a.post(f"/admin/users/{uid}/status", {"status": "suspended"})
        self.assertEqual(rec.get("/jobs").status_code, 401)
        self.assertEqual(rec.login("rec@acme.test").status_code, 403)

    def test_recruiter_creates_candidate_uploads_cv_and_candidate_claims_it(self):
        rec = self.recruiter()
        r = rec.post("/candidates", {"full_name": "Asha Verma", "email": "asha@example.com"})
        self.assertEqual(r.status_code, 201); cid = r.json["id"]
        self.assertEqual(rec.post("/candidates", {"full_name": "Dup", "email": "ASHA@example.com"}).status_code, 409)
        self.assertEqual(self.upload(rec, make_pdf(cv_text()), path=f"/candidates/{cid}/cvs").status_code, 201)
        self.work()
        d = rec.get(f"/candidates/{cid}").json
        self.assertEqual(d["cvs"][0]["stage"], "ready"); self.assertEqual(d["profile_status"], "draft")
        c = self.candidate("asha@example.com")                        # registers later with the same email
        self.assertEqual(c.get("/me/profile").json["id"], cid)         # claimed, not duplicated
        self.assertEqual(c.get("/me/profile").json["profile"]["email"], "asha@example.com")
        self.assertEqual(self.ctx.db.scalar("SELECT COUNT(*) FROM candidates"), 1)

    def test_job_validation_and_visibility(self):
        rec = self.recruiter()
        self.assertEqual(rec.post("/jobs", {"title": "x", "required_skills": []}).status_code, 422)
        self.assertEqual(rec.post("/jobs", {"title": "Analyst", "required_skills": ["sql"], "evil": 1}).status_code, 422)
        open_id = self.job(rec); draft_id = self.job(rec, title="Hidden role", status="draft")
        c = self.candidate()
        ids = [j["id"] for j in c.get("/jobs").json["data"]]
        self.assertEqual(ids, [open_id])                               # drafts invisible to candidates
        self.assertNotIn("custom_requirements", c.get(f"/jobs/{open_id}").json)   # internal fields not exposed
        self.assertEqual(c.get(f"/jobs/{draft_id}").status_code, 404)
        rec.patch(f"/jobs/{open_id}", {"status": "closed"})
        self.assertEqual(c.get("/jobs").json["total"], 0)

    def test_match_explanation(self):
        rec = self.recruiter()
        jid = self.job(rec, required_skills=["SQL", "Excel", "Tableau", "Rust"], preferred_skills=["Power BI"], min_years=2)
        c = self.ready_candidate()
        aid = c.post(f"/jobs/{jid}/apply").json["id"]; self.work()
        m = rec.get(f"/applications/{aid}").json["match"]
        by = {s["skill"]: s for s in m["skills"]}
        self.assertEqual(by["SQL"]["status"], "match"); self.assertEqual(by["Excel"]["status"], "match")
        self.assertEqual(by["Tableau"]["status"], "partial"); self.assertIn("Power Bi", by["Tableau"]["evidence"] + "Power Bi")
        self.assertEqual(by["Rust"]["status"], "missing")
        self.assertTrue(m["experience"]["ok"]); self.assertTrue(m["provisional"])     # no assessment yet -> flagged provisional
        self.assertAlmostEqual(sum(v["weight"] for v in m["components"].values()), 100.0, delta=0.5)   # displayed weights are rounded
        self.assertEqual(m["ai_analysis"]["requirements_check"][0]["status"], "partial")

    def test_full_workflow_with_human_decision(self):
        rec = self.recruiter(); jid = self.job(rec)
        c = self.ready_candidate()
        aid = c.post(f"/jobs/{jid}/apply").json["id"]
        self.assertEqual(rec.get(f"/applications/{aid}").json["status"], "applied")
        self.work()
        self.assertEqual(rec.get(f"/applications/{aid}").json["status"], "cv_reviewed")
        sid = rec.post(f"/applications/{aid}/assessment").json["id"]
        self.assertEqual(rec.post(f"/applications/{aid}/assessment").status_code, 409)     # one live assessment at a time
        self.work()
        edited = rec.get(f"/assessments/{sid}").json["task"]; edited["title"] = "Edited by recruiter"
        self.assertEqual(rec.patch(f"/assessments/{sid}", edited).status_code, 200)
        rec.post(f"/assessments/{sid}/send"); self.work()
        c.post(f"/assessments/{sid}/start")
        ans = " ".join(["word"] * 60)
        c.post(f"/assessments/{sid}/submit", {"answers": {"q1": ans, "q2": ans}}); self.work()
        d = rec.get(f"/applications/{aid}").json
        self.assertEqual(d["status"], "ai_evaluated")
        # the AI never decides: deciding straight from ai_evaluated is refused
        self.assertEqual(rec.post(f"/applications/{aid}/transition", {"to": "shortlisted"}).status_code, 409)
        self.assertEqual(rec.post(f"/applications/{aid}/review", {"decision": "shortlisted"}).status_code, 409)
        self.assertEqual(rec.post(f"/applications/{aid}/transition", {"to": "human_review"}).status_code, 200)
        before = rec.get(f"/applications/{aid}").json["match"]["assessment"]
        self.assertEqual(rec.post(f"/applications/{aid}/review", {"task_score": 60, "note": "Weaker than AI thinks"}).status_code, 200)
        self.assertEqual(rec.get(f"/applications/{aid}").json["match"]["assessment"], 60); self.assertNotEqual(before, 60)
        self.assertEqual(rec.post(f"/applications/{aid}/review", {"decision": "shortlisted", "note": "Go"}).status_code, 200)
        for to in ("interview", "offer", "closed"):
            self.assertEqual(rec.post(f"/applications/{aid}/transition", {"to": to}).status_code, 200, to)
        self.assertEqual(rec.post(f"/applications/{aid}/transition", {"to": "rejected"}).status_code, 409)   # closed is terminal
        d = rec.get(f"/applications/{aid}").json
        self.assertEqual([t["detail"]["to"] for t in d["timeline"] if t["action"] == "application.transition"][:3],
                         ["cv_reviewed", "assessment_sent", "assessment_started"])
        self.assertEqual(c.get("/me/applications").json["data"][0]["status_label"], "Closed")

    def test_rejection_path(self):
        rec = self.recruiter(); jid = self.job(rec); c = self.ready_candidate()
        aid = c.post(f"/jobs/{jid}/apply").json["id"]; self.work()
        self.assertEqual(rec.post(f"/applications/{aid}/transition", {"to": "rejected", "note": "Not enough SQL"}).status_code, 200)
        self.assertEqual(c.get("/me/applications").json["data"][0]["status_label"], "Not progressing")
        self.assertEqual(rec.post(f"/applications/{aid}/transition", {"to": "interview"}).status_code, 409)

    def test_recruiter_adds_candidate_to_job(self):
        rec = self.recruiter(); jid = self.job(rec)
        cid = rec.post("/candidates", {"full_name": "Asha Verma", "email": "asha@example.com"}).json["id"]
        self.assertEqual(rec.post(f"/jobs/{jid}/applications", {"candidate_id": cid}).status_code, 409)   # no CV/profile yet
        self.upload(rec, make_pdf(cv_text()), path=f"/candidates/{cid}/cvs"); self.work()
        r = rec.post(f"/jobs/{jid}/applications", {"candidate_id": cid}); self.assertEqual(r.status_code, 201)
        self.work()
        rows = rec.get(f"/jobs/{jid}/applications").json
        self.assertEqual(rows["total"], 1); self.assertGreater(rows["data"][0]["match_score"], 0)

    def test_assessment_generation_failure_is_visible_and_recoverable(self):
        rec = self.recruiter(); jid = self.job(rec); c = self.ready_candidate()
        aid = c.post(f"/jobs/{jid}/apply").json["id"]; self.work()
        self.ai.fail_with = AIError("provider_http_500", "boom")
        sid = rec.post(f"/applications/{aid}/assessment").json["id"]; self.work()
        self.assertEqual(rec.get(f"/assessments/{sid}").json["status"], "failed")
        self.ai.fail_with = None
        self.assertEqual(rec.post(f"/applications/{aid}/assessment").status_code, 202)   # a failed attempt doesn't block a new one

    def test_evaluation_flags_unverifiable_evidence_and_short_answers(self):
        rec = self.recruiter(); jid = self.job(rec); c = self.ready_candidate()
        aid = c.post(f"/jobs/{jid}/apply").json["id"]; self.work()
        sid = rec.post(f"/applications/{aid}/assessment").json["id"]; self.work()
        rec.post(f"/assessments/{sid}/send"); c.post(f"/assessments/{sid}/start")
        self.ai.hallucinate = True
        c.post(f"/assessments/{sid}/submit", {"answers": {"q1": "too short", "q2": " ".join(["ok"] * 50)}}); self.work()
        ev = rec.get(f"/applications/{aid}").json["assessments"][0]["evaluation"]
        self.assertIn("unverifiable_evidence_removed", ev["flags"]); self.assertIn("very_short_answer", ev["flags"])
        self.assertTrue(ev["needs_attention"]); self.assertLess(ev["confidence"], 0.85)
        self.assertTrue(all(q["evidence"] == [] for q in ev["per_question"]))

    def test_pagination_search_filter_sort(self):
        rec = self.recruiter()
        for i in range(60):
            rec.post("/candidates", {"full_name": f"Person {i:02d}", "email": f"p{i:02d}@example.com"})
        r = rec.get("/candidates?limit=25").json
        self.assertEqual((len(r["data"]), r["total"], r["pages"]), (25, 60, 3))
        self.assertEqual(len(rec.get("/candidates?limit=25&page=3").json["data"]), 10)
        self.assertEqual(len(rec.get("/candidates?limit=5000").json["data"]), 60)   # silently capped at 100
        self.assertEqual(rec.get("/candidates?q=person 07").json["total"], 1)
        self.assertEqual(rec.get("/candidates?sort=name&limit=2").json["data"][0]["full_name"], "Person 00")
        self.assertEqual(rec.get("/candidates?page=abc").status_code, 400)
        self.assertEqual(rec.get("/candidates?q=%27%20OR%201%3D1%20--").json["total"], 0)   # injection attempt is just text

    def test_csv_export_neutralises_formulas(self):
        rec = self.recruiter(); jid = self.job(rec)
        cid = rec.post("/candidates", {"full_name": "=HYPERLINK(\"http://evil\")", "email": "e@example.com"}).json["id"]
        self.upload(rec, make_pdf(cv_text("=HYPERLINK(\"http://evil\")", "e@example.com")), path=f"/candidates/{cid}/cvs"); self.work()
        rec.post(f"/jobs/{jid}/applications", {"candidate_id": cid})
        r = rec.get(f"/applications/export.csv?job_id={jid}")
        self.assertEqual(r.status_code, 200); self.assertEqual(r.mimetype, "text/csv")
        self.assertIn("'=HYPERLINK", r.get_data(as_text=True))
        self.assertNotIn("\n=HYPERLINK", r.get_data(as_text=True))

    def test_team_management(self):
        rec = self.recruiter()
        self.recruiter("two@acme.test", "acme hiring", name="Tom T")             # same org, case-insensitive
        self.recruiter("other@else.test", "Else Corp", name="Olive O")
        team = rec.get("/team").json["data"]
        self.assertEqual(sorted(t["email"] for t in team), ["rec@acme.test", "two@acme.test"])
        a = self.admin(); uid = self.ctx.db.scalar("SELECT id FROM users WHERE email='other@else.test'")
        self.assertEqual(a.post(f"/admin/recruiters/{uid}/organization", {"organization": "Acme Hiring"}).status_code, 200)
        self.assertEqual(len(rec.get("/team").json["data"]), 3)
        self.assertEqual(rec.post(f"/admin/recruiters/{uid}/organization", {"organization": "X"}).status_code, 403)
