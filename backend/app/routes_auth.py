from flask import Blueprint, g, jsonify, request, make_response
from datetime import datetime, timezone, timedelta
from .http import ApiError, body, ctx, audit, require, paging, envelope, client_ip, expires
from .db import now, uid
from .security import hash_password, verify_password, DUMMY_HASH, password_problem, new_token, token_hash
from .validation import S, O

bp = Blueprint("auth", __name__)
EMAIL = S(format="email", maxLength=200)
PW = S(minLength=1, maxLength=128)
COOKIE = "tb_session"


def _limit(key, limit):
    ok, wait = ctx().limiter.allow(key, limit)
    if not ok:
        e = ApiError(429, "rate_limited", f"Too many attempts. Try again in {wait} seconds.")
        raise e


def _start_session(user):
    c, tok, csrf = ctx(), new_token(), new_token()
    c.db.execute("INSERT INTO sessions (token_hash,user_id,csrf_token,ip,user_agent,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
                 (token_hash(tok), user["id"], csrf, client_ip(), (request.user_agent.string or "")[:200], now(), expires(c.cfg.session_hours)))
    c.db.execute("DELETE FROM sessions WHERE user_id=? AND expires_at<?", (user["id"], now()))
    return tok, csrf


def _me(user, csrf):
    c = ctx()
    out = {"id": user["id"], "email": user["email"], "role": user["role"], "status": user["status"], "csrf_token": csrf}
    if user["role"] == "candidate":
        r = c.db.one("SELECT id, full_name, profile_status FROM candidates WHERE user_id=?", (user["id"],))
        out["candidate"] = r
    elif user["role"] == "recruiter":
        out["recruiter"] = c.db.one("SELECT r.id, r.full_name, r.organization_id, o.name AS organization FROM recruiters r JOIN organizations o ON o.id=r.organization_id WHERE r.user_id=?", (user["id"],))
    return out


@bp.post("/auth/register/candidate")
def register_candidate():
    d = body(O({"email": EMAIL, "password": PW, "full_name": S(minLength=2, maxLength=120)}, ["email", "password", "full_name"]))
    _limit("reg:" + client_ip(), ctx().cfg.rl_register)
    email = d["email"].lower()
    prob = password_problem(d["password"], email)
    if prob: raise ApiError(422, "weak_password", prob)
    c = ctx()
    if c.db.one("SELECT 1 AS x FROM users WHERE email=?", (email,)):
        raise ApiError(409, "email_taken", "An account with this email already exists.")
    uid_, t = uid(), now()
    with c.db.tx():
        c.db.execute("INSERT INTO users (id,email,password_hash,role,status,created_at) VALUES (?,?,?,?,?,?)",
                     (uid_, email, hash_password(d["password"]), "candidate", "active", t))
        existing = c.db.one("SELECT id FROM candidates WHERE email=? AND user_id IS NULL", (email,))
        if existing:   # a recruiter created this record earlier: the candidate claims it by registering with the same email
            c.db.execute("UPDATE candidates SET user_id=?, updated_at=? WHERE id=?", (uid_, t, existing["id"]))
            cid = existing["id"]
        else:
            cid = uid()
            c.db.execute("INSERT INTO candidates (id,user_id,email,full_name,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                         (cid, uid_, email, d["full_name"], t, t))
    audit("auth.register", "user", uid_, {"role": "candidate", "claimed_record": bool(existing)}, actor={"id": uid_, "role": "candidate"})
    from .mail import queue_email, render
    queue_email(c, email, *render("registered", name=d["full_name"], url=c.cfg.public_url), kind="registered")
    return jsonify({"ok": True}), 201


@bp.post("/auth/register/recruiter")
def register_recruiter():
    d = body(O({"email": EMAIL, "password": PW, "full_name": S(minLength=2, maxLength=120),
                "organization": S(minLength=2, maxLength=120)}, ["email", "password", "full_name", "organization"]))
    _limit("reg:" + client_ip(), ctx().cfg.rl_register)
    email = d["email"].lower()
    prob = password_problem(d["password"], email)
    if prob: raise ApiError(422, "weak_password", prob)
    c = ctx()
    if c.db.one("SELECT 1 AS x FROM users WHERE email=?", (email,)):
        raise ApiError(409, "email_taken", "An account with this email already exists.")
    uid_, t = uid(), now()
    with c.db.tx():
        org = c.db.one("SELECT id FROM organizations WHERE LOWER(name)=LOWER(?)", (d["organization"],))
        oid = org["id"] if org else uid()
        if not org:
            c.db.execute("INSERT INTO organizations (id,name,created_at) VALUES (?,?,?)", (oid, d["organization"], t))
        c.db.execute("INSERT INTO users (id,email,password_hash,role,status,created_at) VALUES (?,?,?,?,?,?)",
                     (uid_, email, hash_password(d["password"]), "recruiter", "pending", t))
        c.db.execute("INSERT INTO recruiters (id,user_id,organization_id,full_name) VALUES (?,?,?,?)", (uid(), uid_, oid, d["full_name"]))
    audit("auth.register", "user", uid_, {"role": "recruiter", "organization": d["organization"]}, actor={"id": uid_, "role": "recruiter"})
    return jsonify({"ok": True, "status": "pending", "message": "Your account is waiting for administrator approval."}), 201


@bp.post("/auth/login")
def login():
    d = body(O({"email": EMAIL, "password": PW}, ["email", "password"]))
    email = d["email"].lower()
    c = ctx()
    _limit(f"login:{client_ip()}:{email}", c.cfg.rl_login)
    u = c.db.one("SELECT * FROM users WHERE email=?", (email,))
    if u and u["locked_until"] and u["locked_until"] > now():
        audit("auth.login_blocked", "user", u["id"], {"reason": "locked"}, actor={"id": u["id"], "role": u["role"]})
        raise ApiError(423, "account_locked", "Too many failed attempts. Try again later.")
    ok = verify_password(d["password"], u["password_hash"] if u else DUMMY_HASH)
    if not u or not ok:
        if u:
            fails = u["failed_logins"] + 1
            lock = (datetime.now(timezone.utc) + timedelta(minutes=c.cfg.lockout_minutes)).isoformat(timespec="microseconds") if fails >= c.cfg.lockout_after else None
            c.db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (0 if lock else fails, lock, u["id"]))
        audit("auth.login_failed", "user", u["id"] if u else None, {"email_known": bool(u)}, actor={"id": u["id"], "role": u["role"]} if u else None)
        raise ApiError(401, "invalid_credentials", "Invalid email or password.")
    if u["status"] == "pending":
        raise ApiError(403, "pending_approval", "Your recruiter account is waiting for administrator approval.")
    if u["status"] != "active":
        raise ApiError(403, "account_suspended", "This account has been suspended.")
    c.db.execute("UPDATE users SET failed_logins=0, locked_until=NULL, last_login_at=? WHERE id=?", (now(), u["id"]))
    tok, csrf = _start_session(u)
    audit("auth.login", "user", u["id"], actor=u)
    resp = make_response(jsonify(_me(u, csrf)))
    resp.set_cookie(COOKIE, tok, httponly=True, samesite="Strict", secure=c.cfg.cookie_secure, max_age=c.cfg.session_hours * 3600, path="/")
    return resp


@bp.post("/auth/logout")
@require()
def logout():
    ctx().db.execute("DELETE FROM sessions WHERE token_hash=?", (g.session["token_hash"],))
    audit("auth.logout", "user", g.user["id"])
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(COOKIE, path="/")
    return resp


@bp.get("/auth/me")
@require()
def me():
    return jsonify(_me(g.user, g.session["csrf_token"]))


# ------------------------------------------------------------------ admin
@bp.get("/admin/users")
@require("admin")
def admin_users():
    page, limit, off = paging()
    where, args = ["1=1"], []
    for k in ("role", "status"):
        if request.args.get(k):
            where.append(f"u.{k}=?"); args.append(request.args[k])
    if request.args.get("q"):
        where.append("LOWER(u.email) LIKE ?"); args.append("%" + request.args["q"].lower() + "%")
    w = " AND ".join(where)
    total = ctx().db.scalar(f"SELECT COUNT(*) FROM users u WHERE {w}", args)
    rows = ctx().db.all(f"""SELECT u.id,u.email,u.role,u.status,u.created_at,u.last_login_at,o.name AS organization
        FROM users u LEFT JOIN recruiters r ON r.user_id=u.id LEFT JOIN organizations o ON o.id=r.organization_id
        WHERE {w} ORDER BY u.created_at DESC LIMIT ? OFFSET ?""", args + [limit, off])
    return envelope(rows, total, page, limit)


@bp.post("/admin/users/<uid_>/status")
@require("admin")
def admin_set_status(uid_):
    d = body(O({"status": S(enum=["active", "suspended"])}, ["status"]))
    c = ctx()
    u = c.db.one("SELECT * FROM users WHERE id=?", (uid_,))
    if not u: raise ApiError(404, "not_found", "User not found.")
    if u["id"] == g.user["id"]: raise ApiError(400, "self_change", "You cannot change your own status.")
    c.db.execute("UPDATE users SET status=? WHERE id=?", (d["status"], uid_))
    if u["role"] == "recruiter" and d["status"] == "active" and u["status"] == "pending":
        c.db.execute("UPDATE recruiters SET approved_by=?, approved_at=? WHERE user_id=?", (g.user["id"], now(), uid_))
    if d["status"] == "suspended":
        c.db.execute("DELETE FROM sessions WHERE user_id=?", (uid_,))
    audit("admin.user_status", "user", uid_, {"from": u["status"], "to": d["status"]})
    return jsonify({"ok": True})


@bp.post("/admin/recruiters/<uid_>/organization")
@require("admin")
def admin_set_org(uid_):
    d = body(O({"organization": S(minLength=2, maxLength=120)}, ["organization"]))
    c = ctx()
    if not c.db.one("SELECT 1 AS x FROM recruiters WHERE user_id=?", (uid_,)): raise ApiError(404, "not_found", "Recruiter not found.")
    org = c.db.one("SELECT id FROM organizations WHERE LOWER(name)=LOWER(?)", (d["organization"],))
    oid = org["id"] if org else uid()
    if not org: c.db.execute("INSERT INTO organizations (id,name,created_at) VALUES (?,?,?)", (oid, d["organization"], now()))
    c.db.execute("UPDATE recruiters SET organization_id=? WHERE user_id=?", (oid, uid_))
    audit("admin.recruiter_org", "user", uid_, {"organization": d["organization"]})
    return jsonify({"ok": True})


@bp.get("/admin/audit-logs")
@require("admin")
def admin_logs():
    page, limit, off = paging(50)
    where, args = ["1=1"], []
    for k in ("entity_type", "entity_id", "actor_id", "action"):
        if request.args.get(k):
            where.append(f"{k}=?"); args.append(request.args[k])
    w = " AND ".join(where)
    total = ctx().db.scalar(f"SELECT COUNT(*) FROM activity_logs WHERE {w}", args)
    rows = ctx().db.all(f"SELECT * FROM activity_logs WHERE {w} ORDER BY created_at DESC, id LIMIT ? OFFSET ?", args + [limit, off])
    return envelope(rows, total, page, limit)


@bp.get("/team")
@require("recruiter", "admin")
def team():
    if g.user["role"] == "admin":
        raise ApiError(400, "no_org", "Admins are not members of an organisation; use /admin/users.")
    r = ctx().db.one("SELECT organization_id FROM recruiters WHERE user_id=?", (g.user["id"],))
    rows = ctx().db.all("""SELECT r.full_name, u.email, u.status, u.last_login_at FROM recruiters r JOIN users u ON u.id=r.user_id
                           WHERE r.organization_id=? ORDER BY r.full_name""", (r["organization_id"],))
    return jsonify({"data": rows})
