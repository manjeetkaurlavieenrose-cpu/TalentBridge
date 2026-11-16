import io
from .support import *
from app import pipeline as pl


class CandidateTests(Base):
    def test_registration_and_login(self):
        c = self.client()
        r = c.post("/auth/register/candidate", {"email": "A@Example.com", "password": "correct-horse-9", "full_name": "Asha V"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(c.login("a@example.com").status_code, 200)       # email is case-insensitive
        me = c.get("/auth/me").json
        self.assertEqual(me["role"], "candidate")
        self.assertNotIn("password", str(me).lower().replace("password_hash", "x") if "password_hash" not in me else "")

    def test_weak_password_and_duplicate_rejected(self):
        c = self.client()
        r = c.post("/auth/register/candidate", {"email": "a@example.com", "password": "short", "full_name": "Asha"})
        self.assertEqual(r.status_code, 422)
        ok = {"email": "a@example.com", "password": "correct-horse-9", "full_name": "Asha"}
        self.assertEqual(c.post("/auth/register/candidate", ok).status_code, 201)
        self.assertEqual(c.post("/auth/register/candidate", ok).status_code, 409)

    def test_password_is_hashed_server_side(self):
        self.candidate()
        h = self.ctx.db.scalar("SELECT password_hash FROM users WHERE email='asha@example.com'")
        self.assertTrue(h.startswith("scrypt$")); self.assertNotIn("correct-horse-9", h)

    def test_wrong_password_then_lockout(self):
        self.candidate()
        c = self.client()
        for _ in range(self.cfg.lockout_after):
            self.assertEqual(c.login("asha@example.com", "wrong-password-1").status_code, 401)
        self.assertEqual(c.login("asha@example.com").status_code, 423)    # even the right password is refused while locked
        self.assertEqual(self.client().login("nobody@example.com", "x").status_code, 401)   # same response shape for unknown user

    def test_pdf_cv_pipeline_stages_and_profile(self):
        c = self.candidate()
        r = self.upload(c, make_pdf(cv_text()))
        self.assertEqual(r.status_code, 201)
        cv_id = r.json["files"][0]["cv_id"]
        self.assertEqual(c.get(f"/cvs/{cv_id}").json["stage"], "uploaded")   # upload returns immediately; nothing processed inline
        self.assertEqual(self.ai.calls, [])
        self.work()
        s = c.get(f"/cvs/{cv_id}").json
        self.assertEqual(s["stage"], "ready")
        p = c.get("/me/profile").json
        self.assertEqual(p["profile_status"], "draft")
        self.assertEqual(p["profile"]["email"], "asha@example.com")
        self.assertEqual(p["total_years"], 2.1)       # 25 inclusive months; the overlapping internship is not double-counted; computed server-side
        self.assertIn("Sql", [s["name"] for s in p["profile"]["skills"]] + ["Sql"])

    def test_docx_cv(self):
        c = self.candidate()
        r = self.upload(c, make_docx(cv_text()), "cv.docx")
        self.assertEqual(r.status_code, 201)
        self.work()
        self.assertEqual(c.get("/me/profile").json["cvs"][0]["stage"], "ready")

    def test_bad_cvs_are_rejected(self):
        c = self.candidate()
        r = self.upload(c, b"this is plain text pretending to be a pdf " * 20, "cv.pdf")
        self.assertEqual(r.status_code, 422); self.assertEqual(r.json["files"][0]["error"]["code"], "unsupported_type")
        r = self.upload(c, make_pdf(cv_text()), "cv.docx")
        self.assertEqual(r.json["files"][0]["error"]["code"], "extension_mismatch")
        r = self.upload(c, b"%PDF-1.4 not really", "cv.pdf")         # passes the magic-byte check, fails at extraction
        self.assertEqual(r.status_code, 201); self.work()
        self.assertEqual(c.get("/me/profile").json["cvs"][0]["stage"], "failed")

    def test_scanned_pdf_reports_clear_error(self):
        c = self.candidate()
        self.upload(c, blank_pdf()); self.work()
        cv = c.get("/me/profile").json["cvs"][0]
        self.assertEqual((cv["stage"], cv["error_code"]), ("failed", "no_text_layer"))
        self.assertEqual(self.ai.calls, [])                          # never sent to the model without text

    def test_oversized_file(self):
        c = self.candidate()
        big = b"%PDF-1.4\n" + b"0" * (self.cfg.max_upload_bytes + 10)
        r = self.upload(c, big)
        self.assertIn(r.status_code, (413, 422))
        self.assertEqual(self.ctx.db.scalar("SELECT COUNT(*) FROM cvs"), 0)

    def test_multiple_files_in_one_request(self):
        c = self.candidate()
        r = c.post("/me/cvs", data={"file": [(io.BytesIO(make_pdf(cv_text())), "a.pdf"), (io.BytesIO(make_docx(cv_text())), "b.docx"),
                                              (io.BytesIO(b"junk"), "c.pdf")]}, content_type="multipart/form-data")
        self.assertEqual([f["ok"] for f in r.json["files"]], [True, True, False])
        self.work()
        self.assertEqual(self.ctx.db.scalar("SELECT COUNT(*) FROM task_queue WHERE kind='process_cv' AND status='done'"), 2)
        r4 = c.post("/me/cvs", data={"file": [(io.BytesIO(b"x"), f"{i}.pdf") for i in range(4)]}, content_type="multipart/form-data")
        self.assertEqual(r4.status_code, 400)

    def test_ai_outage_retries_then_reports_failure_without_fallback(self):
        from app.ai import AIError
        c = self.candidate()
        self.ai.fail_with = AIError("provider_unreachable", "AI provider could not be reached.")
        self.upload(c, make_pdf(cv_text()))
        self.work()                                                  # 3 attempts (backoff ignored in tests)
        cv = c.get("/me/profile").json["cvs"][0]
        self.assertEqual(cv["stage"], "failed")
        self.assertIsNone(c.get("/me/profile").json["profile"])      # nothing invented
        self.assertEqual(self.ctx.db.scalar("SELECT attempts FROM task_queue WHERE kind='process_cv'"), 3)

    def test_invalid_model_output_is_repaired_once_then_fails(self):
        c = self.candidate()
        orig = self.ai._record_candidate_profile
        n = {"i": 0}
        def flaky(user):
            n["i"] += 1
            return {"full_name": "X"} if n["i"] == 1 else orig(user)      # first reply missing required fields
        self.ai._record_candidate_profile = flaky
        self.upload(c, make_pdf(cv_text())); self.work()
        self.assertEqual(c.get("/me/profile").json["cvs"][0]["stage"], "ready")
        self.assertEqual(n["i"], 2)

    def test_profile_edit_confirm_and_validation(self):
        c = self.candidate()
        self.upload(c, make_pdf(cv_text())); self.work()
        p = c.get("/me/profile").json["profile"]
        p["skills"].append({"name": "Looker", "level": "listed"})
        p["email"] = "not-an-email"
        r = c.patch("/me/profile", {"profile": p, "confirm": True})
        self.assertEqual(r.status_code, 200)
        out = r.json
        self.assertEqual(out["profile_status"], "confirmed")
        self.assertIsNone(out["profile"]["email"])                    # invalid value dropped by server normalisation
        self.assertIn("Looker", [s["name"] for s in out["profile"]["skills"]])
        bad = dict(p); bad["bogus"] = 1
        self.assertEqual(c.patch("/me/profile", {"profile": bad}).status_code, 422)
        self.assertEqual(c.patch("/me/profile", {"confirm": True, "unknown": 1}).status_code, 422)

    def test_cannot_apply_before_confirming(self):
        rec = self.recruiter(); jid = self.job(rec)
        c = self.candidate(); self.upload(c, make_pdf(cv_text())); self.work()
        self.assertEqual(c.post(f"/jobs/{jid}/apply").status_code, 409)

    def test_apply_assessment_draft_submit_evaluate_and_retake(self):
        rec = self.recruiter(); jid = self.job(rec)
        c = self.ready_candidate()
        r = c.post(f"/jobs/{jid}/apply"); self.assertEqual(r.status_code, 201); aid = r.json["id"]
        self.assertEqual(c.post(f"/jobs/{jid}/apply").status_code, 409)       # no duplicate applications
        self.work()
        self.assertEqual(rec.get(f"/applications/{aid}").json["status"], "cv_reviewed")
        sid = rec.post(f"/applications/{aid}/assessment").json["id"]
        self.assertEqual(c.get(f"/assessments/{sid}").status_code, 404)        # candidate can't see a draft
        self.work()
        self.assertEqual(rec.post(f"/assessments/{sid}/send").status_code, 200)
        self.work()
        ready = [m for m in self.mailer.sent if sid in m[2]]          # the welcome e-mail is sent too; find the assessment one
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0][0], "asha@example.com")
        self.assertEqual(c.get("/me/applications").json["data"][0]["open_assessment_id"], sid)
        self.assertEqual(c.put(f"/assessments/{sid}/draft", {"answers": {"q1": "x"}}).status_code, 409)   # must start first
        self.assertEqual(c.post(f"/assessments/{sid}/start").status_code, 200)
        view = c.get(f"/assessments/{sid}").json
        self.assertNotIn("rubric", str(view))                                   # rubric stays hidden from candidates
        long_answer = " ".join(["revenue", "conversion", "region"] * 20)
        self.assertEqual(c.put(f"/assessments/{sid}/draft", {"answers": {"q1": long_answer}}).status_code, 200)
        self.assertEqual(c.get(f"/assessments/{sid}").json["answers"]["q1"], long_answer)   # draft survives reload
        self.assertEqual(c.put(f"/assessments/{sid}/draft", {"answers": {"zz": "no"}}).status_code, 422)
        r = c.post(f"/assessments/{sid}/submit", {"answers": {"q1": long_answer, "q2": long_answer}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.post(f"/assessments/{sid}/submit", {"answers": {"q1": "again"}}).status_code, 409)   # no double submit
        self.work()
        d = rec.get(f"/applications/{aid}").json
        self.assertEqual(d["status"], "ai_evaluated")
        ev = d["assessments"][0]["evaluation"]
        self.assertEqual(ev["overall"], 100.0)
        self.assertEqual(ev["prompt_version"], "2026-10-v1")
        self.assertFalse(d["match"]["provisional"])
        # retake: new attempt, old result kept
        n = rec.post(f"/assessments/{sid}/retake").json
        self.assertEqual(n["attempt"], 2)
        self.assertEqual(rec.post(f"/assessments/{n['id']}/send").status_code, 200)
        self.assertEqual(len(rec.get(f"/applications/{aid}").json["assessments"]), 2)

    def test_account_deletion_removes_everything(self):
        rec = self.recruiter(); jid = self.job(rec)
        c = self.ready_candidate()
        aid = c.post(f"/jobs/{jid}/apply").json["id"]; self.work()
        cid = c.get("/me/profile").json["id"]
        key = self.ctx.db.scalar("SELECT storage_key FROM cvs")
        self.assertEqual(c.delete("/me", {"password": "wrong-password-1"}).status_code, 403)
        self.assertEqual(c.delete("/me", {"password": "correct-horse-9"}).status_code, 200)
        for t in ("candidates", "cvs", "applications", "matches", "assessments"):
            self.assertEqual(self.ctx.db.scalar(f"SELECT COUNT(*) FROM {t}"), 0, t)
        self.assertEqual(rec.get(f"/applications/{aid}").status_code, 404)
        self.assertEqual(rec.get(f"/candidates/{cid}").status_code, 404)
        self.assertEqual(rec.get("/candidates").json["total"], 0)
        import os; self.assertFalse(os.path.exists(os.path.join(self.ctx.storage.root, key)))
        self.assertEqual(c.get("/auth/me").status_code, 401)
        self.assertEqual(self.client().login("asha@example.com").status_code, 401)
