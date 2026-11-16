import mimetypes, os
from datetime import datetime, timezone
from flask import Flask, g, jsonify, request, send_from_directory
from .config import Config
from .db import DB, now, uid
from .files import make_storage
from .security import RateLimiter, DBRateLimiter, hash_password, token_hash
from .http import ApiError, ctx as _ctx
from . import ai as ai_mod, ocr as ocr_mod


class Ctx:
    def __init__(self, cfg, ai=None, mailer=None):
        self.cfg = cfg
        self.db = DB(cfg.database_url)
        self.db.init_schema()
        self.storage = make_storage(cfg)
        self.ai = ai or ai_mod.get_provider(cfg)
        from .similarity import make_encoder
        self.encoder = make_encoder(cfg)
        self.limiter = DBRateLimiter(self.db) if cfg.rate_limit_backend == "db" else RateLimiter()
        from .pipeline import get_mailer
        self.mailer = mailer or get_mailer(cfg)


UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT = {"auth.login", "auth.register_candidate", "auth.register_recruiter"}


def bootstrap_admin(c):
    if c.cfg.admin_email and c.cfg.admin_password and not c.db.one("SELECT 1 AS x FROM users WHERE role='admin'"):
        c.db.execute("INSERT INTO users (id,email,password_hash,role,status,created_at) VALUES (?,?,?,?,?,?)",
                     (uid(), c.cfg.admin_email.lower(), hash_password(c.cfg.admin_password), "admin", "active", now()))


def start_embedded_worker(c, poll=0.4):
    """Run the background task loop in a daemon thread of the web process (laptop/demo mode)."""
    import threading, time
    from . import pipeline as pl

    def loop():
        while True:
            try:
                if not pl.run_one(c):
                    time.sleep(poll)
            except Exception:       # a failing task must never kill the loop
                time.sleep(1)
    t = threading.Thread(target=loop, name="tb-worker", daemon=True)
    t.start()
    return t


WEB_TYPES = ((".js", "text/javascript"), (".mjs", "text/javascript"), (".css", "text/css"), (".svg", "image/svg+xml"),
             (".html", "text/html"), (".json", "application/json"))


def create_app(cfg=None, ai=None, mailer=None):
    # Windows takes MIME types from the registry, where ".js" is often "text/plain"; browsers then refuse to run the UI's ES modules.
    for ext, typ in WEB_TYPES:
        mimetypes.add_type(typ, ext)
    cfg = cfg or Config()
    app = Flask(__name__, static_folder=None)
    app.ctx = Ctx(cfg, ai, mailer)
    if cfg.trusted_proxies > 0:  # real client IP from X-Forwarded-For, trusting only this many proxy hops
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=cfg.trusted_proxies, x_proto=cfg.trusted_proxies, x_host=cfg.trusted_proxies)
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_upload_bytes + 64 * 1024
    bootstrap_admin(app.ctx)
    from . import pipeline as pl
    pl.backfill(app.ctx)
    if cfg.embedded_worker:
        pl.recover_interrupted(app.ctx)      # one process owns the queue: anything 'running' was cut off by a restart
        start_embedded_worker(app.ctx)

    @app.before_request
    def guard():
        if not request.path.startswith("/api/"):
            return
        c = app.ctx
        ok, wait = c.limiter.allow("g:" + (request.remote_addr or "?"), c.cfg.rl_global)
        if not ok:
            raise ApiError(429, "rate_limited", f"Too many requests. Try again in {wait} seconds.")
        origin = request.headers.get("Origin")
        if request.method in UNSAFE and origin and origin not in c.cfg.allowed_origins and origin != request.host_url.rstrip("/"):
            raise ApiError(403, "bad_origin", "Cross-origin request blocked.")
        g.user = g.session = None
        tok = request.cookies.get("tb_session")
        if tok:
            s = c.db.one("SELECT * FROM sessions WHERE token_hash=?", (token_hash(tok),))
            if s and s["expires_at"] > now():
                u = c.db.one("SELECT * FROM users WHERE id=?", (s["user_id"],))
                if u and u["status"] != "suspended":
                    g.user, g.session = u, s
        if g.user and request.method in UNSAFE and request.endpoint not in CSRF_EXEMPT:
            if request.headers.get("X-CSRF-Token") != g.session["csrf_token"]:
                raise ApiError(403, "csrf", "Missing or invalid CSRF token.")

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
            origin = request.headers.get("Origin")
            if origin and origin in app.ctx.cfg.allowed_origins:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token"
                resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE"
                resp.headers["Vary"] = "Origin"
        else:
            resp.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        return resp

    @app.errorhandler(ApiError)
    def api_error(e):
        r = jsonify({"error": {"code": e.code, "message": e.message, "details": e.details}})
        r.status_code = e.status
        return r

    @app.errorhandler(413)
    def too_big(_):
        return api_error(ApiError(413, "file_too_large", f"Uploads are limited to {cfg.max_upload_bytes // (1024 * 1024)} MB."))

    @app.errorhandler(404)
    def nf(_):
        return api_error(ApiError(404, "not_found", "Not found."))

    @app.errorhandler(405)
    def na(_):
        return api_error(ApiError(405, "method_not_allowed", "Method not allowed."))

    @app.errorhandler(Exception)
    def boom(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return api_error(ApiError(e.code, "http_error", e.description))
        app.logger.exception("unhandled")
        return api_error(ApiError(500, "internal_error", "Something went wrong."))

    from . import routes_auth, routes_core
    app.register_blueprint(routes_auth.bp, url_prefix="/api/v1")
    app.register_blueprint(routes_core.bp, url_prefix="/api/v1")

    @app.get("/api/v1/health")
    def health():
        app.ctx.db.scalar("SELECT 1")
        a = app.ctx.ai
        return jsonify({"ok": True, "ai_provider": ai_mod.provider_label(a, cfg), "ai_configured": not isinstance(a, ai_mod.UnconfiguredAI),
                        "ai_model": ai_mod.model_status(a), "email": app.ctx.mailer.describe() if hasattr(app.ctx.mailer, "describe") else None,
                        "database": "postgresql" if app.ctx.db.pg else "sqlite",
                        "semantic_match": app.ctx.encoder is not None, "ocr": ocr_mod.describe(cfg), "embedded_worker": bool(cfg.embedded_worker),
                        "demo": bool(cfg.demo_mode)})

    fe = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

    @app.get("/")
    def index():
        return send_from_directory(fe, "index.html")

    @app.get("/<path:p>")
    def static_files(p):
        if p.startswith("api/"):
            raise ApiError(404, "not_found", "Not found.")
        return send_from_directory(fe, p)

    return app
