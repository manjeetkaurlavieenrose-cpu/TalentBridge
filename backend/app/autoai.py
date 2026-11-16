"""Zero-setup AI: use the free local model when it is there, without anyone editing a settings file.

Called by run.py when AI_PROVIDER is not set. Ollama (https://ollama.com) is free, needs no account and runs on this computer.
  Ollama running with a usable model   -> the app uses it.
  Ollama installed but not running     -> it is started.
  Ollama running, model not downloaded -> the model is downloaded in the background (about 1.9 GB, once); results are
                                          rule-based, and labelled as such, until the download has finished.
  No Ollama                            -> the built-in rule-based engine; the banner says how to get the free AI.
Nothing here can stop the app from starting: every step is best effort.
"""
import json, os, shutil, subprocess, sys, threading, time, urllib.request

EMBED_HINTS = ("embed", "bge-", "minilm", "e5-")


def _get(url, timeout=1.5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def installed_models(url, timeout=1.5):
    """Names of the models the Ollama server at `url` has, or None when no server answers."""
    try:
        return [m.get("name") for m in _get(url.rstrip("/") + "/api/tags", timeout).get("models", []) if m.get("name")]
    except Exception:
        return None


def pick_model(names, preferred):
    """The preferred model if present (with or without ':latest'); otherwise the first installed chat model."""
    if preferred in names or (":" not in preferred and preferred + ":latest" in names):
        return preferred
    base = preferred.split(":")[0]
    same = [n for n in names if n.split(":")[0] == base]
    chat = [n for n in names if not any(h in n.lower() for h in EMBED_HINTS)]
    return (same or chat or [None])[0]


def find_ollama():
    exe = shutil.which("ollama")
    if exe:
        return exe
    for p in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"), "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama",
              "/Applications/Ollama.app/Contents/Resources/ollama"):
        if os.path.exists(p):
            return p
    return None


def start_server(exe, url, wait=8):
    """Start `ollama serve` in the background and wait until it answers. -> True when it is up."""
    try:
        kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {"start_new_session": True}
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, **kw)
    except Exception:
        return False
    end = time.time() + wait
    while time.time() < end:
        if installed_models(url, 1) is not None:
            return True
        time.sleep(0.5)
    return False


def pull_in_background(url, model, log=print):
    """Download the model through the server's own API. The app keeps working (rule-based) meanwhile."""
    def go():
        try:
            req = urllib.request.Request(url.rstrip("/") + "/api/pull", json.dumps({"model": model, "stream": True}).encode(),
                                         {"content-type": "application/json"})
            last = 0
            with urllib.request.urlopen(req, timeout=3600) as r:
                for line in r:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if d.get("error"):
                        log(f"  AI model download failed: {d['error']}")
                        return
                    if d.get("total") and d.get("completed") and time.time() - last > 20:
                        last = time.time()
                        log(f"  AI model download: {100 * d['completed'] // d['total']}%")
            log(f"  AI model {model} is ready. New CVs, tests and answers now use it.")
        except Exception as e:
            log(f"  AI model download stopped ({type(e).__name__}). It is tried again the next time the app starts.")
    t = threading.Thread(target=go, name="tb-ai-pull", daemon=True)
    t.start()
    return t


def configure(env=os.environ, log=print, start=True, pull=True):
    """Decide the AI settings when none were given. Sets AI_PROVIDER / OLLAMA_MODEL in `env`; returns a one-line explanation."""
    if env.get("AI_PROVIDER"):
        return None                                  # the person chose: nothing is decided for them
    url = env.get("OLLAMA_URL", "http://127.0.0.1:11434")
    preferred = env.get("OLLAMA_MODEL", "qwen2.5:3b")
    names = installed_models(url)
    if names is None and start:
        exe = find_ollama()
        if exe and start_server(exe, url):
            names = installed_models(url)
    if names is None:
        return ("Free AI not found on this computer: using the built-in rule-based engine. To switch the AI on, install Ollama "
                "(free, no account) from https://ollama.com/download and start TalentBridge again.")
    model = pick_model(names, preferred)
    env["AI_PROVIDER"] = "ollama"
    if model:
        env["OLLAMA_MODEL"] = model
        return f"Free local AI found (Ollama, model {model}): switched on automatically."
    env["OLLAMA_MODEL"] = preferred
    if pull:
        pull_in_background(url, preferred, log)
        return (f"Ollama is installed; downloading the free AI model {preferred} in the background (about 1.9 GB, once). "
                "Results are rule-based, and labelled so, until it is ready.")
    return f"Ollama is installed but has no model yet. Run: ollama pull {preferred}"
