# Test report and readiness assessment

## Latest verification (16 November 2026)

| Check | Result |
|---|---|
| Full automated suite, Linux, Python 3.13 | **213 tests: 211 passed, 2 skipped, 0 failed** (skipped: OCR, which needs Tesseract; the live-model test, run separately below). |
| **Real local AI model** (Ollama 0.40, qwen2.5:3b, CPU only) | **Live-model test passed** (CV check, fit summary, question attempt, per-question scoring). The end-to-end smoke test with no AI settings **passed**: the model was found and used automatically; it scored the answers and wrote the summary. Question writing: see the next row. |
| Model-written questions with the real 3B model | **The real model now writes the tests itself** (before this round both of its attempts were rejected and the question bank was used). Data Analyst: accepted on the 2nd try (SQL, data cleaning, Excel pivot tables, plus one general question). Backend Developer: accepted on the 1st try, but two questions referred to "question 2"; that is now rejected, and on the rerun the 3rd try gave five self-contained questions (API under load, frontend integration, SQL, Git review, error handling and retries). About 1.5 to 3.5 minutes per test on a 4-core CPU. A 3B model's questions are usable but plain: preview them, or use a larger model (qwen2.5:7b) on a 16 GB machine. Correctness of model-written questions is not checked automatically. |
| Browser journey (Chromium, new design) | **23 of 23 checks passed**, including CV upload, analysis, skill test, scoring, byte-identical CV download, second attempt and follow-up message. |
| On-screen test warnings (Chromium) | **10 of 10 passed**: told before starting; warned on leaving the page, on the pointer staying outside, on pasting; firmer wording after 3 departures; never blocks submitting; the recruiter sees the counts and the limits. |
| Container image | Built and started here like a hosting service (given `PORT`, Render-style settings, data disk). Healthy; detected the platform and its public address; data owned by the app user; the app runs as a normal user (uid 999); sign-in through an https proxy works with Secure, HttpOnly cookies; requests from other sites refused. **The Tesseract and gosu install step could not run here** (this sandbox cannot reach Debian's servers); GitHub's `docker.yml` workflow builds the real image and checks it after every upload. |
| Render, GitHub Actions, Windows, macOS | **Not run here.** The Render file and the two new workflows are written to their documented formats but are untested until uploaded. |

## Earlier verification (14 November 2026: originality checks, skill-test tools, new interface)

| Check | Result |
|---|---|
| Full automated suite (`cd backend && python -m unittest discover -s tests -t .`), Linux, Python 3.13, SQLite | **201 tests: 199 passed, 2 skipped, 0 failed.** The two skipped tests need things this environment lacks: a live Ollama model and Tesseract OCR (the OCR code was not changed in this round). Without the optional Claude library installed, its two tests are skipped as well (197 passed, 4 skipped). 34 tests are new. The suite was not run on PostgreSQL in this round. |
| Complete journey in a real browser (headless Chromium, the real launcher `run.py`, fictional data) | **23 of 23 checks passed**: register, upload a CV, CV read and matched to its owner, profile with skills and roles, confirm, match preview, apply, skill test written and sent, fairness notice, draft restored after reload, submit, scored with per-question feedback, candidate shown no similarity finding; recruiter opens the file, **downloads the CV and it is byte-identical to the upload**, reads the extracted text, sees every answer, both originality exhibits, sends a follow-up, offers a second attempt (first attempt kept), saves a note; candidate sees the message and the new attempt; no JavaScript errors. |
| Seeded demo (6 fictional applicants) | The three template CVs are grouped (88% word-for-word, 100% same template); the two shared answer sets are flagged as identical, with the chatbot opening line quoted; the four genuinely different CVs and their answers show nothing. |
| Layout | Every main screen captured at 1366 px and 390 px; no horizontal scrolling at either width. Tablet widths, Safari, Firefox and Edge were not checked in this round. |
| AI path, start to finish (`scripts/smoke_test.py` with no AI settings, against a stand-in Ollama server that imitates a small model: fenced JSON, gendered pronouns, an invented skill and employer, scores on a 0-100 scale) | **Passed.** The model was detected and switched on automatically; CV reading, fit summary, questions and scoring all went through the model code path; the invented skill and employer were rejected; an invented quote was removed; the out-of-scale scores were asked again and came back on the right scale; the rule-based cross-check ran. This run also found and fixed a start-up ordering bug in the new automatic detection. |
| **Real Ollama model** | **Not run in this environment**: its network blocks ollama.com, so the program and model could not be downloaded. The last live qwen2.5:3b run is the one recorded below (29 October). The request format sent to Ollama is unchanged apart from the test-length sentence in the question prompt. **Run `test_windows.bat` / `test_mac.command` on the presentation computer with Ollama installed**; it prints which engine wrote and scored the test. |
| Claude and OpenAI-compatible providers | Request shape covered by tests with stand-in clients/servers; not run against live services (no keys here, and none is needed for the default setup). |
| Windows and macOS | **Not run**: this environment is Linux only. The batch and command files were edited by hand (the Ollama install step uses `winget` on Windows and `brew` on a Mac); those lines are untested and are written so that a failure there cannot stop setup. |
| E-mail | Follow-up messages are stored, shown in the candidate's account and written to the file outbox. Real delivery through Resend/Brevo/SMTP remains untested (no account). |
| Clean-room check | The delivered zip was unpacked into an empty folder, set up from `requirements.txt` only, and the suite and the smoke test were run there (see the end of this section). |

### What the originality checks can and cannot do (read before relying on them)
- They compare **wording**. Copies, lightly edited copies and one template with different fill-ins are caught. A text reworded
  thoroughly (by a person or a model) shares few word sequences and is **not** caught, unless an embedding model is switched on,
  and that path has only been tested with a stand-in encoder.
- They are **not an AI detector**. Nothing here claims to know whether a person or a model wrote a text; no reliable method for
  that exists. "Chatbot text" means a literal leftover such as "As an AI language model", quoted so the reviewer can see it.
- Thresholds (25% / 55% for CVs, 30% / 60% for answers) were set on a small set of fictional documents. Expect some false alarms
  (two graduates of one careers workshop, a common textbook answer) and some misses. That is why every finding carries its
  passages and a reviewer's verdict, and why it never changes a score or a stage.
- Comparison is within one organisation's applicants (the most recent 1,500). Not tested for speed beyond a few dozen applicants.
- Model-written tests are checked for being about the opening, not for being factually right. A recruiter can preview and edit a
  test; with automatic sending switched on, model-written questions reach candidates unread by a person.

### Clean-room result
The zip was unpacked into an empty folder and set up with `requirements.txt` and `requirements-dev.txt` only. There: the suite
ran **201 tests, 197 passed, 4 skipped, 0 failed** (no Claude library, OCR or Ollama in that folder); `scripts/smoke_test.py`
**passed**; the demo was started with `run.py --load-demo-candidates` and the 23-check browser journey **passed**, including the
byte-identical CV download; all main screens rendered at 1366 px and 390 px without horizontal scrolling.

## Earlier verification (29 October 2026, AI upgrade and Windows round)

| Check | Result |
|---|---|
| Full automated suite (`cd backend && python -m unittest discover -s tests -t .`), Linux, Python 3.13, SQLite | **167 tests, 166 passed, 1 skipped** (the opt-in live-Ollama test). Includes 31 new tests for OCR, two-column PDFs, the OpenAI-compatible and Claude providers, verified AI CV reading, question retries, error checks, non-answer detection, synonyms, embeddings, and Windows portability. |
| OCR on a real scanned CV (Priya Nair sample printed to images, no text layer) with Tesseract 5.3 | **Passed**: name, roles, skills read; profile marked "read with OCR". |
| Two-column PDF fixture | **Passed**: columns read separately; roles and education parsed. The three sample PDFs extract byte-for-byte as before. |
| `scripts/smoke_test.py` against the real launcher (`run.py`, waitress, temporary data folder), rule-based engine | **Passed**: health, page, JS/CSS content types, demo sign-in, register, upload, profile, confirm, apply, auto-assessment, submit, scored result visible to the recruiter. |
| Same smoke test with `AI_PROVIDER=openai` against a local stand-in model server | **Passed**: CV read by "rules + model (verified against the CV)", questions and scores by the model, an invented skill was rejected. |
| Claude provider | Request shape tested with a stand-in client (structured outputs, no forced tool choice, unsupported schema keywords removed, refusal falls back). Not run against the live API (no key in this environment). |
| Real Ollama model in this round | Not re-run here (Ollama could not be installed in this environment). The earlier live qwen2.5:3b run is recorded below; rerun `TB_TEST_OLLAMA=1` and the smoke test with Ollama on the presentation machine. |
| Windows | Code reviewed and fixed for Windows (MIME types, `.env` encoding, console code page, paths with spaces/accents, Tesseract folders, CRLF scripts); these are covered by `test_portability.py`. Execution on Windows itself is done by `.github/workflows/tests.yml` (windows-latest, Python 3.10/3.13, plus the double-click scripts) and by `test_windows.bat` on the target PC; neither had been run when this report was written, because this environment has no Windows machine and no GitHub access. |

## Earlier verification (29 October 2026, repair pass)

| Check | Result |
|---|---|
| Full automated suite (`cd backend && ../.venv/bin/python -m unittest discover -s tests -t .`) | **136 tests, 135 passed, 1 skipped**. The skipped test is the opt-in real-model test; it was run separately below. |
| Real Ollama integration (`TB_TEST_OLLAMA=1 OLLAMA_MODEL=qwen2.5:3b ... LiveOllamaTests.test_real_model_analysis_questions_and_scoring`) | **Passed** against the installed local qwen2.5:3b model: analysis, assessment generation and evaluation. |
| Local app run (`127.0.0.1:5157`, data in `/tmp/talentbridge-verification`) | **Passed**. `/api/v1/health` returned `ok: true`, Ollama reachable and installed, SQLite, demo mode off. The browser displayed the sign-in page. |
| Responsive visual check | Viewed the served sign-in page at the in-app browser's 615 × 726 viewport; it fit without a visible horizontal overflow. Desktop and alternate phone widths were not re-tested in this pass. Earlier Chromium checks at 1366/820/390 px are recorded below. |
| Existing user data | Left `data/talentbridge.db`, uploads, and `.env` untouched. Runtime verification used a disposable `/tmp` data directory. |
| Deployment / Windows / email delivery | Not exercised in this pass. See the deployment guide and readiness notes below. |

Change made: bare `Config()` previously defaulted to `llama3.2:3b` even though the project setup, docs, and requested model specify `qwen2.5:3b`. The default now agrees with those settings. `.env` can still select another model.

For this pass, candidate/recruiter API workflows, identity isolation, persistence and fallback labels were covered by the automated suite. The live application was not populated with demo records; the full fictional workflow is exercised by tests and documented in `DEMO_SCRIPT.md`.

The Round 2 report below is prior verification, not a claim that PostgreSQL, browser widths or deployment were re-tested on 29 October.

### Readiness snapshot

| Feature | Status |
|---|---|
| Candidate registration, CV upload/extraction/confirmation, applications and assessment persistence | Implemented and tested in the automated SQLite suite |
| Recruiter job and application review, evidence display, human decisions | Implemented and tested in the automated SQLite suite |
| PDF/DOCX validation, CV-to-account checks, application/profile snapshots | Implemented and tested with fictional fixtures; no OCR for scanned PDFs |
| Ollama qwen2.5:3b summary, assessment and evaluation paths | Implemented and live-model tested; AI output still needs human review |
| Honest rule-based fallback and engine labels | Implemented and tested |
| Responsive layout | Implemented; inspected at 615 px this pass, previous Chromium evidence at 1366/820/390 px is historical |
| Public deployment configuration and guidance | Partially implemented; guide exists, but no cloud deployment or production hardening audit was run |
| Windows setup | Implemented in scripts/docs but not verified on Windows |
| Email | Outbox and provider integrations implemented; real delivery remains unconfigured and untested |
| OCR, MFA, password reset, retention automation | Not implemented |

## Round 2 (handover preparation, macOS 26, Apple M5 16 GB, Python 3.15)
| What | Result |
|---|---|
| Automated suite on SQLite | **136 tests run, 135 pass, 1 skipped** (the live-model test, run separately below) |
| Same suite on PostgreSQL 18.6 (`TB_TEST_DATABASE_URL`) | **136 run, 135 pass, 1 skipped** |
| Live local model `TB_TEST_OLLAMA=1` (qwen2.5:3b via Ollama) | **pass**: real analysis, questions and scoring; engine recorded; quotes verified |
| Real-model workflow (one process, Flask test client, fictional data) | register → CV → confirm → apply (AI analysis + AI questions, ~40 s) → draft restored → submit → AI scoring per question (~20 s) → recruiter review → shortlist → **new app instance on the same DB (restart)**: status, note, answers and AI result kept. Ollama-down path labelled rule-based. All checks passed. |
| SQLite → PostgreSQL copy script (fictional seed data) | all 17 tables copied, row counts verified; second run refused (target not empty); app ran on the copy: logins, lists, scores, answers, CV download, CSV |
| Clean-room setup: only the files that would be committed, `./setup_mac.command dev` in a fresh folder | setup succeeded; full suite ran there |
| E-mail | Resend/Brevo request format, allow-list hold, 401 handling, missing-key fallback tested with captured HTTP (nothing sent). Notifications (registration, assessment ready, submitted) verified in the outbox. **Real delivery not verified: no account/API key.** |
| Browser (Chromium) | Not re-run this round: starting a background server was declined. The previous round's 35/35 browser run predates the small UI changes made here (competitions tabs, engine labels). |
| Windows | Not tested (no Windows machine available). |

AI quality findings from the live runs and what was done: the 3B model used gendered pronouns (now neutralised server-side), wrote questions that referred
to "provided data" the candidate never receives (now rejected; rules used and labelled), and when scoring all answers in one call it applied one rubric to every
question (now one call per question; repeated feedback and AI/rule disagreements of 25+ points are flagged).

# Round 1 (23 October 2026, macOS, Python 3.15, SQLite)

## Tests actually run
| What | Result |
|---|---|
| Automated suite `python3 -m unittest discover -s tests -t .` (from `backend/`) | **126 tests, all pass** (100 earlier + 26 new regression tests). Two new tests were deliberately broken (ownership check disabled, blank/short labelling disabled) and failed as expected, so they do test the behaviour. |
| Browser end-to-end (headless Chromium 156 via Playwright, fresh data folder, fictional data only) | **35/35 checks pass.** Candidate: demo banner; someone else's CV flagged and not applied; own CV verified; undated-role warning; "not verifiable" experience; confirm; preview score = application score; 4 distinct questions; draft restored exactly after navigating away and after reload; 4 answers submitted; DB holds exactly those answers; all 4 scored; results show own answers; no horizontal scroll at 390 px. Recruiter: correct person, contact details and CV; every submitted answer visible; same overall score as candidate; human review with note → shortlist; persisted after reload; activity history shows the note; no horizontal scroll at 390 px and 820 px; candidate pool and dashboard counts updated; CSV lists the right person and CV; candidate gets 403 on recruiter API. Only console error: that deliberate 403. |
| The supplied tester CVs (stored text, not included in the repository) through the new parser | Tester B: undated role now captured with a warning, BA (History & Political Science), certificates flagged as possibly run together. Tester A: 3 dated roles, tools no longer inside the last job, BA English Literature, 4 clean certifications. Priya: unchanged roles, data-analysis credit no longer taken from a certificate. |
| Identity repair on a copy, then on `data/` | Plan, moves and rescoring as described in CHANGES.md. |

## Not tested / could not verify
- **Restart via the real launcher in the browser**: my attempt was declined in this session. Restart persistence *is* covered by automated tests that open a second app instance on the same database (answers, scores, review notes, status).
- Safari (only Chromium was automated), Windows, PostgreSQL, SMTP e-mail, S3 storage, Ollama with a real model, the paid Anthropic provider, `sentence-transformers` semantic mode.
- Real-world CV variety: only 7 CVs (4 fictional, 3 supplied). Multi-column and table-heavy PDFs remain a known weakness.
- No load testing beyond the existing small performance test; no fairness/bias evaluation; no penetration test.

## Status of each major requirement
| Requirement | Status |
|---|---|
| Stable candidate IDs; application ↔ candidate ↔ job ↔ CV association | Implemented and tested |
| Upload cannot overwrite another person's profile; mismatch flagged | Implemented and tested |
| Applications keep their own CV/profile; multiple applications per person | Implemented and tested |
| Existing records repaired with backups | Implemented and verified on the data (CLI output + UI) |
| Backend access control for profiles, CVs, applications, answers, files | Implemented and tested |
| Duplicate-person prevention | Partially implemented: unique email, ownership check, re-use of a record by CV email when moving. No fuzzy duplicate detection (deliberately: similar names are not merged). |
| Draft persistence, exact restore, submit, idempotency, late-autosave guard | Implemented and tested (API + browser) |
| Scoring reads persisted answers; blank vs short vs scored; failure ≠ zero; retry; resume after restart; retake keeps history | Implemented and tested (automated) |
| Distinct, role-relevant, CV-grounded questions | Implemented and tested for the 3 demo openings × 4 CVs; other job types rely on templates and may be generic |
| CV parsing improvements, warnings, edit before confirm | Implemented and tested on fixtures and the supplied CVs |
| One documented, reproducible, versioned match score with history | Implemented and tested |
| Recruiter: create/edit/publish/close/reopen jobs, applicants, detail, notes, decisions, stages, history, search/filters, CSV, dashboard | Implemented and tested |
| Interface redesign of application pages, responsive | Implemented; checked in Chromium at 1366/820/390 px |
| Setup, run, stop, test, backup documentation | Implemented (README, MAC_SETUP_GUIDE, ROLLBACK, DEMO_SCRIPT) |
| Live AI scoring | Not implemented beyond the existing optional Ollama/Anthropic code paths (unverified with real models) |
| Production deployment, e-mail delivery, SSO, data retention policy | Not implemented / not verified |

## Readiness (honest view)
**Demonstrably working:** the full candidate → recruiter loop on one laptop with correct identities, protected data, persistent drafts and answers, explainable and consistent scores, and a usable reviewer workflow. Suitable for controlled demonstrations and a **small supervised pilot with fictional or consenting test users**.

**Before a real commercial pilot with real candidates:**
1. Legal/privacy: privacy notice and consent text, lawful basis, retention and deletion schedule, DPDP Act 2023 (India) / GDPR review as applicable, data-processing terms. None exists yet.
2. Hosting: HTTPS, PostgreSQL, separate worker, backups with tested restore, monitoring/alerting (docs/DEPLOY.md is a starting point, untested here).
3. Security: external penetration test, dependency scanning, MFA for recruiters/admins, password reset flow (there is none), session revocation UI.
4. Assessment quality: rule-based scoring checks topic coverage only; a reviewer must read answers. Validate against human ratings before relying on scores; run a bias/adverse-impact review.
5. Parsing: test on a larger real CV set; OCR for scanned CVs is not available.
6. E-mail notifications (SMTP) are implemented but untested; candidates currently see assessments in the app only.

Calling this "70% commercially ready" is a judgement, not a measurement: the product core works and is tested; the legal, hosting and assurance work around it has not started.
