"""E-mail providers, engine labelling and the optional live local model. No message ever leaves the machine in these tests:
HTTP calls are captured, and the live-model test only runs when TB_TEST_OLLAMA=1 and Ollama is running."""
import io, json, os, shutil, tempfile, unittest, urllib.error, urllib.request
from .support import Base
from .test_local_engine import LocalBase
from . import fixtures as F
from app import mail, ai as ai_mod
from app.config import Config


def cfg(tmp, **kw):
    return Config(**{**Config().__dict__, "upload_dir": os.path.join(tmp, "uploads"), **kw})


class Capture:
    """Stands in for urllib.request.urlopen and records what would have been sent."""
    def __init__(self, status=200, body=b'{"id": "msg_123", "messageId": "<abc@brevo>"}'):
        self.calls, self.status, self.body = [], status, body

    def __call__(self, req, timeout=None):
        self.calls.append({"url": req.full_url, "headers": {k.lower(): v for k, v in req.header_items()}, "json": json.loads(req.data)})
        if self.status >= 400:
            raise urllib.error.HTTPError(req.full_url, self.status, "err", {}, io.BytesIO(b'{"message": "sender not verified"}'))
        return _Resp(self.body)


class _Resp:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self.body


class MailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.orig = urllib.request.urlopen

    def tearDown(self):
        urllib.request.urlopen = self.orig; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_is_the_file_outbox(self):
        m = mail.get_mailer(cfg(self.tmp))
        self.assertIsInstance(m, mail.FileMailer)
        self.assertFalse(m.describe()["real_delivery"])
        d = m.send("someone@example.org", "Hi", "Body")
        self.assertTrue(d.startswith("file:"))
        self.assertEqual(len(os.listdir(os.path.join(self.tmp, "outbox"))), 1)

    def test_resend_payload_and_allow_list(self):
        cap = Capture(); urllib.request.urlopen = cap
        m = mail.get_mailer(cfg(self.tmp, email_provider="resend", resend_api_key="re_test_key", email_from="onboarding@resend.dev",
                                email_allowed_recipients="owner@example.org,@school.example"))
        self.assertEqual(m.send("owner@example.org", "Test", "Body"), "resend:msg_123")
        self.assertEqual(cap.calls[0]["url"], "https://api.resend.com/emails")
        self.assertEqual(cap.calls[0]["headers"]["authorization"], "Bearer re_test_key")
        self.assertEqual(cap.calls[0]["json"]["to"], ["owner@example.org"])
        self.assertTrue(m.send("prof@school.example", "T", "B").startswith("resend:"))       # domain rule
        held = m.send("candidate@elsewhere.example", "T", "B")                              # not approved: never sent
        self.assertTrue(held.startswith("held:file:"))
        self.assertEqual(len(cap.calls), 2)
        self.assertNotIn("re_test_key", json.dumps(m.describe()))                           # no secret in status output

    def test_brevo_payload_and_rejection_is_not_retried(self):
        cap = Capture(); urllib.request.urlopen = cap
        m = mail.get_mailer(cfg(self.tmp, email_provider="brevo", brevo_api_key="xkeysib-test", email_from="me@example.org", email_allow_all=True))
        self.assertTrue(m.send("a@example.org", "S", "B").startswith("brevo:"))
        self.assertEqual(cap.calls[0]["headers"]["api-key"], "xkeysib-test")
        self.assertEqual(cap.calls[0]["json"]["sender"]["email"], "me@example.org")
        urllib.request.urlopen = Capture(status=401)
        with self.assertRaises(mail.MailError) as e:
            m.send("a@example.org", "S", "B")
        self.assertFalse(e.exception.retryable)
        self.assertIn("HTTP 401", e.exception.message)

    def test_missing_key_falls_back_and_says_so(self):
        m = mail.get_mailer(cfg(self.tmp, email_provider="resend", email_from="x@example.org"))
        self.assertIsInstance(m, mail.FileMailer)
        self.assertIn("missing its API key", m.describe()["note"])


class NotificationTests(Base):
    def test_registration_and_submission_emails_are_queued_and_sent(self):
        c = self.ready_candidate()
        rec = self.recruiter(); jid = self.job(rec)
        aid = c.post(f"/jobs/{jid}/apply").json["id"]; self.work()
        sid = rec.post(f"/applications/{aid}/assessment").json["id"]; self.work()
        rec.post(f"/assessments/{sid}/send"); self.work()
        c.post(f"/assessments/{sid}/start")
        qs = c.get(f"/assessments/{sid}").json["task"]["questions"]
        c.post(f"/assessments/{sid}/submit", {"answers": {q["id"]: "A complete answer with enough words to count." for q in qs}}); self.work()
        kinds = [r["kind"] for r in self.ctx.db.all("SELECT kind FROM email_outbox WHERE to_email='asha@example.com' ORDER BY created_at")]
        self.assertEqual(kinds, ["registered", "assessment_ready", "assessment_submitted"])
        self.assertEqual(len(self.mailer.sent), 3)
        self.assertTrue(all(r["status"] == "sent" for r in self.ctx.db.all("SELECT status FROM email_outbox")))


class EngineLabelTests(LocalBase):
    def test_rules_fallback_is_labelled_as_rules_not_ai(self):
        c = Config(**{**self.cfg.__dict__, "ai_provider": "ollama", "ollama_url": "http://127.0.0.1:9", "ollama_timeout": 1})
        ai = ai_mod.get_provider(c)
        task = ai_mod.generate_assessment(ai, {"skills": []}, F.JOBS["analyst"])
        self.assertEqual(task["engine"], "local-rules-v1 (AI model unavailable)")
        res = ai_mod.evaluate(ai, task, {q["id"]: F.STRONG_ANALYST_ANSWER for q in task["questions"]}, {}, F.JOBS["analyst"])
        self.assertTrue(res["engine"].startswith("local-rules-v1"))
        self.assertIn("model_unavailable_rules_used", res["flags"])
        self.assertNotIn("cross_check", res)

    def test_model_result_is_labelled_and_cross_checked(self):
        class Model:
            label = "ollama:test-model"
            def call(self, tool, description, schema, system, user):
                assert "never assume gender" in system
                if tool == "record_question_score":          # local models score one question per call
                    return {"score": 100, "rationale": "He gave a generous answer.", "evidence": ["a sentence never written"]}
                raise ai_mod.AIError("x", "unused", retryable=False)
        ai = ai_mod.HybridAI(Model(), __import__("app.local_ai", fromlist=["LocalAI"]).LocalAI(), ["evaluation"])
        from app.question_bank import build_assessment
        task = ai_mod.normalise_task(build_assessment({"skills": []}, F.JOBS["analyst"]))
        res = ai_mod.evaluate(ai, task, {q["id"]: F.WEAK_ANSWER for q in task["questions"]}, {}, F.JOBS["analyst"])
        self.assertEqual(res["engine"], "ollama:test-model")
        self.assertIn("cross_check", res)
        self.assertIn("ai_and_rules_disagree", res["flags"])                  # a generous model is caught by the rubric cross-check
        self.assertIn("model_score_rescaled", res["flags"])                   # "100" for a 25-point question is read as 100% and flagged
        self.assertIn("model_feedback_repeated", res["flags"])                # identical feedback for different questions
        self.assertIn("unverifiable_evidence_removed", res["flags"])          # invented quotes are dropped
        self.assertTrue(all(p["evidence"] == [] for p in res["per_question"]))
        self.assertTrue(all("They gave" in p["rationale"] for p in res["per_question"]))   # no assumed gender
        self.assertTrue(all(p["score"] <= p["max_points"] for p in res["per_question"]))

    def test_overlapping_model_questions_are_rejected(self):
        bad = {"questions": [{"prompt": "Write a SQL query to find the top five customers by revenue", "rubric": "joins"},
                             {"prompt": "Write a SQL query to find the top five customers by revenue please", "rubric": "joins"}]}
        with self.assertRaises(ai_mod.AIError):
            ai_mod.check_generated_task(bad)
        needs_data = {"questions": [{"prompt": "Using the provided sales data, find the region with the largest drop", "rubric": "finds it"},
                                    {"prompt": "Explain how you would present a finding to a manager who is not technical", "rubric": "clear"}]}
        with self.assertRaises(ai_mod.AIError):
            ai_mod.check_generated_task(needs_data)


@unittest.skipUnless(os.getenv("TB_TEST_OLLAMA") == "1", "set TB_TEST_OLLAMA=1 (and run Ollama) to test the real local model")
class LiveOllamaTests(unittest.TestCase):
    def test_real_model_analysis_questions_and_scoring(self):
        from app.cv_parser import parse_cv
        from app.profile import normalise
        c = Config(ai_provider="ollama", ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"), ollama_tasks="profile,summary,assessment,evaluation")
        ai = ai_mod.get_provider(c)
        st = ai_mod.model_status(ai)
        self.assertTrue(st["reachable"] and st["installed"], st)
        read = ai_mod.extract_profile(ai, F.KIRAN)
        self.assertTrue(read["extracted_by"].startswith("local-rules-v1"), read["extracted_by"])
        self.assertNotIn("unavailable", read["extracted_by"])
        prof, job = normalise(parse_cv(F.KIRAN)), F.JOBS["analyst"]
        an = ai_mod.analyse_application(ai, prof, job)
        self.assertEqual(an["engine"], "ollama:" + c.ollama_model)
        task = ai_mod.generate_assessment(ai, prof, job)
        ans = {q["id"]: F.STRONG_ANALYST_ANSWER for q in task["questions"]}
        res = ai_mod.evaluate(ai, task, ans, prof, job)
        self.assertTrue(res["engine"].startswith("ollama:") or "AI model unavailable" in res["engine"])
        self.assertTrue(0 <= res["overall"] <= 100)
        for p in res["per_question"]:
            for e in p["evidence"]:
                self.assertIn(" ".join(e.lower().split()), " ".join(ans[p["question_id"]].lower().split()))   # quotes are real


if __name__ == "__main__":
    unittest.main()
