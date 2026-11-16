"""AI and reading upgrades: OCR for scanned CVs, two-column PDFs, the OpenAI-compatible and Anthropic providers, AI-assisted
CV reading with verification, question-writing retries, error checks in scoring, non-answer detection, synonyms and
embeddings. Model servers are local stand-ins (no network, nothing paid). All people are fictional."""
import io, json, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from .support import Base
from .test_local_engine import LocalBase
from . import fixtures as F
from app import ai as ai_mod, ocr, similarity, extract
from app.answer_scorer import score_answers, non_answer_reason
from app.assist import merge_verified
from app.config import Config
from app.cv_parser import parse_cv
from app.local_ai import LocalAI
from app.question_bank import build_assessment


class FakeServer:
    """A tiny HTTP server that answers like an AI server. `handler(path, body) -> (status, dict)`."""
    def __init__(self, handler):
        self.calls = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _go(self, body):
                outer.calls.append((self.path, body))
                status, out = handler(self.path, body)
                data = json.dumps(out).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

            def do_POST(self):
                self._go(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"))

            def do_GET(self):
                self._go(None)

            def log_message(self, *a):
                pass
        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}"

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


def chat(content):
    return {"choices": [{"message": {"content": content if isinstance(content, str) else json.dumps(content)}}]}


def scanned_cv_pdf(text):
    """A real image-only PDF: the CV is printed, rasterised, and saved as pictures with no text layer."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(F.make_pdf(text))
    imgs = [pdf[i].render(scale=150 / 72).to_pil().convert("L") for i in range(len(pdf))]
    pdf.close()
    buf = io.BytesIO()
    imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:], resolution=150)
    return buf.getvalue()


def two_column_pdf():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setFont("Helvetica-Bold", 16); c.drawString(50, 800, "Anika Rao")
    c.setFont("Helvetica", 10); c.drawString(50, 784, "anika.rao@example.com | +91 98000 12345 | Bengaluru, India")
    left = ["SKILLS", "SQL", "Tableau", "Python", "Excel", "", "LANGUAGES", "English (Fluent)", "Kannada (Native)", "", "EDUCATION",
            "B.Sc. Statistics", "Christ University", "2019"] + [""] * 4 + ["CERTIFICATIONS", "Tableau Desktop Specialist"]
    right = ["EXPERIENCE", "Data Analyst | Nimbus Retail | Jan 2021 - Present",
             "- Built Tableau dashboards for twelve regional sales teams.", "- Wrote SQL queries to reconcile weekly inventory.",
             "- Automated a monthly Excel report with Python scripts.", "", "Junior Analyst | Pebble Foods | Jun 2019 - Dec 2020",
             "- Cleaned survey data and presented findings to managers.", "- Maintained pivot tables for the finance team.",
             "", "PROJECTS", "Churn analysis - modelled churn drivers with Python.", "Store dashboard - compared footfall across stores."]
    for i, line in enumerate(left):
        c.drawString(50, 750 - i * 15, line)
    for i, line in enumerate(right):
        c.drawString(230, 750 - i * 15, line)
    c.showPage(); c.save()
    return buf.getvalue()


class ReadingTests(LocalBase):
    def test_two_column_pdf_is_read_column_by_column(self):
        txt = extract.pdf_text(two_column_pdf(), 15)
        self.assertIn("Built Tableau dashboards for twelve regional sales teams.", txt)      # right column lines stay whole
        self.assertLess(txt.index("SKILLS"), txt.index("LANGUAGES"))
        self.assertNotIn("SQL Data Analyst", txt)                                           # no left/right interleaving
        prof = parse_cv(txt)
        self.assertEqual(prof["full_name"], "Anika Rao")
        self.assertEqual({w["company"] for w in prof["work_history"]} >= {"Nimbus Retail", "Pebble Foods"}, True, prof["work_history"])
        self.assertTrue(any(e["institution"] == "Christ University" for e in prof["education"]), prof["education"])

    def test_single_column_pdf_unchanged(self):
        self.assertIsNone(extract.find_gutter([{"x0": 50, "x1": 540, "top": i * 14, "bottom": i * 14 + 10} for i in range(60)], 595, 842))

    def test_ocr_off_gives_a_clear_message(self):
        cfg = Config(**{**self.cfg.__dict__, "ocr": "off"})
        with self.assertRaises(extract.ExtractionError) as e:
            extract.extract_document(scanned_cv_pdf(F.PRIYA), "pdf", cfg)
        self.assertEqual(e.exception.code, "no_text_layer")
        self.assertIn("Tesseract", e.exception.message)

    @unittest.skipUnless(ocr.engine(Config()), "no OCR engine installed (install Tesseract)")
    def test_scanned_cv_is_read_with_ocr_and_labelled(self):
        c = self.candidate("priya@example.com", "Priya Nair")
        self.assertEqual(self.upload(c, scanned_cv_pdf(F.PRIYA), "scan.pdf").status_code, 201)
        self.work()
        p = c.get("/me/profile").json
        self.assertEqual(p["cvs"][0]["stage"], "ready", p["cvs"])
        prof = p["profile"]
        self.assertTrue(prof["text_source"].startswith("ocr:"))
        self.assertIn("OCR", prof["gaps"][0])
        self.assertEqual(prof["full_name"], "Priya Nair")
        self.assertTrue(any(s["name"] == "SQL" for s in prof["skills"]))
        self.assertTrue(any("RetailWorks" in w["company"] for w in prof["work_history"]), prof["work_history"])

    def test_blank_scan_still_reports_no_text(self):
        c = self.candidate()
        self.upload(c, F.scanned_like_pdf(), "scan.pdf"); self.work()
        self.assertEqual(c.get("/me/profile").json["cvs"][0]["stage"], "failed")


CV_WITH_FIGMA = F.PRIYA.replace("Presented findings to stakeholders every month", "Prototyped report layouts in Airtable and presented findings to stakeholders every month")


class VerifiedReadingTests(unittest.TestCase):
    def test_only_facts_found_in_the_cv_are_added(self):
        rules = parse_cv(CV_WITH_FIGMA)
        proposed = {"skills": [{"name": "Airtable"}, {"name": "Kubernetes"}, {"name": "SQL"}],
                    "work_history": [{"title": "Chief Data Officer", "company": "Imaginary Corp", "start": "2015", "end": "2019"}],
                    "education": [{"degree": "PhD", "institution": "Nowhere University"}], "full_name": "Someone Else"}
        merged, adds = merge_verified(rules, proposed, CV_WITH_FIGMA)
        names = {s["name"] for s in merged["skills"]}
        self.assertIn("Airtable", names)
        self.assertNotIn("Kubernetes", names)                                # not in the CV: never added
        figma = next(s for s in merged["skills"] if s["name"] == "Airtable")
        self.assertEqual(figma["level"], "demonstrated")                     # it is used in a role description
        self.assertFalse(any(w["company"] == "Imaginary Corp" for w in merged["work_history"]))
        self.assertFalse(any(e["institution"] == "Nowhere University" for e in merged["education"]))
        self.assertEqual(merged["full_name"], "Priya Nair")                  # the parser found a name: it is not replaced
        self.assertEqual(adds, ["Skill: Airtable (shown in use)"])

    def test_model_fills_an_undated_role_and_is_labelled(self):
        class Model:
            label = "ollama:test"
            def call(self, tool, *a):
                assert tool == "record_cv_facts"
                return {"skills": [{"name": "Airtable"}], "work_history": [], "education": []}
        ai = ai_mod.HybridAI(Model(), LocalAI(), ["profile"])
        out = ai_mod.extract_profile(ai, CV_WITH_FIGMA)
        self.assertEqual(out["extracted_by"], "local-rules-v1 + ollama:test (verified against the CV)")
        self.assertIn("Skill: Airtable (shown in use)", out["ai_additions"])

    def test_model_down_keeps_rules_and_says_so(self):
        class Down:
            label = "ollama:test"
            def call(self, *a): raise ai_mod.AIError("ollama_unreachable", "down", retryable=False)
        out = ai_mod.extract_profile(ai_mod.HybridAI(Down(), LocalAI(), ["profile"]), F.PRIYA)
        self.assertEqual(out["extracted_by"], "local-rules-v1 (AI model unavailable)")
        self.assertEqual(out["full_name"], "Priya Nair")


GOOD_TASK = {"title": "Retail analysis", "scenario": "A retailer has seen weekend sales fall in two regions and wants to know why.", "minutes": 30,
             "questions": [{"id": "a", "prompt": "Which three metrics would you check first, and why those?", "max_points": 25, "rubric": "metrics; reasons; order",
                            "expected_points": [{"point": "Names metrics", "cues": ["revenue", "footfall", "conversion", "basket"]}]},
                           {"id": "b", "prompt": "How would you write SQL to compare weekend sales by region?", "max_points": 25, "rubric": "join; group by; filter"},
                           {"id": "c", "prompt": "Explain how you would check that your numbers are correct before sharing.", "max_points": 25, "rubric": "reconcile; totals"},
                           {"id": "d", "prompt": "How would you present the findings to a regional manager who is not technical?", "max_points": 25, "rubric": "clear; visual"}]}


class OpenAICompatibleTests(unittest.TestCase):
    def setUp(self):
        self.mode_rejected, self.score_reply = True, {"score": 20, "rationale": "Covers joins and grouping.", "evidence": ["group by region"],
                                                     "covered": ["group by"], "missed": ["filter"], "errors": ["Says WHERE filters after GROUP BY"]}

        def handle(path, body):
            if path == "/v1/models":
                return 200, {"data": [{"id": "llama-test"}]}
            if path == "/v1/embeddings":
                return 200, {"data": [{"embedding": [1.0, 0.0] if "sql" in t.lower() else [0.0, 1.0]} for t in body["input"]]}
            fmt = body["response_format"]["type"]
            if fmt == "json_schema" and self.mode_rejected:
                return 400, {"error": {"message": "response_format json_schema is not supported"}}
            user = body["messages"][-1]["content"]
            if "<candidate_answer>" in user:
                return 200, chat("```json\n" + json.dumps(self.score_reply) + "\n```")             # fenced, as small models do
            if "work-sample task" in user:
                return 200, chat(GOOD_TASK)
            return 200, chat({"summary": "She is a reasonable fit with strong SQL.", "strengths": ["SQL"], "gaps": ["Power BI"], "risks": [],
                              "requirements_check": [], "interview_questions": ["Tell us about a dashboard."], "confidence": 0.8})
        self.server = FakeServer(handle)
        self.cfg = Config(ai_provider="openai", openai_base_url=self.server.url + "/v1", openai_model="llama-test", openai_api_key="k",
                          ai_tasks="summary,assessment,evaluation")

    def tearDown(self):
        self.server.close()

    def test_provider_status_and_json_mode_fallback(self):
        ai = ai_mod.get_provider(self.cfg)
        self.assertIsInstance(ai.model, ai_mod.OpenAICompatAI)
        st = ai_mod.model_status(ai)
        self.assertTrue(st["reachable"] and st["installed"])
        self.assertEqual(st["provider"], "openai-compatible")
        prof = parse_cv(F.PRIYA)
        an = ai_mod.analyse_application(ai, prof, F.JOBS["analyst"])
        self.assertEqual(an["engine"], "openai-compatible:llama-test")
        self.assertIn("They are a reasonable fit", an["summary"])                     # gendered wording neutralised
        self.assertEqual(ai.model.mode, "json_object")                                # json_schema refused -> JSON mode remembered
        auth = [b for p, b in self.server.calls if p == "/v1/chat/completions"]
        self.assertTrue(auth)
        task = ai_mod.generate_assessment(ai, prof, F.JOBS["analyst"])
        self.assertEqual(task["engine"], "openai-compatible:llama-test")
        self.assertEqual([q["id"] for q in task["questions"]], ["q1", "q2", "q3", "q4"])

    def test_scoring_checks_correctness_and_flags_errors(self):
        ai = ai_mod.get_provider(self.cfg)
        task = ai_mod.normalise_task(json.loads(json.dumps(GOOD_TASK)))
        answers = {q["id"]: "I would join sales to stores, filter to Saturdays and Sundays, then group by region and compare totals week on week."
                   for q in task["questions"]}
        res = ai_mod.evaluate(ai, task, answers, {}, F.JOBS["analyst"])
        self.assertEqual(res["engine"], "openai-compatible:llama-test")
        self.assertIn("possible_factual_errors", res["flags"])
        self.assertTrue(res["possible_errors"][0].startswith("q1: Says WHERE"))
        self.assertIn("Possible errors", res["per_question"][0]["rationale"])
        self.assertEqual(res["per_question"][0]["covered"], ["group by"])
        self.assertIn("cross_check", res)

    def test_embeddings_from_the_same_server(self):
        cfg = Config(**{**self.cfg.__dict__, "semantic_match": True})
        enc = similarity.make_encoder(cfg)
        self.assertIsInstance(enc, similarity.HTTPEncoder)
        self.assertEqual(similarity.compare(F.PRIYA, "SQL reporting", enc)["method"], "semantic")

    def test_missing_model_name_falls_back_to_rules_with_warning(self):
        ai = ai_mod.get_provider(Config(ai_provider="openai", openai_model=""))
        self.assertTrue(ai.is_local)
        self.assertIn("missing", ai.misconfigured)


class OllamaRequestTests(unittest.TestCase):
    def test_context_window_and_tolerant_json(self):
        def handle(path, body):
            if path == "/api/tags":
                return 200, {"models": [{"name": "qwen2.5:3b"}]}
            if path == "/api/embed":
                return 200, {"embeddings": [[0.6, 0.8] for _ in body["input"]]}
            return 200, {"message": {"content": 'Sure! {"score": 7, "rationale": "Fine."} Hope this helps.'}}
        s = FakeServer(handle)
        try:
            cfg = Config(ai_provider="ollama", ollama_url=s.url, ollama_model="qwen2.5:3b", ollama_tasks="evaluation", semantic_match=True)
            ai = ai_mod.get_provider(cfg)
            self.assertTrue(ai_mod.model_status(ai)["installed"])
            out = ai.call("t", "d", ai_mod.Q_SCORE_SCHEMA, "sys", "user")
            self.assertEqual(out["score"], 7)
            body = [b for p, b in s.calls if p == "/api/chat"][0]
            self.assertEqual(body["options"]["num_ctx"], 8192)                 # Ollama's default 2048 would cut the CV off
            enc = similarity.make_encoder(cfg)
            self.assertEqual(enc.label, "ollama:nomic-embed-text")
            self.assertEqual(similarity.compare(F.PRIYA, "SQL", enc)["score"], 100.0)
        finally:
            s.close()


class AssessmentRetryTests(unittest.TestCase):
    def test_rejected_questions_are_retried_once_with_the_reason(self):
        bad = json.loads(json.dumps(GOOD_TASK)); bad["questions"][0]["prompt"] = "Using the provided sales data, find the weakest region and explain."
        prompts = []

        class Model:
            label = "ollama:test"
            def call(self, tool, description, schema, system, user):
                prompts.append(user)
                return json.loads(json.dumps(bad if len(prompts) == 1 else GOOD_TASK))
        task = ai_mod.generate_assessment(ai_mod.HybridAI(Model(), LocalAI(), ["assessment"]), parse_cv(F.PRIYA), F.JOBS["analyst"])
        self.assertEqual(task["engine"], "ollama:test")
        self.assertEqual(len(prompts), 2)
        self.assertIn("refers to data the candidate is never given", prompts[1])

    def test_two_bad_attempts_use_the_question_bank(self):
        bad = json.loads(json.dumps(GOOD_TASK)); bad["questions"][1]["prompt"] = bad["questions"][0]["prompt"]

        class Model:
            label = "ollama:test"
            def call(self, *a): return json.loads(json.dumps(bad))
        task = ai_mod.generate_assessment(ai_mod.HybridAI(Model(), LocalAI(), ["assessment"]), parse_cv(F.PRIYA), F.JOBS["analyst"])
        self.assertEqual(task["engine"], "local-rules-v1 (AI model unavailable)")


class AnthropicProviderTests(unittest.TestCase):
    """The Claude provider uses the official SDK with structured outputs (no forced tool choice). A stand-in client records
    the request, so nothing is sent."""
    class Client:
        def __init__(self, reply="{}", stop="end_turn"):
            self.reply, self.stop, self.kw = reply, stop, None
            self.messages = self

        def create(self, **kw):
            self.kw = kw
            block = type("B", (), {"type": "text", "text": self.reply})()
            return type("R", (), {"content": [block], "stop_reason": self.stop})()

    def test_structured_output_request(self):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest("anthropic SDK not installed")
        cl = self.Client(json.dumps({"score": 9, "rationale": "Clear."}))
        m = ai_mod.AnthropicAI("key", "claude-opus-5-5", client=cl)
        self.assertEqual(m.call("record_question_score", "Score one answer.", ai_mod.Q_SCORE_SCHEMA, "sys", "u")["score"], 9)
        self.assertNotIn("tool_choice", cl.kw)
        fmt = cl.kw["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertNotIn("maxLength", json.dumps(fmt["schema"]))           # constraints the API does not accept are removed
        self.assertNotIn("minimum", json.dumps(fmt["schema"]))
        self.assertEqual(cl.kw["model"], "claude-opus-5-5")

    def test_refusal_falls_back_to_rules(self):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest("anthropic SDK not installed")
        ai = ai_mod.HybridAI(ai_mod.AnthropicAI("key", "claude-opus-5-5", client=self.Client(stop="refusal")), LocalAI(), ["assessment"])
        task = ai_mod.generate_assessment(ai, parse_cv(F.PRIYA), F.JOBS["analyst"])
        self.assertEqual(task["engine"], "local-rules-v1 (AI model unavailable)")

    def test_anthropic_default_model_and_hybrid(self):
        ai = ai_mod.get_provider(Config(ai_provider="anthropic", anthropic_api_key="k"))
        self.assertIsInstance(ai, ai_mod.HybridAI)
        self.assertEqual(ai.model.label, "anthropic:claude-opus-5-5")


class ScoringGuardTests(unittest.TestCase):
    def setUp(self):
        self.task = ai_mod.normalise_task(build_assessment(parse_cv(F.PRIYA), F.JOBS["analyst"]))

    def test_keyboard_mashing_scores_zero_and_is_flagged(self):
        mash = "almxnxk xhwhiw sjdniw wsdhiwjd qwkjx vbnmz"
        res = ai_mod.finalize_evaluation(score_answers(self.task, {q["id"]: mash for q in self.task["questions"]}), self.task,
                                         {q["id"]: mash for q in self.task["questions"]}, rules=True)
        self.assertEqual(res["overall"], 0)
        self.assertIn("possible_non_answer", res["flags"])

    def test_a_generous_model_cannot_score_a_non_answer(self):
        class Model:
            label = "ollama:test"
            def call(self, *a): return {"score": 90, "rationale": "Excellent."}
        answers = {q["id"]: "I don't know, sorry, no idea about this one" for q in self.task["questions"]}
        res = ai_mod.evaluate(ai_mod.HybridAI(Model(), LocalAI(), ["evaluation"]), self.task, answers, {}, {})
        self.assertEqual(res["overall"], 0)
        self.assertIn("possible_non_answer", res["flags"])

    def test_real_answers_are_not_mistaken_for_non_answers(self):
        self.assertIsNone(non_answer_reason(F.STRONG_ANALYST_ANSWER))
        self.assertIsNone(non_answer_reason("I would use PostgreSQL and MySQL, then build a Tableau dashboard and an Excel pivot."))
        self.assertIsNone(non_answer_reason("Pehle main data saaf karungi, phir region ke hisaab se pivot table banaungi."))

    def test_synonyms_earn_credit(self):
        q = {"id": "q1", "prompt": "How do you make sure a report is right?", "max_points": 100, "rubric": "",
             "expected_points": [{"point": "Validates the numbers", "cues": ["validate", "reconcile", "verify", "check totals"]}]}
        plain = score_answers({"questions": [q]}, {"q1": "I send the report to the team as soon as it is finished each Monday morning."})
        other_words = score_answers({"questions": [q]}, {"q1": "Before sending it I double-check every figure against the finance ledger and confirm the totals match."})
        self.assertEqual(plain["per_question"][0]["score"], 0)
        self.assertGreater(other_words["per_question"][0]["score"], 0)


class HealthTests(Base):
    def test_health_reports_ocr(self):
        h = self.client().get("/health").json
        self.assertIn("ocr", h)
        self.assertIn("enabled", h["ocr"])


if __name__ == "__main__":
    unittest.main()
