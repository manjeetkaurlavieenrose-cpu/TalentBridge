# Windows setup guide (Windows 10 and 11, no programming experience needed)

Everything below is done by double-clicking files in the `TalentBridge` folder. The one-time setup takes about 5 minutes and
needs an internet connection. After that the app runs entirely on your computer.

## 1. Install Python (once)
1. Go to https://www.python.org/downloads/windows/ and download the latest **Python 3** installer ("Windows installer (64-bit)").
2. Run it. On the first screen **tick "Add python.exe to PATH"**, then click **Install Now**.
3. When it says "Setup was successful", close it.

> Already have Python? Any version 3.10 or newer works. The setup script checks this for you.

## 2. Unzip TalentBridge
Right-click the zip file → **Extract All…** → **Extract**. Open the extracted `TalentBridge` folder.
Use a normal folder such as *Documents* or *Desktop* (not inside the zip, and not a OneDrive "online-only" folder).

## 3. Run the setup (once)
Double-click **`setup_windows.bat`**. A black window shows the progress and ends with **Setup finished**. Press any key to close it.

If Windows shows *"Windows protected your PC"*: click **More info** → **Run anyway** (the file is a plain text script; you can
open it in Notepad to read it first).

## 4. Start the app
| To… | Double-click |
|---|---|
| Use the app | **`start_windows.bat`** |
| Show a demo with fictional candidates and scored assessments | **`start_demo_windows.bat`** (kept in `demo-data`, separate from real data) |
| Check that everything works on this computer | **`test_windows.bat`** |

Your browser opens **http://localhost:5050** automatically. **Keep the black window open** while you use the app; closing it
(or pressing Ctrl+C in it) stops the app. Nothing is lost when you stop: start it again the same way.

The first time, Windows Firewall may ask whether Python may use the network. **Cancel / leave unticked is fine**: the app
only listens on this computer.

**Sign-in for the demo** (also shown on the sign-in page with "Fill in" buttons):
- Recruiter: `recruiter@talentbridge.demo` / `DemoRecruiter#2026`
- Admin: `admin@talentbridge.demo` / `DemoAdmin#2026`
- Candidate (demo copy): `priya.nair@talentbridge.demo` / `DemoCandidate#2026`, or register a new candidate in the browser.

Fictional CVs to try are in the `sample_data` folder.

## 5. Turn on the AI model (recommended, free)
1. Download **Ollama for Windows** from https://ollama.com/download and install it. It runs in the background (llama icon near the clock).
2. Open **Command Prompt** (press the Windows key, type `cmd`, Enter) and run:

       ollama pull qwen2.5:3b

   (1.9 GB, one time. On a computer with 16 GB of memory, `qwen2.5:7b` gives better questions and scoring.)
3. Open the `.env` file in the TalentBridge folder with Notepad (right-click → Open with → Notepad) and add these lines:

       AI_PROVIDER=ollama
       OLLAMA_MODEL=qwen2.5:3b

4. Save, close the black TalentBridge window and start `start_windows.bat` again. The window now says
   `AI engine: ollama model qwen2.5:3b for assessment, evaluation, profile, summary`.

What the model does: reads each CV alongside the parser (only facts found in the CV are kept), writes the fit summary and
interview questions, writes each candidate's assessment questions, and scores every answer, including a check for technical errors.
Each result shows the engine that produced it, and the rule-based engine takes over automatically if Ollama is not running.

**Other free options** instead of Ollama (set in `.env`, see the examples in `.env.example`):
- **LM Studio** (https://lmstudio.ai): download a model, open the *Developer* tab, **Start Server**, then
  `AI_PROVIDER=openai`, `OPENAI_BASE_URL=http://127.0.0.1:1234/v1`, `OPENAI_MODEL=<the model name LM Studio shows>`.
- A hosted free tier (Groq, OpenRouter, Google Gemini): `AI_PROVIDER=openai` with that service's `OPENAI_BASE_URL`, `OPENAI_MODEL`
  and `OPENAI_API_KEY`. Only use hosted services with fictional data unless your institution has approved them.

Optional, meaning-based similarity between CV and job: run `ollama pull nomic-embed-text` and add `SEMANTIC_MATCH=1` to `.env`.

## 6. Read scanned CVs (optional, free)
1. Download the Tesseract installer from https://github.com/UB-Mannheim/tesseract/wiki (the 64-bit `.exe`).
2. Install with the default settings (`C:\Program Files\Tesseract-OCR`). TalentBridge finds it there automatically.
3. Restart TalentBridge. The window says `Scanned CVs (OCR): tesseract`.

Scanned CVs are then read with OCR, and the profile is marked "read with OCR" so the candidate checks it before confirming.
No admin rights? Run `.venv\Scripts\python -m pip install -r requirements-ocr.txt` in the folder instead (a pure-Python OCR engine).

## 7. Check it works: `test_windows.bat`
Double-click **`test_windows.bat`**. It runs:
1. the automated test suite (about 170 tests, 1–3 minutes), and
2. an end-to-end check that starts the real app on a spare port with a temporary data folder, signs in, registers a candidate,
   uploads a sample CV, applies, takes and submits the assessment, and checks the recruiter sees the scored result.

It ends with **ALL CHECKS PASSED**. A full log is saved to `test-results-windows.txt` (send this file if you need help).
Your own `data` folder is never touched. If you turned on the AI model, the end-to-end check uses it too.

## Where is my data? Backups
Everything is in the `data` folder (database and uploaded CVs). To back up: stop the app and copy the `data` folder.
To restore: stop the app and put the copy back. See ROLLBACK.md for details.

## Command-line equivalents (optional)
In Command Prompt or PowerShell, inside the TalentBridge folder:

    setup_windows.bat dev                       one-time setup, plus the test tools
    .venv\Scripts\python run.py --open          start (add --port 5051 to use another port)
    .venv\Scripts\python run.py --load-demo-candidates --open
    cd backend && ..\.venv\Scripts\python -m unittest discover -s tests -t .
    .venv\Scripts\python scripts\smoke_test.py

## If something goes wrong
| What you see | Fix |
|---|---|
| `Python was not found` | Install Python (step 1) with **Add python.exe to PATH** ticked, then run `setup_windows.bat` again. |
| Typing `python` opens the Microsoft Store | Settings → Apps → Advanced app settings → **App execution aliases** → turn off *python.exe* and *python3.exe*, then run setup again. |
| `Port 5050 is already in use` | TalentBridge is already open in another black window: use that one, or close it. Or run `start_windows.bat --port 5051`. |
| The page is blank or keeps loading | Make sure the black window is still open, then reload. Use `http://localhost:5050` (not `https://`). |
| `pip` errors about SSL or a proxy (university network) | Try another network once for the setup, or ask IT for the proxy setting (`set HTTPS_PROXY=...` before running setup). |
| Setup fails with "Access is denied" | The folder is read-only or synced by OneDrive. Move the TalentBridge folder to `C:\Users\<you>\TalentBridge` and run setup again. |
| The AI line says the model is not available | Start Ollama from the Start menu, run `ollama pull qwen2.5:3b`, then restart TalentBridge. Results made meanwhile are labelled rule-based. |
| CV upload says it looks like a scan | Install Tesseract (step 6), or upload a text-based PDF / DOCX. |
| Windows SmartScreen blocks a `.bat` file | **More info** → **Run anyway**. |

To start completely fresh: stop the app, delete the `.venv` folder (and `data` if you want to remove all records), run setup again.
