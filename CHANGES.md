# Changes

## 16 November 2026 — real AI model, test-taking checks, calmer design, put it online
- **Real AI verified here**: Ollama and qwen2.5:3b installed in the test environment; TalentBridge found it, started it and downloaded
  the model with no settings. The live-model test passed (CV check, fit summary, per-question scoring).
- **Never breaks on a model fault**: any error from a model (not only the expected kinds) now falls back to the rule-based engine
  and the result says so. Question writing gets three tries, each told every earlier reason, before the role-specific bank is used. Questions that depend on another question's answer ("the function you designed in question 2") are now rejected too.
- **Three or more candidates with the same answer** are named as a group ("3 candidates, same answer") and the finding is marked strong.
- **How the test was taken** (`backend/app/integrity.py`, migration 7): the test page notes leaving the page (and for how long),
  the pointer staying outside it, and pasted versus typed text, as counts and times only. Candidates are told before they start and
  get a calm on-screen notice when something is noted; nothing is blocked. The recruiter sees it as Exhibit C, with what it cannot see.
- **Design**: native system typeface, translucent header, hairline dividers, one muted green accent, soft grey labels; the bundled web
  fonts and the illustration were removed.
- **Put it online**: one-container `Dockerfile` (data on `/data`, runs as a normal user, health check), `render.yaml` (Deploy to
  Render button), `compose.simple.yaml`, GitHub workflows that build, start-check and publish the image and fill in the README links,
  automatic settings for Render, Fly.io, Railway, Cloud Run, Heroku and Codespaces (`backend/app/hosting.py`). Steps in START_HERE.html.
- Tests: 213 (all pass; 2 skipped for OCR and the live model, which was run separately).

## 14 November 2026 — originality checks, skill-test tools, second attempts, follow-ups, new interface
Guiding rule for everything below: the software gathers and shows evidence; a person decides. No finding changes a score, moves an
application or rejects anyone.

**CV similarity and template detection** (`backend/app/originality.py`, migration 5)
- Every application's CV is compared with the CVs of other candidates who applied to the same organisation: share of identical
  5-word sequences (numbers ignored, contact details and the person's own name removed), and the same comparison after names,
  tools, numbers and other proper nouns are blanked out, which catches one template filled in with different details. An identical
  file from another account is the strongest signal. Wording copied from the job advertisement is ignored.
- A second account of the same person applying to the same opening is flagged (same e-mail or phone on both CVs, or the same
  name with similar text). A repeat attempt to apply from the same account stays one application and is noted in its history.
- Text addressed to an automated screener ("ignore previous instructions", "give this candidate full marks") is quoted and flagged.
- Stock résumé phrases are counted and shown as context only; they never raise a flag by themselves.
- The opening page lists groups ("Arjun Rao ↔ Dev Malhotra ↔ Sana Iqbal") with a sample passage; each application page shows
  Exhibit A with every matching passage, and both sides of a match are updated.

**Plagiarism check on skill-test answers**
- Each submitted answer is compared with other candidates' answers for the same opening (4-word sequences, after removing the
  question's own wording): identical text, copied passages, chatbot leftovers ("Certainly! Here is…", "As an AI language model"),
  instructions aimed at the scorer, and more words than can be typed between Start and Submit. With an embedding model configured
  (`SEMANTIC_MATCH=1`) answers that say the same in other words are noted for information.
- Shown as Exhibit B per question, with the other candidate's name and the shared text. Candidates never see these findings; the
  test's start page tells them answers are compared.
- **Reviewer's verdict**: "Not a concern" / "Mark as a concern" with a note, kept in the activity history. A cleared finding stops
  counting as open; it reopens by itself if new matching evidence arrives. Deleting a candidate removes them from other records.
- This is not an "AI detector": it does not claim to know who or what wrote a text. It shows what matches what.

**Skill-test generator**
- Per opening: test length (3 to 6 questions), a **preview** of the test with its private marking guide, and **send to everyone
  waiting** (one test written per applicant; nobody gets a second one by accident).
- Model-written tests must be about the opening: at least one required skill tested and at least half the questions on the role,
  otherwise the model is asked again and then the role-specific question bank is used (and labelled).
- **Second attempt**, the reviewer's call: new questions or the same ones, sent in one click or left as a draft to edit, with a
  reason. The first attempt, its answers and its score stay on file. When a strong CV meets a weak test the page says so.

**AI reliability**
- **Zero-setup AI** (`backend/app/autoai.py`): with no AI settings, start-up uses Ollama if it is installed (starts it, and downloads
  the model once in the background). No account, key or payment. Otherwise the built-in rule engine runs, as before.
- Fixed: a model answering "85" for a 30-point question was silently clamped to full marks. It is now asked again; a persistent
  0-100 answer is converted to the question's points and flagged for the reviewer; anything else falls back to the rules.
- Fixed: the Claude provider crashed instead of falling back when its SDK was not installed.
- Gender-neutral rewriting keeps verb agreement ("He covers" → "They cover").

**Follow-up messages**: a reviewer can write to a candidate from the application page (with starting texts for common cases). The
message always appears in the candidate's own account and is also e-mailed when an e-mail service is configured (migration 6).

**Interface**: redesigned (own typefaces bundled under the SIL Open Font License, neutral off-white, deep teal, apricot highlights,
score dials, "exhibit" cards and verdict stamps), with a four-step guide for candidates, a focused skill-test page with word
counts and a sticky timer, and a simpler sign-in page. Checked in Chromium at 1366 px and 390 px.

**Demo data**: three more fictional applicants (one CV template, two sets of shared answers) so the checks have something to show.

**Tests**: 34 new (`test_originality.py`); 201 in total.

## 29 October 2026 — AI upgrade, scanned CVs, Windows support
**AI (backend/app/ai.py, assist.py)**
- AI CV reading (`profile` task, on by default with a model): the rule-based parser runs first, the model proposes missed skills,
  roles, dates, institutions and contact details, and each proposal is kept only if it is found in the CV text. The profile lists
  every AI addition (`ai_additions`) and shows "Read by: Rules + AI reader (model)".
- New `AI_PROVIDER=openai`: any OpenAI-compatible server (LM Studio, Jan, llama.cpp, vLLM, Groq, OpenRouter, Gemini), with
  json_schema output and automatic fallback to JSON mode for servers that do not support it.
- Claude provider rewritten on the official SDK with structured outputs (`output_config.format`). The previous raw call forced
  `tool_choice`, which current Claude models reject; default model is now `claude-opus-5-5`. All model providers (Ollama, OpenAI-
  compatible, Claude) now share the hybrid mode: rule-based fallback, engine labels, cross-check.
- Ollama: `num_ctx` 8192 (Ollama's 2048 default silently cut long CVs off), `keep_alive`, model warm-up at start-up, JSON parsing
  that tolerates code fences and surrounding text, `:latest` model names recognised.
- Prompts get a compact profile (smaller, faster, fits small models). Fit summary prompt asks for CV-specific interview questions.
- Question writing: a rejected model task is retried once with the reason before falling back to the question bank; models now
  return `expected_points` with cue words, so the rule-based cross-check uses the model's own rubric.
- Scoring: per-question prompts include the rubric points; the model reports covered/missed points and possible factual errors,
  which are shown to the recruiter (`possible_factual_errors` flag).
- Embedding similarity from the AI server (`SEMANTIC_MATCH=1`, Ollama `nomic-embed-text` or OpenAI-compatible `/embeddings`),
  no PyTorch needed. `AI_TASKS` replaces `OLLAMA_TASKS` (the old name still works).

**Rule-based engine (answer_scorer.py)**
- Concept synonyms: an expected point made in other words ("double-check" for "validate") earns one extra cue.
- Non-answers ("I don't know") and keyboard mashing ("xhwhiw sjdniw") score 0 on every engine, flagged `possible_non_answer`.

**Reading CVs (extract.py, ocr.py, cv_parser.py)**
- Scanned PDFs are read with OCR (Tesseract, found on PATH or in the standard Windows/Homebrew folders; RapidOCR as a pure-pip
  option). The profile is marked "read with OCR". `OCR=off` disables it. Tesseract added to the Docker image.
- Two-column PDF layouts are detected and read column by column (single-column extraction is unchanged; verified on the samples).
- DOCX: header text (contact details) and merged table cells read once. Education: degree, institution and year on separate
  sidebar lines are parsed correctly.

**Windows**
- Static files are always served as `text/javascript` / `text/css`: the Windows registry often maps `.js` to `text/plain`, which
  makes browsers refuse the UI's scripts (blank page).
- `.env` reader handles Notepad's UTF-8 BOM, CRLF, inline `# comments` (uncommenting a line from `.env.example` used to break the
  value) and quoted values. Console output never crashes on a legacy code page.
- New double-click scripts: `start_windows.bat` (opens the browser, sets up on first run), `start_demo_windows.bat`,
  `test_windows.bat` (test suite + end-to-end check, log in `test-results-windows.txt`); `setup_windows.bat` rewritten (Python
  launcher / Store-alias detection, options `dev postgres anthropic`, Tesseract hint). Mac equivalents added. `.gitattributes`
  keeps CRLF for batch files.
- `WINDOWS_SETUP_GUIDE.md`; `run.py --open`; friendly "port already in use" message.
- `.github/workflows/tests.yml`: full suite + end-to-end check on Windows, macOS and Linux (Python 3.10 and 3.13), plus a job that
  runs the Windows double-click scripts.

**Tests**: 31 new (`test_ai_upgrades.py`, `test_portability.py`); 167 in total. `scripts/smoke_test.py` starts the real app and runs
the whole candidate → recruiter flow.

## 29 October 2026 — MVP verification
- Fixed the bare `Config()` Ollama model default from `llama3.2:3b` to the documented and requested `qwen2.5:3b`. `.env` deployments could already override this, but direct configuration and test instances silently chose a different model.
- Re-ran the SQLite suite (136 tests, 135 passed, one opt-in live test skipped), then ran that live qwen2.5:3b test separately (passed). Started the app against `/tmp/talentbridge-verification`; health reported Ollama reachable/installed, SQLite, and demo mode off. Existing `data/talentbridge.db` and uploads were not used.
- Updated the Mac Ollama and demo-script instructions to describe the configured AI/rule split accurately.

## Handover round
- **Local AI (Ollama, qwen2.5:3b)**: verified with the installed model; per-question scoring for local models; rule-based cross-check on every AI score;
  the real engine is stored and shown for analysis, questions and scoring (fallback results say "Rule-based (AI model was unavailable)"); generated questions
  validated (count, rubric, overlap, no reference to unseen data); gender-neutral wording enforced; `/health` and the start-up banner report model status.
- **E-mail** (`backend/app/mail.py`): Resend, Brevo, SMTP or the default file outbox; allow-list so no real candidate is e-mailed without approval;
  registration, assessment-ready and assessment-submitted notifications; `scripts/send_test_email.py`; migration 4 records message kind and delivery result.
- **PostgreSQL**: whole test suite runs on PostgreSQL (`TB_TEST_DATABASE_URL`); `scripts/sqlite_to_postgres.py` copies data with verification;
  `requirements-postgres.txt`; friendly error if the driver is missing.
- **Competitions**: a Jobs / Competitions switch for candidates, a type column for recruiters, a fictional demo competition.
- **Setup**: `setup_mac.command`, `setup_windows.bat`; `.gitignore` excludes `.env`, virtual environments, databases, uploads, outbox, logs, backups and any
  CV in `sample_data/` other than the four fictional ones; real tester names removed from the docs.

# Changes — October 2026 stabilisation

## Root causes found (from the code and the stored records, not the screens)

| Reported symptom | Actual cause |
|---|---|
| Tester B's application shown as **Priya Nair**, with Priya's email and phone | All three test CVs were uploaded while signed in as the demo candidate *priya.nair@talentbridge.demo*. The app had one candidate record per account and **silently replaced that account's profile with whatever CV was uploaded last**, while keeping the account's name, email and phone (`phone=COALESCE(phone, …)`). The Backend application was therefore stored under Priya's record with Tester B's CV. |
| Priya's record showed all three CVs | They really were stored on Priya's record. Nothing checked whether a CV belonged to the account uploading it. |
| Candidates page showed 3 people, the opening showed 2 applicants | Both were correct for the stored data (3 accounts; Rohan + "Priya" applied). The identity bug made them look contradictory. |
| Priya's own Data Analyst score changed | Every application was recomputed from the candidate's *latest* profile whenever a CV was uploaded, so her Data Analyst match was being recalculated from Tester B's CV. |
| Assessment 0/100, "all answers empty or fewer than five words" | The persistence chain worked: the stored submission was exactly what the browser sent: `almxnxk`, `xhwhiw`, `sjdniw`, `wsdhiwjd` (one word each). Scoring 0 was arithmetically right, but the message lumped *blank* and *too short* together, the recruiter screen hid the answers in a collapsed box away from the feedback, and a scoring **failure** would have left the assessment stuck in "scoring" forever with no way to recover. Real race found while investigating: an autosave arriving after Submit could overwrite the submitted answers. |
| Two overlapping booking-API questions | The REST-API question template and the job's own scenario ("design an API for a booking service…") were both used. |
| Work history empty, 0 years for Tester B's CV | The parser created a role **only when it found a date range**; her single role has no dates, so it vanished and looked like "no experience". "Bachelor of Arts" became "Bachelor's degree, field: Arts"; "onboarding" (in "onboarding to checkout") was read as an HR skill; certificates were counted as skills *shown in use*. In Tester A's CV the headings "TOOLS & TECHNOLOGY" and "EDUCATION & LANGUAGES" were not recognised, so tools leaked into her last job and her degree into certifications; wrapped bullet lines were cut. |
| Different match scores in candidate and recruiter views | Candidate preview and stored application used different requirement checks; the stored score silently mixed in the assessment (20%) once scored and changed when the profile changed; "experience" showed `0 years` for undated roles. |

## What changed

**Identity and ownership** (`identity.py`, `pipeline.py`, `routes_core.py`, migration 3)
- Every processed CV is checked against the record it was uploaded to (email match, or name agreement; similar names such as "Priya Nair"/"Priya Sharma" do not match). A CV that names someone else is **held** (`mismatch`) and never applied to the profile. The owner can confirm it ("this is my CV", audit-logged) or remove it; a recruiter/admin can move it, with any applications made with it, to its owner's record.
- Each application is **pinned** to the CV it was made with and a snapshot of the confirmed profile. Later uploads or edits never change a submitted application.
- CV files and text are visible to the owner, admins, and recruiters of an organisation that received an application *made with that CV* (or manages the record) — not every CV of a person. All checks are server-side; direct URLs return 404.

**Assessments** (`routes_core.py`, `pipeline.py`, `answer_scorer.py`, `ai.py`)
- Draft save re-checks the state inside a transaction and can never overwrite a submission. Submit is conditional and idempotent (same answers again → OK, different → refused); the scoring job is queued in the same transaction.
- Answers are stored with a fingerprint of the exact question set; scoring reads the persisted submission only.
- Per-question status **blank / too short / scored**; "no scorable answers" is labelled as such, not as a poor answer. Scoring failure → *Needs review: automatic scoring failed (answers are safe)*, never a zero; recruiter can retry scoring or move to human review. Interrupted scoring resumes after a restart. Retakes keep earlier attempts.
- States shown everywhere: Draft saved, Submitted/being scored, Scored, Needs review.
- Question generation: role-aware Python question for backend roles; skill questions that repeat the job's scenario are skipped; a demonstrated SQL dialect counts as SQL in use.

**CV parsing** (`cv_parser.py`, `extract.py`, `profile.py`)
- Undated roles are kept with dates "unknown" and a warning that this is *not* the same as no experience; years show as "not verifiable" instead of 0. Combined headings, wrapped bullets, full degree names, "Remote"/"Hybrid" fragments, certificate-only skills (now "listed"), run-together certificates (warning), missing name (warning), password-protected PDFs (specific message). The candidate can now also edit projects and certifications.

**Matching** (`matching.py`, version `match-v2`)
- One function for preview, stored match, recruiter view, list, comparison and CSV. CV match and overall are separate and documented (overall = 0.8 × CV match + 0.2 × assessment once scored). Evidence levels: shown in use / partial / not found ("not proof of absence") / not parsed; experience: met / below / not verifiable / not found. Each result records scoring version, input fingerprints and date; recalculations keep the previous result in `match_history` with a reason.

**Recruiter workflow and UI** (`frontend/`)
- Application page rebuilt: identity and CV separate from scores; compact stage timeline; actions and notes in a side panel; assessment shown as summary → each question with the candidate's answer, score and feedback → scoring detail; activity history collapsed. Openings: Publish / Save as draft / Close / Reopen buttons. Candidate pool shows application counts and CV-ownership warnings. CSV export now includes IDs, CV used, CV/overall scores, assessment state, decision and scoring version. Dashboard tiles have stated definitions and flag failed scoring.
- Design: same white surface and faint check, calmer type scale, rectangular status badges instead of pills, colour only for status. Demo-mode banner warns not to upload real CVs.

**Data repair** (`scripts/repair_identity.py`, run once on this copy; see ROLLBACK.md)
- Two real tester CVs ("Tester A" and "Tester B") moved from Priya Nair's record to new recruiter-managed records; Tester B's Backend application, assessment, answers and result moved with her CV. Priya's profile restored from her own CV (status *draft*: she must re-confirm once). All scores recalculated with match-v2; 8 earlier results kept in `match_history`. Backups: `backups/talentbridge-20261023-154042.db` + `uploads-…`, and `backups/before-repair-20261023-160013/`.

**Tests**: 26 new regression tests (`backend/tests/test_regressions.py`), 4 existing tests corrected (they uploaded Priya's CV to accounts named "Cand 0/1/2" — the exact bug). Total 126, all passing.
