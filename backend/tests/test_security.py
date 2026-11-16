import io
from .support import *


class SecurityTests(Base):
    def test_unauthenticated_requests_fail(self):
        c = self.client()
        for m, u in (("get", "/auth/me"), ("get", "/candidates"), ("get", "/jobs"), ("post", "/jobs"), ("get", "/applications/x"),
                     ("get", "/me/profile"), ("get", "/admin/users"), ("get", "/admin/audit-logs"), ("get", "/cvs/x"), ("post", "/me/cvs")):
            self.assertEqual(getattr(c, m)(u).status_code, 401, u)

    def test_candidate_cannot_use_recruiter_or_admin_endpoints(self):
        c = self.ready_candidate()
        for m, u in (("get", "/candidates"), ("post", "/jobs"), ("get", "/team"), ("get", "/admin/users"), ("get", "/applications/export.csv?job_id=x")):
            self.assertEqual(getattr(c, m)(u).status_code, 403, u)

    def test_recruiter_cannot_use_admin_functions_or_candidate_functions(self):
        rec = self.recruiter()
        self.assertEqual(rec.get("/admin/users").status_code, 403)
        self.assertEqual(rec.get("/admin/audit-logs").status_code, 403)
        self.assertEqual(rec.post("/admin/users/abc/status", {"status": "active"}).status_code, 403)
        self.assertEqual(rec.get("/me/profile").status_code, 403)
        self.assertEqual(rec.post("/me/cvs").status_code, 403)

    def test_candidate_a_cannot_reach_candidate_b(self):
        rec = self.recruiter(); jid = self.job(rec)
        a = self.ready_candidate("a@example.com", "Alice A"); b = self.ready_candidate("b@example.com", "Bob B")
        aid = a.post(f"/jobs/{jid}/apply").json["id"]; self.work()
        a_cv = a.get("/me/profile").json["cvs"][0]["id"]; a_cid = a.get("/me/profile").json["id"]
        sid = rec.post(f"/applications/{aid}/assessment").json["id"]; self.work(); rec.post(f"/assessments/{sid}/send")
        self.assertEqual(b.get(f"/cvs/{a_cv}").status_code, 404)
        self.assertEqual(b.get(f"/cvs/{a_cv}/file").status_code, 404)
        self.assertEqual(b.get(f"/assessments/{sid}").status_code, 404)
        self.assertEqual(b.post(f"/assessments/{sid}/start").status_code, 404)
        self.assertEqual(b.put(f"/assessments/{sid}/draft", {"answers": {}}).status_code, 404)
        self.assertEqual(b.post(f"/assessments/{sid}/submit", {"answers": {"q1": "hi"}}).status_code, 404)
        self.assertEqual(b.get("/me/applications").json["data"], [])
        self.assertEqual(a.get(f"/cvs/{a_cv}").status_code, 200)       # control: the owner still can
        self.assertEqual(b.get("/me/profile").json["email"], "b@example.com")

    def test_recruiters_are_isolated_by_organisation(self):
        r1 = self.recruiter("r1@one.test", "One Ltd"); r2 = self.recruiter("r2@two.test", "Two Ltd")
        jid = self.job(r1); c = self.ready_candidate()
        aid = c.post(f"/jobs/{jid}/apply").json["id"]; self.work()
        cid = c.get("/me/profile").json["id"]; cv = c.get("/me/profile").json["cvs"][0]["id"]
        self.assertEqual(r1.get(f"/applications/{aid}").status_code, 200)
        for u in (f"/applications/{aid}", f"/jobs/{jid}", f"/jobs/{jid}/applications", f"/candidates/{cid}", f"/cvs/{cv}", f"/cvs/{cv}/file",
                  f"/applications/export.csv?job_id={jid}"):
            self.assertEqual(r2.get(u).status_code, 404, u)
        self.assertEqual(r2.post(f"/applications/{aid}/transition", {"to": "rejected"}).status_code, 404)
        self.assertEqual(r2.post(f"/applications/{aid}/assessment").status_code, 404)
        self.assertEqual(r2.delete(f"/candidates/{cid}").status_code, 404)
        self.assertEqual(r2.patch(f"/jobs/{jid}", {"status": "closed"}).status_code, 404)
        self.assertEqual(r2.get("/candidates").json["total"], 0); self.assertEqual(r1.get("/candidates").json["total"], 1)
        self.assertEqual(r2.get("/jobs").json["total"], 0)

    def test_recruiter_cannot_delete_a_claimed_candidate(self):
        rec = self.recruiter(); jid = self.job(rec); c = self.ready_candidate()
        c.post(f"/jobs/{jid}/apply"); cid = c.get("/me/profile").json["id"]
        self.assertEqual(rec.delete(f"/candidates/{cid}").status_code, 403)

    def test_csrf_origin_and_cookie_flags(self):
        c = self.client()
        c.post("/auth/register/candidate", {"email": "a@example.com", "password": "correct-horse-9", "full_name": "Asha"})
        r = c.login("a@example.com")
        ck = r.headers["Set-Cookie"]
        self.assertIn("HttpOnly", ck); self.assertIn("SameSite=Strict", ck)
        good = c.csrf; c.csrf = None
        self.assertEqual(c.post("/auth/logout").status_code, 403)                         # cookie alone is not enough
        c.csrf = "wrong"; self.assertEqual(c.post("/auth/logout").status_code, 403)
        c.csrf = good
        self.assertEqual(c.post("/auth/logout", headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(c.post("/auth/logout", headers={"Origin": "http://localhost:5000"}).status_code, 200)
        self.assertEqual(c.get("/auth/me").status_code, 401)                               # session really gone

    def test_cors_only_for_allowed_origins(self):
        c = self.client()
        ok = c.get("/health", headers={"Origin": "http://localhost:5000"})
        self.assertEqual(ok.headers.get("Access-Control-Allow-Origin"), "http://localhost:5000")
        bad = c.get("/health", headers={"Origin": "https://evil.example"})
        self.assertIsNone(bad.headers.get("Access-Control-Allow-Origin"))
        self.assertEqual(ok.headers["Cache-Control"], "no-store")

    def test_security_headers_on_static_page(self):
        r = self.app.test_client().get("/")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_mass_assignment_and_input_validation(self):
        c = self.client()
        r = c.post("/auth/register/candidate", {"email": "a@example.com", "password": "correct-horse-9", "full_name": "A B", "role": "admin"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(c.post("/auth/register/candidate", {"email": "nope", "password": "correct-horse-9", "full_name": "A B"}).status_code, 422)
        self.assertEqual(c.post("/auth/register/candidate", {"email": "a@example.com", "password": "correct-horse-9", "full_name": "A" * 500}).status_code, 422)
        self.assertEqual(c.post("/auth/login", data="not json", content_type="application/json").status_code, 400)
        self.assertEqual(c.post("/auth/login", {"email": ["x"], "password": 1}).status_code, 422)

    def test_rate_limiting(self):
        self.cfg.rl_login = (3, 60)
        c = self.client()
        codes = [c.login("nobody@example.com", "x").status_code for _ in range(5)]
        self.assertEqual(codes[:3], [401] * 3); self.assertEqual(codes[3:], [429, 429])
        self.cfg.rl_upload = (2, 60)
        cand = self.candidate()
        self.assertEqual([self.upload(cand, b"junk").status_code for _ in range(3)], [422, 422, 429])

    def test_admin_cannot_change_own_status_and_audit_trail_is_complete(self):
        a = self.admin(); aid = self.ctx.db.scalar("SELECT id FROM users WHERE role='admin'")
        self.assertEqual(a.post(f"/admin/users/{aid}/status", {"status": "suspended"}).status_code, 400)
        rec = self.recruiter(); jid = self.job(rec); c = self.ready_candidate()
        app_id = c.post(f"/jobs/{jid}/apply").json["id"]; self.work()
        rec.post(f"/applications/{app_id}/transition", {"to": "rejected", "note": "n"})
        cid = c.get("/me/profile").json["id"]
        c.delete("/me", {"password": "correct-horse-9"})
        logs = a.get("/admin/audit-logs?limit=100").json["data"]
        actions = {l["action"] for l in logs}
        for need in ("auth.register", "auth.login", "admin.user_status", "job.create", "cv.upload", "cv.processed", "application.create",
                     "application.transition", "candidate.erased", "candidate.profile_update"):
            self.assertIn(need, actions)
        self.assertEqual(a.get(f"/admin/audit-logs?entity_type=application&entity_id={app_id}").json["total"] >= 3, True)
        blob = str(logs)
        self.assertNotIn("correct-horse-9", blob); self.assertNotIn("scrypt$", blob)
        erased = [l for l in logs if l["action"] == "candidate.erased"][0]
        self.assertEqual(erased["entity_id"], cid); self.assertNotIn("asha", str(erased).lower())    # erasure log keeps no personal data

    def test_zip_bomb_docx_rejected(self):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", "<x/>"); z.writestr("word/document.xml", b"0" * (35 * 1024 * 1024))
        self.assertLess(len(buf.getvalue()), 200_000)
        c = self.candidate()
        r = self.upload(c, buf.getvalue(), "cv.docx")
        self.assertEqual(r.json["files"][0]["error"]["code"], "too_large_expanded")

    def test_path_traversal_filename_is_neutralised(self):
        c = self.candidate()
        r = self.upload(c, make_pdf(cv_text()), "../../etc/passwd.pdf")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.ctx.db.scalar("SELECT original_name FROM cvs"), "passwd.pdf")
        self.assertRegex(self.ctx.db.scalar("SELECT storage_key FROM cvs"), r"^[0-9a-f]{32}\.pdf$")
