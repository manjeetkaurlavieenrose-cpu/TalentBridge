"""Things that differ on Windows: MIME types from the registry, Notepad-saved .env files, legacy console code pages, folders
with spaces or non-English characters, the Windows Tesseract install folder, and batch-file line endings. These run on every
platform so a Windows break is caught anywhere; .github/workflows/tests.yml also runs the whole suite on real Windows."""
import re
import io, mimetypes, os, shutil, sys, tempfile, unittest
from .support import Base, Client, make_pdf, cv_text
from app import create_app, ocr, pipeline as pl
from app.config import Config

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
import run  # noqa: E402  (the launcher, for its .env reader)


class StaticTypeTests(Base):
    def test_scripts_are_javascript_even_if_the_registry_says_text_plain(self):
        mimetypes.add_type("text/plain", ".js")           # what many Windows registries contain
        mimetypes.add_type("text/plain", ".css")
        app = create_app(self.cfg, ai=self.ai, mailer=self.mailer)
        r = app.test_client().get("/js/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["Content-Type"].startswith("text/javascript"), r.headers["Content-Type"])
        self.assertTrue(app.test_client().get("/styles.css").headers["Content-Type"].startswith("text/css"))
        r.close()
        app.ctx.db.close()


class EnvFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.keys = ["TB_T_PORT", "TB_T_A", "TB_T_Q", "TB_T_C"]

    def tearDown(self):
        for k in self.keys:
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_notepad_bom_crlf_and_inline_comments(self):
        p = os.path.join(self.tmp, ".env")
        with open(p, "wb") as f:      # UTF-8 with BOM and CRLF, as Notepad writes it
            f.write("﻿TB_T_PORT=5051                    # comment like in .env.example\r\nTB_T_A=ollama\r\n"
                    "TB_T_Q=\"pass # word\"\r\n# TB_T_C=ignored\r\n".encode("utf-8"))
        run.load_env(p)
        self.assertEqual(os.environ["TB_T_PORT"], "5051")
        self.assertEqual(os.environ["TB_T_A"], "ollama")
        self.assertEqual(os.environ["TB_T_Q"], "pass # word")
        self.assertNotIn("TB_T_C", os.environ)

    def test_legacy_console_code_page_does_not_crash(self):
        buf = io.BytesIO()
        old = sys.stdout
        sys.stdout = io.TextIOWrapper(buf, encoding="cp1252")
        try:
            run.utf8_console()
            print("Assessment · 12 – 15 “quotes” ✓ ✗")
            sys.stdout.flush()
            out = buf.getvalue()
        finally:
            sys.stdout = old
        self.assertIn(b"Assessment", out)


class FolderTests(unittest.TestCase):
    def test_data_folder_with_spaces_and_accents(self):
        tmp = tempfile.mkdtemp(prefix="Talent Bridge données ")
        try:
            cfg = Config(database_url="sqlite:///" + os.path.join(tmp, "t.db"),
                         upload_dir=os.path.join(tmp, "my uploads"), cookie_secure=False, admin_email="admin@tb.test",
                         admin_password="correct-horse-9", rl_global=(100000, 60), rl_login=(1000, 60), rl_register=(1000, 60),
                         rl_upload=(1000, 60), allowed_origins=["http://localhost:5000"])
            app = create_app(cfg)
            c = Client(app)
            self.assertEqual(c.post("/auth/register/candidate", {"email": "a@example.com", "password": "correct-horse-9",
                                                                  "full_name": "Asha Verma"}).status_code, 201)
            c.login("a@example.com")
            r = c.post("/me/cvs", data={"file": (io.BytesIO(make_pdf(cv_text())), "my cv (final).pdf")}, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 201, r.json)
            pl.run_pending(app.ctx)
            self.assertEqual(c.get("/me/profile").json["cvs"][0]["stage"], "ready")
            self.assertTrue(os.listdir(os.path.join(tmp, "my uploads")))
            app.ctx.db.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TesseractLookupTests(unittest.TestCase):
    def test_configured_path_is_used(self):
        tmp = tempfile.mkdtemp()
        try:
            exe = os.path.join(tmp, "tesseract.exe")
            open(exe, "wb").close()
            self.assertEqual(ocr.tesseract_path(Config(tesseract_cmd=exe)), exe)
            self.assertIsNone(ocr.engine(Config(ocr="off")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_standard_windows_install_folders_are_known(self):
        self.assertTrue(any("Tesseract-OCR" in p for p in ocr.WINDOWS_PATHS))


class ScriptFileTests(unittest.TestCase):
    def test_batch_files_use_crlf_and_shell_scripts_lf(self):
        for name in ("setup_windows.bat", "start_windows.bat", "start_demo_windows.bat", "test_windows.bat"):
            with open(os.path.join(ROOT, name), "rb") as f:
                data = f.read()
            self.assertTrue(data.count(b"\r\n") > 5 and data.count(b"\n") == data.count(b"\r\n"), name)
        for name in ("setup_mac.command", "start_mac.command"):
            with open(os.path.join(ROOT, name), "rb") as f:
                self.assertNotIn(b"\r\n", f.read(), name)

    def test_windows_scripts_never_hang_unattended(self):
        for name in ("setup_windows.bat", "start_windows.bat", "start_demo_windows.bat", "test_windows.bat"):
            with open(os.path.join(ROOT, name), encoding="ascii") as f:
                for line in f:
                    if line.strip().lower() == "pause":
                        self.fail(f"{name}: a bare 'pause' blocks automated runs; use 'if not defined TB_NO_PAUSE pause'")


if __name__ == "__main__":
    unittest.main()


class HostingDefaultsTests(unittest.TestCase):
    """The same code must work on a laptop and behind a hosting service's https proxy without anyone editing settings."""
    def test_render(self):
        from app.hosting import apply_host_defaults
        env = {"RENDER": "true", "PORT": "10000", "RENDER_EXTERNAL_URL": "https://tb.onrender.com/"}
        self.assertEqual(apply_host_defaults(env), "Render")
        self.assertEqual((env["HOST"], env["TRUSTED_PROXIES"], env["COOKIE_SECURE"], env["PUBLIC_URL"], env["ALLOWED_ORIGINS"]),
                         ("0.0.0.0", "1", "1", "https://tb.onrender.com", "https://tb.onrender.com"))

    def test_other_platforms_and_laptop(self):
        from app.hosting import apply_host_defaults
        env = {"FLY_APP_NAME": "tb", "PORT": "8000"}; apply_host_defaults(env); self.assertEqual(env["PUBLIC_URL"], "https://tb.fly.dev")
        env = {"RAILWAY_PUBLIC_DOMAIN": "tb.up.railway.app"}; apply_host_defaults(env); self.assertEqual(env["PUBLIC_URL"], "https://tb.up.railway.app")
        env = {}; self.assertIsNone(apply_host_defaults(env)); self.assertEqual(env, {})          # a laptop is left exactly as it was
        env = {"RENDER": "true", "PORT": "1", "COOKIE_SECURE": "0", "HOST": "127.0.0.1"}; apply_host_defaults(env)
        self.assertEqual((env["COOKIE_SECURE"], env["HOST"]), ("0", "127.0.0.1"))                 # what the person set always wins

    def test_signed_in_requests_work_through_an_https_proxy(self):
        import tempfile
        from app import create_app
        from app.config import Config
        tmp = tempfile.mkdtemp()
        app = create_app(Config(database_url=f"sqlite:///{tmp}/t.db", upload_dir=f"{tmp}/up", trusted_proxies=1, cookie_secure=True,
                                allowed_origins=["https://tb.onrender.com"], rl_global=(10**6, 60), admin_email="a@tb.test", admin_password="correct-horse-9"))
        c = app.test_client()
        h = {"Host": "tb.onrender.com", "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.9", "Origin": "https://tb.onrender.com"}
        r = c.post("/api/v1/auth/login", json={"email": "a@tb.test", "password": "correct-horse-9"}, headers=h)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertIn("Secure", r.headers.get("Set-Cookie", ""))
        r = c.post("/api/v1/auth/register/candidate", json={"email": "x@example.org", "password": "correct-horse-9", "full_name": "Xan Example"},
                   headers={**h, "Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)                                                       # other sites are still refused
        app.ctx.db.close()

    def test_deploy_files_are_present_and_consistent(self):
        import os
        root = os.path.join(os.path.dirname(__file__), "..", "..")
        read = lambda f: open(os.path.join(root, f), encoding="utf-8").read()
        d = read("Dockerfile")
        self.assertIn('CMD ["python", "/app/run.py"]', d); self.assertIn("DEMO_SEED=0", d); self.assertIn("HEALTHCHECK", d)
        self.assertIn("runtime: docker", read("render.yaml")); self.assertIn("healthCheckPath: /api/v1/health", read("render.yaml"))
        readme = read("README.md")       # the placeholder before upload; set-links.yml then fills in the repository's own address
        self.assertTrue("OWNER/REPO" in readme or re.search(r"render\.com/deploy\?repo=https://github\.com/[\w.-]+/[\w.-]+\)", readme), "deploy link missing")
        self.assertIn("gunicorn", read("compose.yaml"))
        self.assertTrue(read("docker-entrypoint.sh").startswith("#!/bin/sh"))
