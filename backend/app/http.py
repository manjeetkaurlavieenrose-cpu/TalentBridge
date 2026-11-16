import json
from datetime import datetime, timezone, timedelta
from flask import current_app, g, request, jsonify
from .db import now, uid, jd
from .validation import validate, ValidationError


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def ctx():
    return current_app.ctx


def body(schema):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_json", "Request body must be a JSON object.")
    try:
        return validate(data, schema)
    except ValidationError as e:
        raise ApiError(422, "validation_failed", "Some fields are invalid.", e.errors)


def client_ip():
    return request.remote_addr or "unknown"


def audit(action, etype=None, eid=None, detail=None, actor=None):
    u = actor if actor is not None else getattr(g, "user", None)
    ctx().db.execute(
        "INSERT INTO activity_logs (id, actor_id, actor_role, action, entity_type, entity_id, detail, ip, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (uid(), u["id"] if u else None, u["role"] if u else "anonymous", action, etype, eid,
         jd(detail) if detail is not None else None, client_ip(), now()))


def paging(default=25, maximum=100):
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = int(request.args.get("limit", default))
    except ValueError:
        raise ApiError(400, "bad_paging", "page and limit must be integers.")
    limit = max(1, min(limit, maximum))
    return page, limit, (page - 1) * limit


def envelope(rows, total, page, limit):
    return jsonify({"data": rows, "page": page, "limit": limit, "total": total, "pages": (total + limit - 1) // limit})


def require(*roles):
    def deco(fn):
        from functools import wraps
        @wraps(fn)
        def wrapper(*a, **k):
            u = getattr(g, "user", None)
            if not u:
                raise ApiError(401, "unauthenticated", "Sign in required.")
            if u["status"] != "active":
                raise ApiError(403, "account_not_active", "Your account is not active.")
            if roles and u["role"] not in roles:
                raise ApiError(403, "forbidden", "You do not have permission to do this.")
            return fn(*a, **k)
        return wrapper
    return deco


def expires(hours):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="microseconds")
