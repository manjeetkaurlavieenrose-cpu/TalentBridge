# Mac setup guide (no programming experience needed)

You will type a few commands into **Terminal** (press ⌘+Space, type "Terminal", press Enter). Copy each line exactly, press Enter, and wait for it to finish before the next.

## 1. One-time: check Python
    python3 --version
You need **3.10 or newer**. If you see "command not found" or an older number, install Python from https://www.python.org/downloads/ (the macOS installer), then close and reopen Terminal.

## 2. Unzip and open the folder
Unzip `talentbridge.zip` (double-click it). Then in Terminal type `cd ` (with a space), drag the unzipped **talentbridge** folder onto the Terminal window, and press Enter.

## 3. One-time: install the app's parts
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
This takes a minute or two and needs internet. `(.venv)` appears at the start of the line when it worked.

## 4. Start it
    python3 run.py --load-demo-candidates
Wait for the line `Running on http://127.0.0.1:5050`, then open **http://localhost:5050** in Safari or Chrome. Leave Terminal open while you use the app.
- Next time you only need: `cd` into the folder, `source .venv/bin/activate`, `python3 run.py` (skip `--load-demo-candidates`: the demo data is already saved).
- Or double-click **start_mac.command** in Finder. The first time macOS may block it: right-click → Open → Open.

## 5. Stop it
Click the Terminal window and press **Control+C**.

## Restart and test
- Restart: press Control+C, then run `python3 run.py` again. Nothing is lost.
- Check everything still works (optional, needs `pip install -r requirements-dev.txt` once): `cd backend` then `python3 -m unittest discover -s tests -t .` — it should end with `OK`.
- Back up: stop the app and copy the `data` folder (see ROLLBACK.md).

## Logins
The sign-in page lists them with "Fill in" buttons. Recruiter: `recruiter@talentbridge.demo` / `DemoRecruiter#2026`.

## Where is my data?
In the `data` folder inside the project (database + uploaded CVs). Copy it to back up. For a clean demo without touching it, start with `DATA_DIR=./demo-data python3 run.py --load-demo-candidates`.

## If something goes wrong
| Problem | Fix |
|---|---|
| `python3: command not found` | Install Python (step 1). |
| `pip: externally-managed-environment` | You skipped step 3's `source .venv/bin/activate`. Run it first. |
| Page won't load | Use port **5050** (not 5000: macOS uses 5000 for AirPlay). Make sure Terminal still shows the app running. |
| "Address already in use" | Another copy is running. Press Control+C in the other Terminal, or run `python3 run.py --port 5051` and open that port. |
| Safari keeps signing you out | Use `http://localhost:5050` exactly (not an IP address). If it persists, try Chrome and tell me. |
| CV upload says it looks like a scan | Install Tesseract (`brew install tesseract`) and restart, or use a text-based PDF or DOCX. |

## Shortcut: double-click scripts
`setup_mac.command` (once), then `start_mac.command` (opens the browser), `start_demo_mac.command` (fictional demo data in
`demo-data/`) or `test_mac.command` (tests + end-to-end check). The first time, macOS may block them: right-click → Open → Open.

## Recommended: the AI model (Ollama, free)
Install Ollama from https://ollama.com, run `ollama pull qwen2.5:3b` (or `qwen2.5:7b` with 16 GB of memory), and add to `.env`:

    AI_PROVIDER=ollama
    OLLAMA_MODEL=qwen2.5:3b

Restart. The banner shows `AI engine: ollama model qwen2.5:3b for assessment, evaluation, profile, summary`. The model reads CVs
(verified against the CV text), writes the fit summary and the assessment questions, and scores answers with an error check; the
rule-based engine cross-checks every score and takes over automatically if Ollama is not running. LM Studio, hosted free tiers
and Claude are also supported: see `.env.example`.

## Optional: scanned CVs (OCR)
`brew install tesseract` (needs Homebrew, https://brew.sh), then restart. The banner shows `Scanned CVs (OCR): tesseract`.
