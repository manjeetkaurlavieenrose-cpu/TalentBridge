"""Local demo/e2e server. Uses the deterministic TEST DOUBLE for AI -- never use this for real hiring.
python -m tests.devserver [port]"""
import sys, threading, time, tempfile
from app import create_app
from app.config import Config
from app import pipeline as pl
from .support import FakeAI, Mailer

def main(port=5055):
    d = tempfile.mkdtemp()
    cfg = Config(database_url=f"sqlite:///{d}/dev.db", upload_dir=f"{d}/up", cookie_secure=False, admin_email="admin@tb.test",
                 admin_password="correct-horse-9", allowed_origins=[f"http://127.0.0.1:{port}"])
    app = create_app(cfg, ai=FakeAI(), mailer=Mailer())
    def loop():
        from app import Ctx
        while True:
            if not pl.run_one(app.ctx): time.sleep(0.3)
    threading.Thread(target=loop, daemon=True).start()
    app.run(port=port, threaded=True)

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5055)
