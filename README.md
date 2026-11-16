# TalentBridge — Candidate Assessment & Talent Matching

> **New here, or not a developer?** Open **START_HERE.html** in this folder (double-click it). It explains in plain words how to start the app, try the demo, switch on the free AI and share the package.

## Put it online (a link anyone can open)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/OWNER/REPO)
[![tests](https://github.com/OWNER/REPO/actions/workflows/tests.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/tests.yml)

1. Click **Deploy to Render** above, sign in with your GitHub account, and click **Apply** (or **Deploy**). After a few minutes Render shows
   your link, for example `https://talentbridge-xxxx.onrender.com`. Open it: the demo logins are on the sign-in page.
2. That is all. The free plan sleeps when nobody uses it (the first visit then takes about a minute) and restarts with fresh demo data.

**Any other server with Docker:** `docker run -p 8080:8000 -v talentbridge-data:/data -e DEMO_SEED=1 -e DEMO_CANDIDATES=1 ghcr.io/owner/repo:latest`
then open `http://SERVER-ADDRESS:8080`. The image is built and checked by GitHub on every upload (see the Actions tab).
More options, real-use settings and limits: [docs/DEPLOY_ANYWHERE.md](docs/DEPLOY_ANYWHERE.md).


A complete, working hiring workflow: a candidate uploads a CV, the app reads it into a profile, matches it to an opening with a
transparent explanation, writes a tailored work-sample assessment, scores the answers against a visible rubric, and a recruiter
reviews everything on one dashboard and records the decision.

**Runs on your own Windows or Mac computer and costs nothing.** AI runs locally through Ollama (free), or through LM Studio,
a hosted free tier, or the Claude API. All people and companies in the demo are fictional.

## Quick start
| | Windows | Mac |
|---|---|---|
| 1. Install Python 3.10+ | python.org, tick **Add python.exe to PATH** | python.org installer |
| 2. One-time setup | double-click `setup_windows.bat` | double-click `setup_mac.command` |
| 3. Start | double-click `start_windows.bat` | double-click `start_mac.command` |
| Demo with sample data | `start_demo_windows.bat` | `start_demo_mac.command` |
| Check everything works | `test_windows.bat` | `test_mac.command` |

The browser opens **http://localhost:5050**. Step-by-step guides: **[WINDOWS_SETUP_GUIDE.md](WINDOWS_SETUP_GUIDE.md)** and
**[MAC_SETUP_GUIDE.md](MAC_SETUP_GUIDE.md)**. A presenter's walkthrough is in **[DEMO_SCRIPT.md](DEMO_SCRIPT.md)**.

Demo logins (shown on the sign-in page): recruiter `recruiter@talentbridge.demo` / `DemoRecruiter#2026`, admin
`admin@talentbridge.demo` / `DemoAdmin#2026`, candidate `priya.nair@talentbridge.demo` / `DemoCandidate#2026`.
Fictional CVs are in `sample_data/`. Keep demo data and real data in separate folders (`DATA_DIR=…`).

## Turn on the AI (free, 5 minutes)
1. Install Ollama (https://ollama.com, Windows/Mac/Linux) and run `ollama pull qwen2.5:3b` (or `qwen2.5:7b` on a 16 GB machine).
2. In `.env`: `AI_PROVIDER=ollama` and `OLLAMA_MODEL=qwen2.5:3b`. Restart. The start-up banner confirms the model is found.

Alternatives, same `.env` file: `AI_PROVIDER=openai` with `OPENAI_BASE_URL` / `OPENAI_MODEL` / `OPENAI_API_KEY` for LM Studio, Jan,
llama.cpp, vLLM, Groq, OpenRouter or Google Gemini; or `AI_PROVIDER=anthropic` with `ANTHROPIC_API_KEY` for Claude
(`pip install -r requirements-anthropic.txt`). Examples for each are in `.env.example`.

## What it does
| Step | How it works |
|---|---|
| **CV upload** | PDF or DOCX, type checked from file contents, 5 MB cap. Two-column layouts are read column by column. Scanned (image-only) PDFs are read with OCR when Tesseract is installed. Each CV is checked against the account it is uploaded to; a CV naming someone else is held and flagged, never merged. Every application keeps the CV and profile it was made with. |
| **AI CV reading** | The rule-based parser finds sections, roles, dates, education, skills and projects. The AI model reads the same CV and proposes anything missed (tools outside the built-in skills list, roles in unusual layouts, dates, institutions). **Each proposed fact is kept only if it is found in the CV text**, and the profile lists exactly what the AI added. The candidate reviews, corrects and confirms. |
| **Matching** | One documented calculation (`match-v2`) for every screen and the CSV: required skills 35, preferred 10, experience 15, education 10, other requirements 10 (rescaled to what the opening uses); overall = 0.8 × CV match + 0.2 × assessment once scored. Evidence is labelled *shown in use / partial / not found / not verifiable*, so every number can be explained. Optional meaning-based similarity from the AI server's embeddings (`SEMANTIC_MATCH=1`). |
| **Fit summary** | The AI writes a recruiter summary, strengths, gaps, risks and interview questions specific to the candidate's CV. |
| **Assessment** | Four questions written for this opening and this candidate's own experience, each with a private rubric. Model-written questions are checked (distinct, self-contained, no reference to data the candidate never sees) and rewritten once if needed. Auto-sent when the opening has that option on. Drafts autosave and can never overwrite a submission. |
| **Scoring** | Each answer is scored separately against its rubric; the AI also checks it for technical errors and lists them for the recruiter. A transparent rule-based rubric (with synonym recognition) cross-checks every AI score, and large disagreements are flagged. Blank, too-short, "I don't know" and keyboard-mashing answers are labelled and score 0 on every engine. A scoring failure shows as *Needs review* (answers kept, retry available), never as 0. |
| **Recruiter** | Overview, openings (create/edit/publish/close, suggest skills from a pasted ad), applicants, application detail with answers next to their questions, candidate pool with filters, side-by-side compare (2–5), review decisions, notes, CSV export, audit log. |
| **Safety** | Roles and organisation scoping, CSRF, scrypt passwords, rate limits, lockout, audit log, engine label on every result. The system never shortlists or rejects anyone: a person does. |
| **E-mail** | Registration, assessment ready, assessment submitted. File outbox by default; Resend, Brevo or SMTP with an allow-list (see below). |

### AI engines at a glance
| Setting | Model | Cost | Notes |
|---|---|---|---|
| `AI_PROVIDER=ollama` | qwen2.5:3b / 7b or any Ollama model | free, local | recommended for laptops and the Docker deployment |
| `AI_PROVIDER=openai` | LM Studio, Jan, llama.cpp, vLLM | free, local | any OpenAI-compatible server |
| `AI_PROVIDER=openai` | Groq, OpenRouter, Gemini | free tiers | hosted: fictional data unless approved |
| `AI_PROVIDER=anthropic` | `claude-opus-5-5` (`AI_MODEL`) | paid | structured outputs through the official SDK |
| `AI_PROVIDER=local` (default) | built-in rules | free, instant | also the automatic fallback for every engine |

`AI_TASKS=profile,summary,assessment,evaluation` chooses what the model does. Every stored result records the engine that produced
it (for example `ollama:qwen2.5:3b`); `/api/v1/health` reports whether the model is reachable.

## Scanned CVs (OCR)
Install Tesseract (free): Windows — the UB Mannheim installer (see the Windows guide, step 6); Mac — `brew install tesseract`;
Linux — `apt install tesseract-ocr`. It is found automatically. Pure-pip alternative: `pip install -r requirements-ocr.txt`.
`OCR=off` disables it; `OCR_LANG=eng+hin` adds languages.

## E-mail
- Default `EMAIL_PROVIDER=file`: messages are saved in `data/outbox/*.eml` (works offline, ideal for demos).
- Real delivery (free tiers): **Resend** (`RESEND_API_KEY`, `EMAIL_FROM`), **Brevo** (`BREVO_API_KEY`, `EMAIL_FROM`), or SMTP.
- Real mail only goes to `EMAIL_ALLOWED_RECIPIENTS`; everyone else is held in the outbox. `EMAIL_ALLOW_ALL=1` only with consent.
- Test: `python scripts/send_test_email.py --to you@example.org`. Keys are never logged or shown.

## PostgreSQL (optional; SQLite is the default)
- Point `DATABASE_URL` at an empty database and install the driver (`pip install -r requirements-postgres.txt`).
- Copy existing SQLite data: `python scripts/sqlite_to_postgres.py --to <url>` (verifies row counts, refuses a non-empty target).
- Tests on PostgreSQL: `TB_TEST_DATABASE_URL=postgresql://.../talentbridge_test python -m unittest discover -s tests -t .`

## Sharing a URL with other devices
For an HTTPS address that opens on any phone, tablet or computer, deploy the Docker Compose stack (web, worker, PostgreSQL,
Ollama, Caddy HTTPS) on a lab server or a free Oracle Cloud VM: follow [HANDOVER.md](HANDOVER.md) and [docs/DEPLOY.md](docs/DEPLOY.md).
The image includes Tesseract for scanned CVs; PostgreSQL, uploaded CVs and Ollama stay private.

## Start, stop, test
- Start: the start script for your system, or `python run.py --open` inside the activated `.venv`. Options: `--port 5051`, `--load-demo-candidates`.
- Stop: close the window or press Ctrl+C. Data, drafts and queued scoring survive restarts.
- Tests: `test_windows.bat` / `test_mac.command`, or `cd backend && python -m unittest discover -s tests -t .` (167 tests) plus
  `python scripts/smoke_test.py` (starts the real app and runs the whole candidate → recruiter flow).
- Continuous testing: `.github/workflows/tests.yml` runs everything on **Windows, macOS and Linux** (Python 3.10 and 3.13) on every
  push, including the double-click Windows scripts.
- Back up / restore / repair misfiled CVs: [ROLLBACK.md](ROLLBACK.md).

## Project layout
    run.py                  one-command launcher (.env loader, demo seed, waitress, --open)
    setup_/start_/start_demo_/test_  windows.bat and mac.command   double-click scripts
    backend/app/            Flask API: routes, pipeline (task queue), ai (providers), assist (verified AI CV reading),
                            cv_parser, extract (+ columns), ocr, matching, question_bank, answer_scorer, similarity, seed
    backend/tests/          automated tests
    frontend/               plain ES-module UI (no build step)
    sample_data/            fictional CVs (+ files the app should reject)
    scripts/                smoke_test.py, repair_identity.py, sqlite_to_postgres.py, send_test_email.py, make_sample_cvs.py
    docs/DEPLOY.md          production deployment
    WINDOWS_SETUP_GUIDE.md  MAC_SETUP_GUIDE.md  DEMO_SCRIPT.md  HANDOVER.md  AUDIT_REPORT.md  ROLLBACK.md  CHANGES.md
