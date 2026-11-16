"""Regression tests for the October 2026 stabilisation: candidate identity and CV ownership, assessment persistence and
scoring states, CV parsing, match consistency, recruiter workflow and error handling (scenarios A-E of the brief).
Every person here is fictional. Nothing in production code knows these names or expected scores."""
import io, json, unittest
from .support import Client
from .test_local_engine import LocalBase
from . import fixtures as F
from app import create_app, pipeline as pl, ai as ai_mod
from app.ai import AIError
from app.cv_parser import parse_cv
from app.profile import normalise
from app.matching import compute_match
from app.question_bank import build_assessment, overlaps

# Layout features that broke the old parser: an undated role, a '|' header with "Remote", "Bachelor of Arts", certificates
# run together, combined headings and bullets that wrap onto a second line.
UNDATED = F.KIRAN
HEADINGS = """NEHA BANSAL
neha.bansal@example.org | +91 9000022222
WORK EXPERIENCE
Social Media Executive | Kite Media Pvt Ltd | Apr 2021 – Present
• Managed campaigns across Instagram and LinkedIn for three brands, handling customer queries,
generate leads, and drive conversions for the sales team.
• Reported monthly results to the founders.
TOOLS & TECHNOLOGY
Google Analytics, HubSpot, Canva
EDUCATION & LANGUAGES
Bachelor of Commerce, University of Mumbai, 2020
English, Hindi
"""
ANS = ["DISTINCT-ALPHA: First I would profile the slow endpoint with logs and timing, check the query plan, add an index and pagination, then cache results and add a regression test before deploying with monitoring.",
       "DISTINCT-BRAVO: I would talk to my teammate, review the diff, resolve the merge conflict carefully, run the tests and the build to verify, and keep small commits with clear commit messages on a feature branch.",
       "DISTINCT-CHARLIE: In my project I was responsible for the analysis. I used SQL to join tables and aggregate results, delivered a report that reduced manual work by 20%, and next time I would document it better.",
       "DISTINCT-DELTA: I would first clarify the requirements and scope with stakeholders, then plan the steps, build it with python and sql, test and validate the results, and report a summary with a recommendation."]


class Helpers(LocalBase):
    def setUp(self):
        super().setUp()
        self.rec = self.recruiter()
        self.jid = self.jobs(self.rec)

    def applicant(self, text, email, name, job="analyst"):
        c = self.candidate_with(text, email, name)
        return c, self.apply_and_get(c, self.jid[job])

    def started(self, c, aid):
        sid = next(a["open_assessment_id"] for a in c.get("/me/applications").json["data"] if a["id"] == aid)
        self.assertEqual(c.post(f"/assessments/{sid}/start").status_code, 200)
        return sid, c.get(f"/assessments/{sid}").json["task"]["questions"]


# ------------------------------------------------------------------ Scenario A: identities, ownership, privacy
class IdentityTests(Helpers):
    def test_someone_elses_cv_is_held_and_never_applied(self):
        c = self.candidate("asha@example.com", "Asha Verma")
        self.upload(c, F.make_pdf(F.PRIYA)); self.work()
        p = c.get("/me/profile").json
        cv = p["cvs"][0]
        self.assertEqual(cv["identity_status"], "mismatch")
        self.assertIn("Priya Nair", cv["identity"]["reason"])
        self.assertIsNone(p["profile"])                                   # nothing of Priya's became Asha's profile
        self.assertEqual(p["full_name"], "Asha Verma"); self.assertIsNone(p["phone"])
        self.assertEqual(c.patch("/me/profile", {"confirm": True}).status_code, 409)
        self.assertEqual(c.post(f"/jobs/{self.jid['analyst']}/apply").status_code, 409)

    def test_owner_can_confirm_a_flagged_cv_and_it_is_audited(self):
        c = self.candidate("asha@example.com", "Asha Verma")
        self.upload(c, F.make_pdf(F.PRIYA)); self.work()
        cv = c.get("/me/profile").json["cvs"][0]
        self.assertEqual(c.post(f"/me/cvs/{cv['id']}/use", {}).status_code, 409)             # needs explicit confirmation
        r = c.post(f"/me/cvs/{cv['id']}/use", {"confirm_mine": True})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json["cvs"][0]["identity_status"], "confirmed")
        self.assertTrue(self.ctx.db.one("SELECT 1 AS x FROM activity_logs WHERE action='cv.identity_confirmed' AND entity_id=?", (cv["id"],)))

    def test_three_people_keep_their_own_identity_contact_and_cv(self):
        people = [(F.PRIYA, "p@example.com", "Priya Nair", "+91 98200 11122"), (F.ROHAN, "r@example.com", "Rohan Mehta", "+91 99876 54321"),
                  (F.MEERA, "m@example.com", "Meera Kapoor", "+91 91234 56780")]
        apps = {}
        for text, email, name, phone in people:
            c, aid = self.applicant(text, email, name)
            prof = c.get("/me/profile").json
            self.assertEqual((prof["full_name"], prof["email"], prof["phone"]), (name, email, phone))
            self.assertEqual(len(prof["cvs"]), 1)
            apps[aid] = (name, email, prof["cvs"][0]["id"])
        lst = self.rec.get(f"/jobs/{self.jid['analyst']}/applications").json["data"]
        self.assertEqual({a["id"]: (a["full_name"], a["email"]) for a in lst}, {k: v[:2] for k, v in apps.items()})
        pool = {c["full_name"]: c for c in self.rec.get("/candidates").json["data"]}
        self.assertEqual(set(pool), {"Priya Nair", "Rohan Mehta", "Meera Kapoor"})
        self.assertTrue(all(c["applications"] == 1 for c in pool.values()))
        for aid, (name, email, cv_id) in apps.items():
            d = self.rec.get(f"/applications/{aid}").json
            self.assertEqual((d["candidate"]["full_name"], d["candidate"]["email"], d["cv"]["id"]), (name, email, cv_id))
            cand = self.rec.get(f"/candidates/{d['candidate']['id']}").json
            self.assertEqual([x["id"] for x in cand["cvs"]], [cv_id])          # only that person's CV, nobody else's

    def test_new_cv_or_profile_edit_does_not_change_a_submitted_application(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        before = self.rec.get(f"/applications/{aid}").json
        self.upload(c, F.make_pdf(F.PRIYA.replace("Tableau", "Tableau, Looker"))); self.work()
        c.patch("/me/profile", {"phone": "+91 90000 00000"})
        after = self.rec.get(f"/applications/{aid}").json
        self.assertEqual(after["cv"]["id"], before["cv"]["id"])
        self.assertEqual(after["profile"], before["profile"])
        self.assertEqual(after["match"]["score"], before["match"]["score"])

    def test_recruiter_moves_a_misfiled_cv_with_its_application_and_assessment(self):
        c = self.candidate("asha@example.com", "Asha Verma")
        self.upload(c, F.make_pdf(F.PRIYA)); self.work()
        cv = c.get("/me/profile").json["cvs"][0]
        c.post(f"/me/cvs/{cv['id']}/use", {"confirm_mine": True}); c.patch("/me/profile", {"confirm": True})
        aid = self.apply_and_get(c, self.jid["analyst"])
        self.take_test(c, aid, [F.STRONG_ANALYST_ANSWER])
        score = self.ctx.db.scalar("SELECT match_score FROM applications WHERE id=?", (aid,))
        # legacy data: the CV was attached to the wrong account (what the old version allowed silently)
        self.ctx.db.execute("UPDATE cvs SET identity_status='mismatch' WHERE id=?", (cv["id"],))
        r = self.rec.post(f"/cvs/{cv['id']}/reassign", {})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json["applications_moved"], [aid])
        d = self.rec.get(f"/applications/{aid}").json
        self.assertEqual((d["candidate"]["full_name"], d["candidate"]["email"]), ("Priya Nair", "priya.nair@example.com"))
        self.assertEqual(d["assessments"][0]["status"], "evaluated")                  # assessment, answers and result moved with it
        self.assertTrue(d["assessments"][0]["answers"])
        self.assertEqual(c.get(f"/me/applications/{aid}").status_code, 404)           # Asha no longer sees Priya's application
        self.assertEqual(c.get(f"/cvs/{cv['id']}/file").status_code, 404)
        self.assertEqual(self.ctx.db.scalar("SELECT match_score FROM applications WHERE id=?", (aid,)), score)

    def test_candidates_cannot_reach_each_others_data_by_direct_url(self):
        a, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        b, bid = self.applicant(F.ROHAN, "r@example.com", "Rohan Mehta")
        sid, _ = self.started(a, aid)
        a_cv = a.get("/me/profile").json["cvs"][0]["id"]
        for url in (f"/cvs/{a_cv}/file", f"/cvs/{a_cv}/text", f"/cvs/{a_cv}", f"/me/applications/{aid}", f"/assessments/{sid}"):
            self.assertEqual(b.get(url).status_code, 404, url)
        self.assertEqual(b.put(f"/assessments/{sid}/draft", {"answers": {"q1": "x"}}).status_code, 404)
        self.assertEqual(b.post(f"/me/cvs/{a_cv}/use", {}).status_code, 404)
        self.assertEqual(b.get("/candidates").status_code, 403)
        self.assertEqual(b.get(f"/applications/{aid}").status_code, 403)
        self.assertEqual(self.client().get(f"/cvs/{a_cv}/file").status_code, 401)

    def test_recruiters_only_see_cvs_used_for_their_own_organisation(self):
        other = self.recruiter("o@other.test", "Other Org")
        ojob = self.job(other, title="Analyst at other org")
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        first_cv = c.get("/me/profile").json["cvs"][0]["id"]
        self.upload(c, F.make_pdf(F.PRIYA.replace("Pune", "Mumbai"))); self.work(); c.patch("/me/profile", {"confirm": True})
        oid = self.apply_and_get(c, ojob)
        second_cv = self.ctx.db.scalar("SELECT cv_id FROM applications WHERE id=?", (oid,))
        self.assertNotEqual(first_cv, second_cv)
        self.assertEqual(self.rec.get(f"/cvs/{first_cv}/file").status_code, 200)
        self.assertEqual(self.rec.get(f"/cvs/{second_cv}/file").status_code, 404)        # used only for the other organisation
        self.assertEqual(other.get(f"/cvs/{first_cv}/text").status_code, 404)
        self.assertEqual(other.get(f"/applications/{aid}").status_code, 404)
        cid = self.ctx.db.scalar("SELECT candidate_id FROM applications WHERE id=?", (aid,))
        self.assertEqual([x["id"] for x in self.rec.get(f"/candidates/{cid}").json["cvs"]], [first_cv])
        self.assertEqual(self.rec.get(f"/applications/export.csv?job_id={ojob}").status_code, 404)


# ------------------------------------------------------------------ Scenario B: drafts, submission, scoring states
class AssessmentTests(Helpers):
    def test_draft_restored_exactly_submitted_answers_scored_and_shown_to_recruiter_after_restart(self):
        c, aid = self.applicant(F.ROHAN, "r@example.com", "Rohan Mehta", job="backend")
        sid, qs = self.started(c, aid)
        draft = {qs[0]["id"]: "A distinctive draft — with ünïcode, line\nbreaks and  double  spaces."}
        r = c.put(f"/assessments/{sid}/draft", {"answers": draft}); self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(c.get(f"/assessments/{sid}").json["answers"], draft)              # 'navigate away and reopen'
        final = {q["id"]: ANS[i] for i, q in enumerate(qs)}
        self.assertEqual(c.post(f"/assessments/{sid}/submit", {"answers": final}).status_code, 200)
        self.assertEqual(json.loads(self.ctx.db.scalar("SELECT answers FROM assessment_responses WHERE assessment_id=?", (sid,))), final)
        self.work()
        ev = json.loads(self.ctx.db.scalar("SELECT result FROM evaluations WHERE assessment_id=?", (sid,)))
        self.assertEqual([p["answer_status"] for p in ev["per_question"]], ["scored"] * 4)
        self.assertEqual(ev["scorable_answers"], 4)
        self.assertGreater(ev["overall"], 0)
        for q, p in zip(qs, ev["per_question"]):
            self.assertEqual(p["question_id"], q["id"])
        self.ctx.db.close()
        app2 = create_app(self.cfg, mailer=self.mailer); self.ctx = app2.ctx
        r2 = Client(app2); r2.login("rec@acme.test")
        d = r2.get(f"/applications/{aid}").json
        a = d["assessments"][0]
        self.assertEqual(a["answers"], final)                                            # the same text, keyed to the same questions
        self.assertEqual(a["state"]["code"], "scored")
        self.assertEqual(d["status"], "ai_evaluated")
        self.assertEqual((d["candidate"]["full_name"], d["cv"]["original_name"]), ("Rohan Mehta", "cv.pdf"))
        self.assertEqual(d["match"]["assessment"], ev["overall"])

    def test_late_autosave_cannot_overwrite_submitted_answers(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        sid, qs = self.started(c, aid)
        final = {q["id"]: ANS[i] for i, q in enumerate(qs)}
        c.post(f"/assessments/{sid}/submit", {"answers": final})
        self.assertEqual(c.put(f"/assessments/{sid}/draft", {"answers": {qs[0]["id"]: "stale"}}).status_code, 409)
        self.assertEqual(json.loads(self.ctx.db.scalar("SELECT answers FROM assessment_responses WHERE assessment_id=?", (sid,))), final)

    def test_repeated_submission_is_idempotent(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        sid, qs = self.started(c, aid)
        final = {q["id"]: ANS[i] for i, q in enumerate(qs)}
        self.assertEqual(c.post(f"/assessments/{sid}/submit", {"answers": final}).status_code, 200)
        r = c.post(f"/assessments/{sid}/submit", {"answers": final})
        self.assertEqual((r.status_code, r.json.get("already_submitted")), (200, True))
        self.assertEqual(c.post(f"/assessments/{sid}/submit", {"answers": {**final, qs[0]["id"]: "changed"}}).status_code, 409)
        self.assertEqual(self.ctx.db.scalar("SELECT COUNT(*) FROM task_queue WHERE kind='evaluate_assessment'"), 1)
        self.work(); self.work()
        self.assertEqual(self.ctx.db.scalar("SELECT COUNT(*) FROM evaluations WHERE assessment_id=?", (sid,)), 1)

    def test_blank_and_too_short_answers_are_labelled_not_scored_as_poor(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        sid, qs = self.started(c, aid)
        c.post(f"/assessments/{sid}/submit", {"answers": {qs[0]["id"]: "", qs[1]["id"]: "almxnxk", qs[2]["id"]: "xhwhiw sjdniw", qs[3]["id"]: "wsdhiwjd"}})
        self.work()
        ev = c.get(f"/me/applications/{aid}").json["evaluation"]
        self.assertEqual([p["answer_status"] for p in ev["per_question"]], ["blank", "too_short", "too_short", "too_short"])
        self.assertEqual(ev["per_question"][1]["answer"], "almxnxk")                     # the submitted text is shown, not 'empty'
        self.assertIn("No answer was given", ev["per_question"][0]["rationale"])
        self.assertIn("Too short to score", ev["per_question"][1]["rationale"])
        self.assertEqual(ev["scorable_answers"], 0)
        self.assertIn("no_scorable_answers", ev["flags"])
        d = self.rec.get(f"/applications/{aid}").json
        self.assertEqual(d["assessments"][0]["state"]["code"], "needs_review")

    def test_scoring_failure_keeps_answers_and_never_becomes_zero(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        sid, qs = self.started(c, aid)
        final = {q["id"]: ANS[i] for i, q in enumerate(qs)}
        real = ai_mod.evaluate
        def broken(*a, **k): raise AIError("engine_down", "Scoring engine unavailable.", retryable=False)
        ai_mod.evaluate = broken
        try:
            c.post(f"/assessments/{sid}/submit", {"answers": final}); self.work()
        finally:
            ai_mod.evaluate = real
        self.assertIsNone(self.ctx.db.one("SELECT 1 AS x FROM evaluations WHERE assessment_id=?", (sid,)))
        d = self.rec.get(f"/applications/{aid}").json
        a = d["assessments"][0]
        self.assertEqual((a["status"], a["eval_status"], a["state"]["code"]), ("submitted", "failed", "needs_review"))
        self.assertEqual(a["answers"], final)
        self.assertIsNone(d["match"]["assessment"])                                       # no fake 0 in the match
        self.assertIn("human_review", d["allowed_next"])
        self.assertEqual(self.rec.post(f"/assessments/{sid}/rescore").status_code, 202)
        self.work()
        self.assertEqual(self.rec.get(f"/applications/{aid}").json["assessments"][0]["state"]["code"], "scored")

    def test_scoring_interrupted_by_a_restart_is_resumed(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        sid, qs = self.started(c, aid)
        c.post(f"/assessments/{sid}/submit", {"answers": {q["id"]: ANS[i] for i, q in enumerate(qs)}})
        self.ctx.db.execute("UPDATE task_queue SET status='running', locked_at=? WHERE kind='evaluate_assessment'", (pl.now(),))
        self.ctx.db.execute("UPDATE assessments SET eval_status='scoring' WHERE id=?", (sid,))
        self.work()                                                                       # stuck: the 'running' task is not picked up
        self.assertEqual(self.ctx.db.scalar("SELECT status FROM assessments WHERE id=?", (sid,)), "submitted")
        self.assertEqual(pl.recover_interrupted(self.ctx), 1)                             # what start-up does in single-process mode
        self.work()
        self.assertEqual(self.ctx.db.scalar("SELECT status FROM assessments WHERE id=?", (sid,)), "evaluated")

    def test_retake_keeps_the_previous_attempt(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        sid = self.take_test(c, aid, [F.WEAK_ANSWER])
        r = self.rec.post(f"/assessments/{sid}/retake"); self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(self.rec.post(f"/assessments/{r.json['id']}/send").status_code, 200)
        d = self.rec.get(f"/applications/{aid}").json
        self.assertEqual([a["attempt"] for a in d["assessments"]], [1, 2])
        self.assertIsNotNone(d["assessments"][0]["evaluation"])
        self.assertEqual(d["status"], "assessment_sent")

    def test_questions_cover_distinct_competencies(self):
        for text in (F.PRIYA, F.ROHAN, F.MEERA, UNDATED):
            p = normalise(parse_cv(text))
            for job in F.JOBS.values():
                prompts = [q["prompt"] for q in build_assessment(p, job)["questions"]]
                for i, a in enumerate(prompts):
                    self.assertFalse(overlaps(a, prompts[:i] + prompts[i + 1:], 0.6), (job["title"], a[:80]))


# ------------------------------------------------------------------ Scenario C: parsing and matching
class ParsingAndMatchingTests(Helpers):
    def test_undated_role_is_kept_with_unknown_dates_and_a_warning(self):
        p = normalise(parse_cv(UNDATED))
        self.assertEqual((p["full_name"], p["email"], p["phone"]), ("Kiran Desai", "kiran.desai@example.org", "+91 9000011111"))
        self.assertEqual(len(p["work_history"]), 1)
        w = p["work_history"][0]
        self.assertEqual((w["start"], w["end"]), ("unknown", "unknown"))
        self.assertNotIn("Remote", w["company"])
        self.assertEqual(len(w["achievements"]), 2)
        self.assertEqual(w["title"], "Freelance Research & Administrative Support")
        self.assertTrue(any("no readable dates" in g for g in p["gaps"]))
        self.assertTrue(any("certifications may have run together" in g.lower() for g in p["gaps"]))
        self.assertEqual(p["education"][0]["degree"], "Bachelor of Arts (BA)")
        self.assertEqual(p["education"][0]["field"], "Economics & Statistics")
        from app.profile import summary_fields
        self.assertIsNone(summary_fields(p)[0])                                         # unknown, not 0 years

    def test_combined_headings_and_wrapped_bullets(self):
        p = normalise(parse_cv(HEADINGS))
        self.assertEqual(len(p["work_history"]), 1)
        w = p["work_history"][0]
        self.assertNotIn("HubSpot", w["description"])                                   # TOOLS & TECHNOLOGY is a section, not part of the job
        self.assertTrue(w["achievements"][0].endswith("for the sales team."))
        self.assertEqual(p["education"][0]["degree"], "Bachelor of Commerce (BCom)")
        self.assertEqual(p["certifications"], [])
        self.assertIn("Google Analytics", [s["name"] for s in p["skills"]])

    def test_certificate_alone_does_not_count_as_shown_in_use(self):
        p = normalise(parse_cv("Ravi Iyer\nravi@example.org\nExperience\nClerk | City Office | 2019 - 2021\n• Filed records.\nCertifications\nGoogle Analytics Certificate, 2022\n"))
        s = next(x for x in p["skills"] if x["name"] == "Google Analytics")
        self.assertEqual(s["level"], "listed")
        m = compute_match(p, {"required_skills": ["Google Analytics"], "min_years": 0, "education_level": "none"})
        self.assertEqual(m["skills"][0]["status"], "partial")

    def test_missing_dates_do_not_get_experience_credit_and_say_why(self):
        p = normalise(parse_cv(UNDATED))
        m = compute_match(p, {"required_skills": ["Excel"], "min_years": 2, "education_level": "bachelor"})
        self.assertEqual((m["components"]["experience"]["score"], m["experience"]["status"]), (0.0, "unverified"))
        none = compute_match({"skills": [], "work_history": [], "education": []}, {"required_skills": ["Excel"], "min_years": 2, "education_level": "bachelor"})
        self.assertEqual(none["experience"]["status"], "missing")
        self.assertEqual(none["skills"][0]["status"], "unknown")                        # nothing parsed: no conclusion either way
        self.assertIn("does not prove", compute_match(p, {"required_skills": ["Kubernetes"], "min_years": 0})["skills"][0]["evidence"])

    def test_same_score_everywhere_and_documented_formula(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        preview = c.get(f"/me/match/{self.jid['analyst']}").json
        mine = c.get(f"/me/applications/{aid}").json["match"]
        rec = self.rec.get(f"/applications/{aid}").json["match"]
        row = next(a for a in self.rec.get(f"/jobs/{self.jid['analyst']}/applications").json["data"] if a["id"] == aid)
        self.assertEqual(len({preview["cv_score"], mine["cv_score"], rec["cv_score"], row["cv_match_score"]}), 1)
        self.assertEqual(len({preview["score"], mine["score"], rec["score"], row["match_score"]}), 1)
        sid = self.take_test(c, aid, [F.STRONG_ANALYST_ANSWER])
        rec = self.rec.get(f"/applications/{aid}").json["match"]
        a = self.ctx.db.scalar("SELECT overall FROM evaluations WHERE assessment_id=?", (sid,))
        self.assertAlmostEqual(rec["score"], round(0.8 * rec["cv_score"] + 0.2 * a, 1), places=1)
        self.assertEqual(rec["scoring_version"], "match-v2")
        csv_ = self.rec.get(f"/applications/export.csv?job_id={self.jid['analyst']}").data.decode()
        self.assertIn(str(rec["score"]), csv_); self.assertIn(str(rec["cv_score"]), csv_)
        hist = self.ctx.db.all("SELECT score, reason FROM match_history WHERE application_id=?", (aid,))
        self.assertTrue(any(h["reason"] == "assessment scored" for h in hist))           # the CV-only result was kept, not overwritten

    def test_password_protected_pdf_is_explained(self):
        from reportlab.pdfgen import canvas
        buf = io.BytesIO(); cv = canvas.Canvas(buf, encrypt="secret-123")
        cv.drawString(50, 800, "Protected Person " * 20); cv.showPage(); cv.save()
        c = self.candidate()
        self.upload(c, buf.getvalue()); self.work()
        x = c.get("/me/profile").json["cvs"][0]
        self.assertEqual((x["stage"], x["error_code"]), ("failed", "password_protected"))


# ------------------------------------------------------------------ Scenario D: recruiter decisions and job lifecycle
class RecruiterWorkflowTests(Helpers):
    def test_decision_and_note_persist_with_history_and_counts(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        self.take_test(c, aid, [F.STRONG_ANALYST_ANSWER])
        self.assertEqual(self.rec.post(f"/applications/{aid}/transition", {"to": "human_review", "note": "Read all four answers."}).status_code, 200)
        r = self.rec.post(f"/applications/{aid}/review", {"note": "Strong SQL reasoning; invite to interview.", "decision": "shortlisted"})
        self.assertEqual(r.status_code, 200, r.json)
        self.ctx.db.close()
        app2 = create_app(self.cfg, mailer=self.mailer); self.ctx = app2.ctx
        r2 = Client(app2); r2.login("rec@acme.test")
        d = r2.get(f"/applications/{aid}").json
        self.assertEqual(d["status"], "shortlisted")
        self.assertEqual(d["reviews"][-1]["note"], "Strong SQL reasoning; invite to interview.")
        self.assertEqual(d["reviews"][-1]["reviewer"], "Rita Rao")
        moves = [(t["detail"] or {}).get("to") for t in d["timeline"] if t["action"] == "application.transition"]
        self.assertEqual(moves[-2:], ["human_review", "shortlisted"])
        self.assertIn("Read all four answers.", [(t["detail"] or {}).get("note") for t in d["timeline"]])
        self.assertTrue(any(t["action"] == "assessment.scored" for t in d["timeline"]))
        s = r2.get("/dashboard/summary").json["applications"]
        self.assertEqual(s["by_stage"].get("shortlisted"), 1)
        self.assertEqual(s["assessed"], 1)
        self.assertEqual(r2.get("/me/applications").status_code, 403)
        self.assertEqual(c.get(f"/me/applications/{aid}").json["status_label"], "Shortlisted")
        self.assertEqual(r2.post(f"/applications/{aid}/transition", {"to": "offer"}).status_code, 409)   # must go through interview

    def test_job_publish_close_reopen(self):
        jid = self.job(self.rec, title="Draft role", status="draft")
        c = self.candidate_with(F.PRIYA, "p@example.com", "Priya Nair")
        self.assertNotIn(jid, [j["id"] for j in c.get("/jobs").json["data"]])
        self.assertEqual(c.post(f"/jobs/{jid}/apply").status_code, 404)
        self.rec.patch(f"/jobs/{jid}", {"status": "open"})
        self.assertIn(jid, [j["id"] for j in c.get("/jobs").json["data"]])
        self.rec.patch(f"/jobs/{jid}", {"status": "closed"})
        self.assertEqual(c.post(f"/jobs/{jid}/apply").status_code, 404)
        self.rec.patch(f"/jobs/{jid}", {"status": "open"})
        self.assertEqual(c.post(f"/jobs/{jid}/apply").status_code, 201)

    def test_jobs_and_competitions_are_separate_sections(self):
        c = self.candidate_with(F.PRIYA, "p@example.com", "Priya Nair")
        comps = c.get("/jobs?kind=competition").json["data"]
        jobs = c.get("/jobs?kind=job").json["data"]
        self.assertEqual({x["kind"] for x in comps}, {"competition"}); self.assertTrue(comps)
        self.assertEqual({x["kind"] for x in jobs}, {"job"})
        self.assertEqual(len(comps) + len(jobs), c.get("/jobs").json["total"])
        self.assertEqual(c.post(f"/jobs/{comps[0]['id']}/apply").status_code, 201)       # entering a competition uses the same flow

    def test_csv_export_rows_are_the_right_people(self):
        _, a1 = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        _, a2 = self.applicant(F.ROHAN, "r@example.com", "Rohan Mehta")
        import csv
        rows = list(csv.DictReader(io.StringIO(self.rec.get(f"/applications/export.csv?job_id={self.jid['analyst']}").data.decode())))
        got = {r["Application ID"]: (r["Name"], r["Email"], r["CV used"]) for r in rows}
        self.assertEqual(got, {a1: ("Priya Nair", "p@example.com", "cv.pdf"), a2: ("Rohan Mehta", "r@example.com", "cv.pdf")})


# ------------------------------------------------------------------ Scenario E: errors and recovery
class ErrorTests(Helpers):
    def test_bad_inputs_get_clear_errors(self):
        c = self.candidate()
        bad_docx = io.BytesIO()
        import zipfile
        with zipfile.ZipFile(bad_docx, "w") as z: z.writestr("hello.txt", "not a word file")
        r = self.upload(c, bad_docx.getvalue(), "cv.docx")
        self.assertEqual(r.status_code, 422); self.assertEqual(r.json["files"][0]["error"]["code"], "unsupported_type")
        self.assertEqual(self.upload(c, b"%PDF-1.4 broken", "cv.docx").json["files"][0]["error"]["code"], "extension_mismatch")
        self.assertEqual(self.rec.post("/jobs", {"description": "x"}).status_code, 422)          # title missing
        self.assertEqual(self.rec.post("/jobs", data="{not json", content_type="application/json").status_code, 400)
        self.assertEqual(c.post(f"/jobs/{self.jid['analyst']}/apply").status_code, 409)         # no profile yet
        self.assertEqual(c.post("/assessments/does-not-exist/submit", {"answers": {}}).status_code, 404)

    def test_answers_must_match_the_questions(self):
        c, aid = self.applicant(F.PRIYA, "p@example.com", "Priya Nair")
        sid, qs = self.started(c, aid)
        self.assertEqual(c.put(f"/assessments/{sid}/draft", {"answers": {"q99": "x"}}).status_code, 422)
        self.assertEqual(c.post(f"/assessments/{sid}/submit", {"answers": {q["id"]: "" for q in qs}}).status_code, 422)
        self.assertEqual(c.post(f"/assessments/{sid}/submit", {"answers": {qs[0]["id"]: "x" * 8001}}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
