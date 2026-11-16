#!/usr/bin/env python3
"""Start TalentBridge on your own computer.

    python run.py                          start the app (creates the database and demo accounts on first run)
    python run.py --load-demo-candidates   also create 6 fictional candidates with applications and scored skill tests
    python run.py --port 5055              use another port

Settings come from a file called .env next to this script (copy .env.example to .env) or from environment variables.
Everything runs on this computer. No account, API key or internet connection is needed for the default setup.
"""
import argparse, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))


def load_env(path):
    """Tiny .env reader (KEY=VALUE per line, # comments). Real environment variables win over the file.
    utf-8-sig: Windows Notepad may save the file with a byte-order mark."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if v[:1] in ('"', "'") and v[0] in v[1:]:
                v = v[1:v.index(v[0], 1)]                                # "quoted value" (may contain #)
            else:
                v = v.split(" #", 1)[0].strip()                          # KEY=value   # comment (as in .env.example)
            os.environ.setdefault(k.strip(), v)


def check_python():
    if sys.version_info < (3, 10):
        sys.exit(f"TalentBridge needs Python 3.10 or newer; this is {sys.version.split()[0]}.\n"
                 "See MAC_SETUP_GUIDE.md (Step 1) to install a current Python.")


def check_packages():
    missing = []
    for mod, pkg in (("flask", "Flask"), ("pdfplumber", "pdfplumber"), ("docx", "python-docx")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        sys.exit("Some required packages are not installed: " + ", ".join(missing) + ".\n"
                 "Run this once (inside the project folder), then try again:\n"
                 "    python3 -m pip install -r requirements.txt\n"
                 "If you made a virtual environment, activate it first: source .venv/bin/activate\n"
                 "(Windows: run setup_windows.bat once, then start_windows.bat)")


def utf8_console():
    """Windows consoles may use a legacy code page; never crash on a character it cannot show."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def main():
    utf8_console()
    check_python()
    load_env(os.path.join(ROOT, ".env"))
    import importlib.util                       # loaded by file path: importing the `app` package would read the settings too early
    for name in ("hosting",):
        spec = importlib.util.spec_from_file_location("tb_" + name, os.path.join(ROOT, "backend", "app", name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    hosted_on = mod.apply_host_defaults()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", 5050)))
    ap.add_argument("--load-demo-candidates", action="store_true", help="create fictional candidates, applications and scored assessments")
    ap.add_argument("--open", action="store_true", help="open the app in the default web browser once it is running")
    args = ap.parse_args()
    check_packages()
    if os.getenv("DATABASE_URL", "").startswith("postgres"):
        try:
            __import__("psycopg")
        except ImportError:
            sys.exit("DATABASE_URL points at PostgreSQL but the driver is missing. Run: python3 -m pip install -r requirements-postgres.txt")

    data = os.path.abspath(os.getenv("DATA_DIR", os.path.join(ROOT, "data")))
    os.makedirs(data, exist_ok=True)
    os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(data, "talentbridge.db"))
    os.environ.setdefault("UPLOAD_DIR", os.path.join(data, "uploads"))
    os.environ.setdefault("COOKIE_SECURE", "0")            # plain http://localhost (Safari refuses Secure cookies there)
    os.environ.setdefault("EMBEDDED_WORKER", "1")          # background processing runs inside this process
    os.environ.setdefault("PUBLIC_URL", f"http://localhost:{args.port}")
    os.environ.setdefault("ALLOWED_ORIGINS", f"http://localhost:{args.port},http://127.0.0.1:{args.port}")
    os.environ.setdefault("RATE_LIMIT_BACKEND", "db")
    os.environ.setdefault("DEMO_SEED", "1")

    # No AI settings given: use the free local model if this computer has it (nothing to configure, nothing to pay for).
    auto_note = None
    if os.getenv("TB_AUTO_AI", "1") != "0":
        spec = importlib.util.spec_from_file_location("tb_autoai", os.path.join(ROOT, "backend", "app", "autoai.py"))
        autoai = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(autoai)
        auto_note = autoai.configure()

    from app.config import Config
    from app import create_app, seed
    cfg = Config()
    app = create_app(cfg)
    demo = os.getenv("DEMO_SEED", "1") != "0"
    if demo:
        made = seed.seed_accounts(app.ctx)
        if made:
            print("Created demo accounts/openings:", ", ".join(made))
    if args.load_demo_candidates or os.getenv("DEMO_CANDIDATES") == "1":
        if not demo:
            sys.exit("Demo candidates need the demo recruiter; remove DEMO_SEED=0 or skip --load-demo-candidates.")
        for line in seed.seed_candidates(app, os.path.join(ROOT, "sample_data")):
            print("  demo:", line)

    from app import ai as ai_mod
    url = f"http://localhost:{args.port}"
    print("\n" + "=" * 66)
    print("  TalentBridge: Candidate Assessment & Talent Matching")
    print("=" * 66)
    if hosted_on:
        url = os.getenv("PUBLIC_URL", url)
        print(f"  Running on {hosted_on}.")
    print(f"  Open this address in your browser:  {url}")
    st = ai_mod.model_status(app.ctx.ai)
    if auto_note:
        print("  " + auto_note)
    if st is None:
        note = getattr(app.ctx.ai, "misconfigured", None)
        print(f"  AI engine: built-in rule-based engine (no AI model configured)" + (f"\n  WARNING {note}" if note else ""))
    elif st["reachable"] and st["installed"]:
        print(f"  AI engine: {st['provider']} model {st['model']} for {', '.join(st['tasks'])}; every AI result is checked by the rules")
        ai_mod.warm_up(app.ctx.ai)
    else:
        fix = ("start Ollama, or run: ollama pull " + st["model"]) if st["provider"] == "ollama" else (st.get("error") or "check OPENAI_BASE_URL / the API key")
        print(f"  AI engine: WARNING {st['provider']} model {st['model']} is not available ({fix})."
              " Results will be rule-based and labelled as such until it is.")
    from app import ocr
    o = ocr.describe(cfg)
    print("  Scanned CVs (OCR): " + (o["engine"] if o["enabled"] else "off - install Tesseract to read scanned PDFs (see the setup guide)"))
    em = app.ctx.mailer.describe()
    print(f"  E-mail: {em['provider']}" + ("" if em.get("real_delivery") else " (saved to data/outbox, not sent)") +
          (f", restricted to allowed recipients" if em.get("restricted") else ""))
    print(f"  Database: {'PostgreSQL' if app.ctx.db.pg else 'SQLite'}")
    print(f"  Data folder: {data}")
    if demo:
        print("  Demo logins (local demo only):")
        print("    Recruiter  recruiter@talentbridge.demo   DemoRecruiter#2026")
        print("    Admin      admin@talentbridge.demo       DemoAdmin#2026")
        print("    Candidate  register a new account in the browser, or use the demo ones if loaded:")
        print("               priya.nair@talentbridge.demo  DemoCandidate#2026")
    print("  Stop the app with Ctrl+C.")
    print("=" * 66 + "\n", flush=True)
    if args.open:
        import threading, webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        try:
            from waitress import serve
        except ImportError:
            serve = None
        if serve:
            serve(app, host=args.host, port=args.port, threads=8)
        else:
            app.run(host=args.host, port=args.port, threaded=True)
    except OSError as e:
        if getattr(e, "errno", None) in (48, 98, 10048) or "address already in use" in str(e).lower():
            sys.exit(f"Port {args.port} is already in use (is TalentBridge already running in another window?).\n"
                     f"Close the other window, or start on another port:  python run.py --port {args.port + 1}")
        raise


if __name__ == "__main__":
    main()
