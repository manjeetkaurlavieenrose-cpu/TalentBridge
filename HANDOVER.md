# TalentBridge professor handover

> **New here, or not a developer?** Open **START_HERE.html** in this folder (double-click it). It explains in plain words how to start the app, try the demo, switch on the free AI and share the package.

## What this project is

TalentBridge is a responsive web application for candidate CV upload, profile confirmation, job matching, work-sample assessments, and recruiter review. Candidates and recruiters use the same URL in a modern browser. The repository does not contain native iOS or Android apps.

With Ollama and `qwen2.5:3b` switched on, the AI model reads each CV alongside the rule-based parser (only facts found in the CV text are kept), writes the fit summary and interview questions, writes job- and CV-grounded assessment questions, and scores each answer against its rubric, including a check for technical errors. The match score is a documented calculation, so every number can be explained. Each result names the engine that produced it and keeps the underlying answers and evidence; a human recruiter makes every decision. Scanned CVs are read with OCR (Tesseract, included in the Docker image). E-mail is kept in a file outbox until a provider account (Resend/Brevo/SMTP) is added.

## Two ways to present it

### Quick local presentation

On a Mac or Windows computer with Python 3.10+, unzip the package and run the setup script for that computer. This launches the app only on that computer; it is not an always-on cross-device URL.

**Mac:** open Terminal in the unzipped `TalentBridge` folder and run:

```sh
./setup_mac.command
source .venv/bin/activate
python3 run.py --load-demo-candidates
```

**Windows:** double-click `setup_windows.bat`, then `start_demo_windows.bat` (demo data) or `start_windows.bat`. Run `test_windows.bat` once to confirm everything works on that computer. Full instructions: [WINDOWS_SETUP_GUIDE.md](WINDOWS_SETUP_GUIDE.md).

The browser opens `http://localhost:5050`. Keep the terminal window open while presenting. The page shows fictional demo sign-ins; the recruiter login is `recruiter@talentbridge.demo` / `DemoRecruiter#2026`. Do not upload real CVs to the demo.

For the AI features, install Ollama separately, download the model with `ollama pull qwen2.5:3b`, and add these settings to `.env` before starting the app:

```text
AI_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:3b
```

All four AI tasks are on by default (`AI_TASKS=profile,summary,assessment,evaluation`).

Ollama must be running on the same computer as the app for this local mode. Read [README.md](README.md) and [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for more detail.

### Verify Ollama is actually being used

1. While the app is running, open `http://localhost:5050/api/v1/health`. Confirm `ai_model.reachable` and `ai_model.installed` are `true`, and `ai_model.model` is `qwen2.5:3b`.
2. Use the seeded fictional recruiter account to open a candidate application. The fit summary and assessment should say **AI-assisted (local model qwen2.5:3b)**. Submit an assessment and open its results; the evaluation should show the same model name.
3. If a result instead says **Rule-based (AI model was unavailable)**, Ollama was not used for that result. Confirm Ollama is still running and restart the app after correcting `.env`. Existing records keep the engine that created them; rerun the demo in a fresh data folder to generate new AI results.

This check exercises Ollama for CV reading, the summary, question generation and answer evaluation. On the candidate's profile, "Read by" shows `Rules + AI reader (ollama:qwen2.5:3b)` when the model added verified facts. `scripts/smoke_test.py` (or `test_windows.bat` / `test_mac.command`) runs the whole flow against the running configuration and prints which engine wrote and scored the assessment.

### Shared professor/candidate URL with no new hosting bill

The first choice is still an approved lab/university server. If none exists, the closest public no-cost option is Oracle Cloud Infrastructure's Always Free Ampere VM. Its current Always Free allowance includes 2 OCPUs, 12 GB RAM, and block storage; that is enough on paper for the app and the 1.9 GB qwen2.5:3b model, though CPU AI may be slow. Oracle requires identity/payment-card verification for most sign-ups, has capacity limits, and may reclaim Always Free compute if it is judged idle over a 7-day period. So treat this as a free demonstration host, not guaranteed availability. See [the detailed limitations and deployment steps](docs/DEPLOY.md#free-hosting-reality).

After the server is created, follow [docs/DEPLOY.md](docs/DEPLOY.md) to run the Compose stack. A free DuckDNS subdomain can supply the public hostname for Caddy HTTPS if the project owner accepts that third-party DNS dependency. Once deployed and health-checked, share only the HTTPS URL and professor's account. Never share `.env.production` or its database credentials.

If Oracle sign-up, the card verification, or its availability terms are not acceptable, the fallback is to run the app on a computer that stays on. Other devices can use it only while that computer and network are available; an institution-approved VPN or network route may be needed. Do not make a personal laptop or router publicly reachable for real CV data.

The source package is ready for deployment, but it is **not yet hosted**: the project owner must create the Oracle account/VM and DuckDNS name, then Docker Compose must be run, the model downloaded, and the health endpoint verified. Docker is not installed in the development environment used for this handover, so the container stack was not run here. Oracle Free is a best-effort demo host with the capacity, signup, and idle-reclamation caveats above, not guaranteed availability; see [the deployment guide](docs/DEPLOY.md#free-hosting-reality).

## Acceptance checklist before handover

- [ ] Public HTTPS URL opens from a device outside the server's network.
- [ ] `/api/v1/health` reports `ok: true`, `ai_model.reachable: true`, `ai_model.installed: true`, and `qwen2.5:3b`.
- [ ] Ollama port 11434 and PostgreSQL port 5432 are not exposed publicly.
- [ ] Demo mode is off; administrator password is unique; no test/demo accounts or real CVs are included.
- [ ] Register a fictional candidate, upload a fictional CV, confirm extracted profile, apply, draft and submit an assessment.
- [ ] Register/sign in as recruiter, create a job, review the candidate's answers and evidence, and record a human decision.
- [ ] Restart the stack and confirm records, assessment results, and uploaded CV remain available.
- [ ] Test the shared URL in current Safari, Chrome, and Edge, plus iOS Safari and Android Chrome at phone/tablet/desktop sizes.
- [ ] `/api/v1/health` reports `ocr.enabled: true` (Tesseract) on the server.
- [ ] Explain to the professor that e-mail stays in the outbox until a provider account is added, and that real candidate data requires institutional privacy/retention approval.

See [AUDIT_REPORT.md](AUDIT_REPORT.md) for test evidence and scope limits.
