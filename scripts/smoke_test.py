#!/usr/bin/env python3
"""End-to-end check of a real TalentBridge server, the way a person uses it. Works on Windows, macOS and Linux.

    python scripts/smoke_test.py            start a fresh copy on a free port with a temporary data folder, test it, stop it
    python scripts/smoke_test.py --url http://localhost:5050   test a copy that is already running (creates a test candidate)

It checks: the server starts; the page and its scripts load with the right content types; demo sign-in works; a candidate can
register, upload a fictional sample CV, see it read into a profile, confirm it, apply, receive an assessment, answer and submit
it; the answers get scored; the recruiter sees the application with its score. Your own data folder is never touched.
"""
import argparse, http.cookiejar, json, os, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "sample_data", "cv_priya_nair_data_analyst.pdf")
ANSWER = ("First I would agree the goal with the manager and check which metrics matter, for example revenue, conversion and "
          "footfall by region. Then I would join the sales and store tables, filter to the period, group by region and compare "
          "the totals week on week. I would validate the numbers against the finance report before sharing, and present the "
          "findings in a short dashboard with one clear recommendation.")


class Session:
    def __init__(self, base):
        self.base, self.csrf = base.rstrip("/"), None
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def req(self, method, path, data=None, ctype="application/json", raw=False):
        h = {"Content-Type": ctype} if data is not None else {}
        if self.csrf:
            h["X-CSRF-Token"] = self.csrf
        body = json.dumps(data).encode() if (data is not None and ctype == "application/json") else data
        r = urllib.request.Request(self.base + path, body, h, method=method)
        try:
            with self.op.open(r, timeout=60) as resp:
                payload = resp.read()
                return resp.status, (payload if raw else json.loads(payload or b"null")), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null"), e.headers

    def get(self, p, **k): return self.req("GET", "/api/v1" + p, **k)
    def post(self, p, d=None): return self.req("POST", "/api/v1" + p, d if d is not None else {})
    def patch(self, p, d): return self.req("PATCH", "/api/v1" + p, d)

    def login(self, email, pw):
        st, b, _ = self.post("/auth/login", {"email": email, "password": pw})
        if st == 200:
            self.csrf = b["csrf_token"]
        return st

    def upload(self, path):
        boundary = uuid.uuid4().hex
        with open(path, "rb") as f:
            data = f.read()
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{os.path.basename(path)}\"\r\n"
                "Content-Type: application/pdf\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        return self.req("POST", "/api/v1/me/cvs", body, ctype=f"multipart/form-data; boundary={boundary}")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def wait(fn, seconds, what):
    end = time.time() + seconds
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.5)
    raise AssertionError(f"timed out after {seconds}s waiting for {what}")


def run_checks(base, log):
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        log(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"  ({detail})"))
        return cond

    anon = Session(base)
    st, h, _ = anon.get("/health")
    check("server answers /api/v1/health", st == 200 and h.get("ok"), h)
    log(f"      AI: {h.get('ai_provider')} | model: {h.get('ai_model')} | OCR: {h.get('ocr')} | database: {h.get('database')}")
    st, page, hd = anon.req("GET", "/", raw=True)
    check("sign-in page loads", st == 200 and b"<script" in page, st)
    st, _, hd = anon.req("GET", "/js/app.js", raw=True)
    check("app scripts are served as JavaScript (needed on Windows)", st == 200 and "javascript" in hd.get("Content-Type", ""), hd.get("Content-Type"))
    st, _, hd = anon.req("GET", "/styles.css", raw=True)
    check("stylesheet is served as CSS", st == 200 and "text/css" in hd.get("Content-Type", ""), hd.get("Content-Type"))

    rec = Session(base)
    if not check("demo recruiter can sign in", rec.login("recruiter@talentbridge.demo", "DemoRecruiter#2026") == 200, "is DEMO_SEED=0?"):
        return ok
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.org"
    cand = Session(base)
    st, b, _ = cand.post("/auth/register/candidate", {"email": email, "password": "Smoke-test-pass-9", "full_name": "Priya Nair"})
    check("candidate can register", st == 201, b)
    check("candidate can sign in", cand.login(email, "Smoke-test-pass-9") == 200)
    st, b, _ = cand.upload(SAMPLE)
    check("CV upload accepted", st == 201, b)

    def ready():
        _, p, _ = cand.get("/me/profile")
        stage = (p.get("cvs") or [{}])[0].get("stage")
        return p if stage in ("ready", "failed") else None
    p = wait(ready, 240, "the CV to be read")
    check("CV read into a profile", p["cvs"][0]["stage"] == "ready", p["cvs"][0])
    prof = p.get("profile") or {}
    check("profile has name, roles and skills", prof.get("full_name") == "Priya Nair" and prof.get("work_history") and prof.get("skills"),
          {k: prof.get(k) for k in ("full_name",)})
    log(f"      CV read by: {prof.get('extracted_by')}; {len(prof.get('skills', []))} skills, {len(prof.get('work_history', []))} roles")
    st, b, _ = cand.patch("/me/profile", {"confirm": True})
    check("profile confirmed", st == 200, b)

    _, jobs, _ = cand.get("/jobs?limit=50")
    job = next((j for j in jobs.get("data", []) if "analyst" in j["title"].lower()), (jobs.get("data") or [None])[0])
    if not check("an open job is listed", job, jobs):
        return ok
    st, b, _ = cand.post(f"/jobs/{job['id']}/apply")
    check(f"applied to '{job['title']}'", st == 201, b)
    aid = b.get("id") if isinstance(b, dict) else None

    def assessment():
        _, apps, _ = cand.get("/me/applications")
        a = next((x for x in apps.get("data", []) if x["id"] == aid), {})
        return a.get("open_assessment_id")
    try:
        sid = wait(assessment, 300, "the assessment to be written")
    except AssertionError as e:
        check("assessment sent automatically", False, e)
        return ok
    check("assessment sent automatically", sid)
    cand.post(f"/assessments/{sid}/start")
    _, s, _ = cand.get(f"/assessments/{sid}")
    qs = s["task"]["questions"]
    log(f"      {len(qs)} questions")
    st, b, _ = cand.post(f"/assessments/{sid}/submit", {"answers": {q["id"]: ANSWER for q in qs}})
    check("answers submitted", st == 200, b)

    def scored():
        _, d, _ = rec.get(f"/applications/{aid}")
        return d if any(x.get("evaluation") for x in d.get("assessments") or []) else None
    try:
        d = wait(scored, 600, "the answers to be scored")
        ev = next(x for x in d["assessments"] if x.get("evaluation"))
        check("answers scored and visible to the recruiter", ev["evaluation"]["overall"] > 0, ev["evaluation"].get("overall"))
        log(f"      questions by: {ev.get('questions_by')}; scored by: {ev['evaluation'].get('model')}; "
            f"assessment {ev['evaluation']['overall']}/100; overall match {(d.get('match') or {}).get('score')}")
    except AssertionError as e:
        check("answers scored and visible to the recruiter", False, e)
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="test an already running copy instead of starting one")
    ap.add_argument("--keep", action="store_true", help="keep the temporary data folder")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    lines = []

    def log(s):
        print(s, flush=True); lines.append(s)
    proc, data = None, None
    if args.url:
        base = args.url
    else:
        port = free_port()
        data = tempfile.mkdtemp(prefix="talentbridge-smoke-")
        env = {**os.environ, "DATA_DIR": data, "PORT": str(port), "DEMO_SEED": "1", "PYTHONUTF8": "1",
               "DATABASE_URL": "sqlite:///" + os.path.join(data, "talentbridge.db"), "EMAIL_PROVIDER": "file"}
        out = open(os.path.join(data, "server.log"), "w", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.py"), "--port", str(port)], cwd=ROOT, env=env, stdout=out,
                                stderr=subprocess.STDOUT)
        base = f"http://127.0.0.1:{port}"

        def up():
            if proc.poll() is not None:
                raise AssertionError("the server stopped during start-up; see " + os.path.join(data, "server.log"))
            try:
                with urllib.request.urlopen(base + "/api/v1/health", timeout=2) as r:
                    return r.status == 200
            except Exception:
                return False
        try:
            wait(up, 90, "the server to start")
            log(f"PASS  server started on {base} (temporary data folder)")
        except AssertionError as e:
            log(f"FAIL  {e}")
            proc.kill()
            return 1
    try:
        ok = run_checks(base, log)
    except Exception as e:
        log(f"FAIL  unexpected error: {type(e).__name__}: {e}")
        ok = False
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(10)
            except Exception:
                proc.kill()
    log("\nSMOKE TEST " + ("PASSED" if ok else "FAILED"))
    if data and not args.keep and ok:
        import shutil
        shutil.rmtree(data, ignore_errors=True)
    elif data:
        log("Server log and data kept in: " + data)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
