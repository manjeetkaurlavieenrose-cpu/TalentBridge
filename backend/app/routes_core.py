import csv, hashlib, io, json, re
from datetime import datetime, timezone, timedelta
from flask import Blueprint, g, jsonify, request, Response
from .http import ApiError, body, ctx, audit, require, paging, envelope, expires
from .db import now, uid, jd, jl
from .validation import validate, ValidationError, S, N, I, A, O
from .security import verify_password
from .files import sniff, safe_name, FileRejected
from .ai import CV_SCHEMA, ASSESSMENT_SCHEMA, normalise_task
from .profile import normalise, summary_fields
from . import pipeline as pl, workflow, identity, originality, integrity

bp = Blueprint("core", __name__)
REC = ("recruiter", "admin")


# ------------------------------------------------------------------ scoping / access
def my_org():
    r = ctx().db.one("SELECT organization_id FROM recruiters WHERE user_id=?", (g.user["id"],))
    return r["organization_id"] if r else None


def org_scope_sql():
    """SQL fragment limiting candidates `c` to those a recruiter's organisation may see."""
    return ("(c.managed_by_org_id=? OR EXISTS (SELECT 1 FROM applications a JOIN jobs j ON j.id=a.job_id "
            "WHERE a.candidate_id=c.id AND j.organization_id=?))")


def get_candidate(cid):
    c = ctx()
    row = c.db.one("SELECT * FROM candidates WHERE id=?", (cid,))
    if not row: raise ApiError(404, "not_found", "Candidate not found.")
    u = g.user
    if u["role"] == "admin": return row
    if u["role"] == "candidate":
        if row["user_id"] == u["id"]: return row
    else:
        o = my_org()
        if row["managed_by_org_id"] == o or c.db.one(
                "SELECT 1 AS x FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.candidate_id=? AND j.organization_id=?", (cid, o)):
            return row
    raise ApiError(404, "not_found", "Candidate not found.")   # 404, not 403: do not reveal existence


def get_application(aid):
    c = ctx()
    row = c.db.one("""SELECT a.*, j.organization_id AS org_id, j.title AS job_title, ca.user_id AS cand_user
                      FROM applications a JOIN jobs j ON j.id=a.job_id JOIN candidates ca ON ca.id=a.candidate_id WHERE a.id=?""", (aid,))
    if not row: raise ApiError(404, "not_found", "Application not found.")
    u = g.user
    if u["role"] == "admin" or (u["role"] == "candidate" and row["cand_user"] == u["id"]) or \
            (u["role"] == "recruiter" and row["org_id"] == my_org()):
        return row
    raise ApiError(404, "not_found", "Application not found.")


def get_job(jid, recruiter_only=True):
    row = ctx().db.one("SELECT * FROM jobs WHERE id=?", (jid,))
    if not row: raise ApiError(404, "not_found", "Job not found.")
    if g.user["role"] == "admin": return row
    if g.user["role"] == "recruiter":
        if row["organization_id"] == my_org(): return row
    elif row["status"] == "open" and not recruiter_only:
        return row
    raise ApiError(404, "not_found", "Job not found.")


def get_assessment(sid):
    c = ctx()
    row = c.db.one("""SELECT s.*, a.id AS app_id, a.candidate_id, j.organization_id AS org_id, ca.user_id AS cand_user, j.title AS job_title
                      FROM assessments s JOIN applications a ON a.id=s.application_id JOIN jobs j ON j.id=a.job_id
                      JOIN candidates ca ON ca.id=a.candidate_id WHERE s.id=?""", (sid,))
    if not row: raise ApiError(404, "not_found", "Assessment not found.")
    u = g.user
    if u["role"] == "admin" or (u["role"] == "recruiter" and row["org_id"] == my_org()) or \
            (u["role"] == "candidate" and row["cand_user"] == u["id"] and row["status"] not in ("generating", "draft", "failed")):
        return row
    raise ApiError(404, "not_found", "Assessment not found.")


def get_cv(cv_id):
    """A CV file/text is visible to its owner, to admins, and to recruiters of an organisation that either manages the
    candidate record or received an application made WITH THIS CV. Other CVs of the same person stay private."""
    c = ctx()
    row = c.db.one("SELECT * FROM cvs WHERE id=?", (cv_id,))
    if not row: raise ApiError(404, "not_found", "CV not found.")
    u = g.user
    if u["role"] == "admin": return row
    cand = c.db.one("SELECT user_id, managed_by_org_id FROM candidates WHERE id=?", (row["candidate_id"],))
    if u["role"] == "candidate":
        if cand["user_id"] == u["id"]: return row
    else:
        o = my_org()
        if o and (cand["managed_by_org_id"] == o or c.db.one(
                "SELECT 1 AS x FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.cv_id=? AND j.organization_id=?", (cv_id, o))):
            return row
    raise ApiError(404, "not_found", "CV not found.")


def job_out(r):
    r = dict(r)
    for k in ("required_skills", "preferred_skills", "custom_requirements"):
        r[k] = jl(r[k], [])
    r["auto_assessment"] = bool(r.get("auto_assessment"))
    return r


def public_job(r):
    r = job_out(r)
    return {k: r[k] for k in ("id", "title", "kind", "description", "required_skills", "preferred_skills", "min_years",
                              "education_level", "deadline", "status", "created_at")}


# ------------------------------------------------------------------ CV upload
def store_cvs(candidate_id):
    c = ctx()
    ok, wait = c.limiter.allow(f"up:{g.user['id']}", c.cfg.rl_upload)
    if not ok: raise ApiError(429, "rate_limited", f"Upload limit reached. Try again in {wait} seconds.")
    files = request.files.getlist("file") + request.files.getlist("files")
    if not files: raise ApiError(400, "no_file", "Attach one or more files in the 'file' field.")
    if len(files) > 3: raise ApiError(400, "too_many_files", "Upload at most 3 files at a time.")
    results = []
    for f in files:
        name = safe_name(f.filename)
        data = f.read(c.cfg.max_upload_bytes + 1)
        try:
            if len(data) > c.cfg.max_upload_bytes:
                raise FileRejected("file_too_large", f"Files are limited to {c.cfg.max_upload_bytes // (1024 * 1024)} MB.")
            kind, mime = sniff(data, name)
        except FileRejected as e:
            results.append({"name": name, "ok": False, "error": {"code": e.code, "message": e.message}})
            continue
        sha_now = hashlib.sha256(data).hexdigest()
        dup = c.db.one("SELECT id, stage FROM cvs WHERE candidate_id=? AND sha256=? AND stage != 'failed' ORDER BY created_at DESC LIMIT 1", (candidate_id, sha_now))
        if dup:   # same file again (double click, refresh, retry): do not create a second record or a second background job
            results.append({"name": name, "ok": True, "cv_id": dup["id"], "stage": dup["stage"], "duplicate": True})
            continue
        key, sha = c.storage.put(data, kind)
        cid, t = uid(), now()
        c.db.execute("INSERT INTO cvs (id,candidate_id,storage_key,original_name,mime,size,sha256,stage,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (cid, candidate_id, key, name, mime, len(data), sha, "uploaded", t, t))
        pl.enqueue(c, "process_cv", {"cv_id": cid})
        audit("cv.upload", "cv", cid, {"candidate_id": candidate_id, "size": len(data), "sha256": sha})
        results.append({"name": name, "ok": True, "cv_id": cid, "stage": "uploaded"})
    status = 201 if any(r["ok"] for r in results) else 422
    return jsonify({"files": results}), status


def cv_out(r, active_id=None):
    out = {k: r[k] for k in ("id", "original_name", "size", "stage", "error_code", "error_message", "created_at", "updated_at")}
    out["identity_status"] = r.get("identity_status")
    out["identity"] = jl(r.get("identity_detail"))
    out["active"] = bool(active_id and r["id"] == active_id)
    ext = jl(r.get("extraction")) if r.get("extraction") else None
    out["warnings"] = (ext or {}).get("gaps", [])
    out["extracted_name"] = (ext or {}).get("full_name")
    out["message"] = STAGE_TEXT[r["stage"]] if r["stage"] != "ready" or identity.usable(r.get("identity_status")) else \
        "Not applied: this CV appears to belong to someone else"
    return out


STAGE_TEXT = {"uploaded": "Upload received", "extracting": "Reading your CV…", "analysing": "Analysing profile…",
              "ready": "Profile ready to review", "failed": "Could not process this file"}


@bp.post("/me/cvs")
@require("candidate")
def my_upload():
    cand = ctx().db.one("SELECT id FROM candidates WHERE user_id=?", (g.user["id"],))
    return store_cvs(cand["id"])


@bp.post("/candidates/<cid>/cvs")
@require(*REC)
def rec_upload(cid):
    return store_cvs(get_candidate(cid)["id"])


@bp.get("/cvs/<cv_id>")
@require()
def cv_status(cv_id):
    row = get_cv(cv_id)
    return jsonify(cv_out(row, ctx().db.scalar("SELECT active_cv_id FROM candidates WHERE id=?", (row["candidate_id"],))))


@bp.get("/cvs/<cv_id>/file")
@require(*REC, "candidate")
def cv_file(cv_id):
    row = get_cv(cv_id)
    audit("cv.download", "cv", cv_id)
    return Response(ctx().storage.get(row["storage_key"]), mimetype=row["mime"],
                    headers={"Content-Disposition": f'attachment; filename="{row["original_name"]}"'})


@bp.get("/cvs/<cv_id>/text")
@require(*REC, "candidate")
def cv_text(cv_id):
    """The plain text actually extracted from the uploaded file (what the parser worked from). Rendered as text by the UI."""
    row = get_cv(cv_id)
    if g.user["role"] != "candidate": audit("cv.text_view", "cv", cv_id)
    txt = row["extracted_text"] or ""
    return jsonify({"id": cv_id, "name": row["original_name"], "stage": row["stage"], "chars": len(txt), "text": txt[:30000], "truncated": len(txt) > 30000})


@bp.post("/me/cvs/<cv_id>/use")
@require("candidate")
def use_my_cv(cv_id):
    """Make one of my processed CVs the source of my profile. A CV that appears to belong to someone else needs an
    explicit confirmation (e.g. after a change of name); the confirmation is audit-logged."""
    c = ctx()
    d = body(O({"confirm_mine": {"type": "boolean"}}))
    cv = get_cv(cv_id)
    if cv["stage"] != "ready": raise ApiError(409, "not_ready", "This CV has not been processed successfully.")
    if cv["identity_status"] == "mismatch":
        if not d.get("confirm_mine"):
            raise ApiError(409, "identity_mismatch", (jl(cv["identity_detail"]) or {}).get("reason", "This CV appears to belong to someone else."))
        c.db.execute("UPDATE cvs SET identity_status='confirmed' WHERE id=?", (cv_id,))
        audit("cv.identity_confirmed", "cv", cv_id, {"cv_name": (jl(cv["identity_detail"]) or {}).get("cv_name")})
    pl.apply_cv_to_candidate(c, cv_id)
    audit("cv.activated", "cv", cv_id)
    return my_profile()


@bp.delete("/me/cvs/<cv_id>")
@require("candidate")
def delete_my_cv(cv_id):
    c = ctx()
    cv = get_cv(cv_id)
    if c.db.one("SELECT 1 AS x FROM applications WHERE cv_id=?", (cv_id,)):
        raise ApiError(409, "cv_in_use", "This CV was used for an application, so it is kept as the record of what you sent.")
    with c.db.tx():
        c.db.execute("UPDATE candidates SET active_cv_id=NULL WHERE active_cv_id=?", (cv_id,))
        c.db.execute("DELETE FROM cvs WHERE id=?", (cv_id,))
    c.storage.delete(cv["storage_key"])
    audit("cv.deleted", "cv", cv_id)
    return jsonify({"ok": True})


@bp.post("/cvs/<cv_id>/reassign")
@require(*REC)
def reassign_cv(cv_id):
    """Recruiter/admin: a CV on the wrong record is moved, with the applications made with it, to the record of the person
    it belongs to (found by the CV's email, or created). Only CVs flagged as belonging to someone else can be moved."""
    c = ctx()
    cv = get_cv(cv_id)
    if cv["identity_status"] != "mismatch":
        raise ApiError(409, "not_mismatched", "Only a CV flagged as belonging to someone else can be moved.")
    det = jl(cv["identity_detail"]) or {}
    org = my_org()
    apps = c.db.all("SELECT a.id, j.organization_id FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.cv_id=?", (cv_id,))
    if g.user["role"] == "recruiter" and any(a["organization_id"] != org for a in apps):
        raise ApiError(403, "forbidden", "This CV was also used for another organisation's opening; ask an administrator.")
    org = org or (apps[0]["organization_id"] if apps else None)
    email = (det.get("cv_email") or "").lower() or None
    target = c.db.one("SELECT * FROM candidates WHERE email=?", (email,)) if email else None
    if target is None:
        if not det.get("cv_name"):
            raise ApiError(409, "no_identity", "The CV has no readable name, so a record cannot be created for its owner.")
        ext = jl(cv["extraction"]) or {}
        tid, t = uid(), now()
        c.db.execute("INSERT INTO candidates (id,managed_by_org_id,email,full_name,phone,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                     (tid, org, email or f"no-email+{tid[:12]}@invalid.local", det["cv_name"], ext.get("phone"), t, t))
        audit("candidate.create", "candidate", tid, {"from_cv": cv_id})
    else:
        tid = target["id"]
    try:
        moved = pl.reassign_cv(c, cv_id, tid, g.user, request.remote_addr)
    except ValueError as e:
        raise ApiError(409, "conflict", str(e))
    for aid in moved:
        pl.recompute_match(c, aid, reason="CV moved to its owner's record")
    return jsonify({"ok": True, "candidate_id": tid, "applications_moved": moved})


# ------------------------------------------------------------------ candidate self-service
PROFILE_EDIT = {**CV_SCHEMA, "properties": {k: v for k, v in CV_SCHEMA["properties"].items() if k not in ("confidence",)},
                "required": ["full_name", "education", "work_history", "skills"]}


def cand_out(r, full=True):
    out = {k: r[k] for k in ("id", "full_name", "email", "phone", "profile_status", "total_years", "created_at")}
    out["top_skills"] = jl(r["top_skills"], [])
    if full: out["profile"] = jl(r["profile"])
    return out


@bp.get("/me/profile")
@require("candidate")
def my_profile():
    c = ctx()
    r = c.db.one("SELECT * FROM candidates WHERE user_id=?", (g.user["id"],))
    cvs = c.db.all("SELECT * FROM cvs WHERE candidate_id=? ORDER BY created_at DESC LIMIT 10", (r["id"],))
    used = {x["cv_id"] for x in c.db.all("SELECT cv_id FROM applications WHERE candidate_id=?", (r["id"],))}
    return jsonify({**cand_out(r), "cvs": [{**cv_out(x, r["active_cv_id"]), "used_in_application": x["id"] in used} for x in cvs],
                    "applications": c.db.scalar("SELECT COUNT(*) FROM applications WHERE candidate_id=?", (r["id"],))})


@bp.patch("/me/profile")
@require("candidate")
def edit_profile():
    d = body(O({"full_name": S(minLength=2, maxLength=120), "phone": S(maxLength=40, nullable=True),
                "profile": {"type": "object", "additionalProperties": True}, "confirm": {"type": "boolean"}}))
    c = ctx()
    r = c.db.one("SELECT * FROM candidates WHERE user_id=?", (g.user["id"],))
    upd = {}
    if "full_name" in d: upd["full_name"] = d["full_name"]
    if "phone" in d: upd["phone"] = d["phone"]
    if "profile" in d:
        p = dict(d["profile"])
        for k in ("total_experience_years", "confidence", "extracted_by", "ai_additions", "text_source"): p.pop(k, None)   # server-owned fields
        try:
            p = validate(p, PROFILE_EDIT)
        except ValidationError as e:
            raise ApiError(422, "validation_failed", "Profile has invalid fields.", e.errors)
        p = normalise(p)
        before = jl(r["profile"], {}) or {}
        for k in ("extracted_by", "ai_additions", "text_source"):      # keep how the CV was read, for the reviewer
            if before.get(k): p[k] = before[k]
        yrs, top = summary_fields(p)
        upd.update(profile=jd(p), total_years=yrs, top_skills=jd(top))
        upd["profile_status"] = "draft"
    if d.get("confirm"):
        if not (upd.get("profile") or r["profile"]): raise ApiError(409, "no_profile", "Upload a CV before confirming your profile.")
        upd["profile_status"] = "confirmed"
    if not upd: raise ApiError(422, "nothing_to_update", "No changes supplied.")
    upd["updated_at"] = now()
    c.db.execute(f"UPDATE candidates SET {', '.join(k + '=?' for k in upd)} WHERE id=?", list(upd.values()) + [r["id"]])
    # applications already made keep the profile they were submitted with; edits apply to future applications
    audit("candidate.profile_update", "candidate", r["id"], {"fields": [k for k in upd if k != "updated_at"], "confirmed": bool(d.get("confirm"))})
    return jsonify(cand_out(c.db.one("SELECT * FROM candidates WHERE id=?", (r["id"],))))


def erase_candidate(c, cand):
    keys = [x["storage_key"] for x in c.db.all("SELECT storage_key FROM cvs WHERE candidate_id=?", (cand["id"],))]
    # similarity findings on OTHER people's applications that point at this person must not outlive the deletion
    touched = set()
    for o in c.db.all("SELECT o.detail, o.kind FROM originality_checks o JOIN applications a ON a.id=o.application_id WHERE a.candidate_id=?", (cand["id"],)):
        touched |= {(m["application_id"], o["kind"]) for m in (jl(o["detail"], {}) or {}).get("matches", [])}
    with c.db.tx():
        c.db.execute("DELETE FROM candidates WHERE id=?", (cand["id"],))      # cascades: cvs, applications, assessments, evaluations, matches, reviews
        if cand["user_id"]:
            c.db.execute("DELETE FROM users WHERE id=?", (cand["user_id"],))   # cascades sessions
    for k in keys: c.storage.delete(k)
    for aid, kind in touched:
        if c.db.one("SELECT 1 AS x FROM applications WHERE id=?", (aid,)):
            pl.enqueue(c, "originality", {"application_id": aid, "kind": kind})
    audit("candidate.erased", "candidate", cand["id"], {"cv_files": len(keys)})   # id only, no personal data


@bp.delete("/me")
@require("candidate")
def delete_me():
    d = body(O({"password": S(minLength=1, maxLength=128)}, ["password"]))
    if not verify_password(d["password"], g.user["password_hash"]):
        raise ApiError(403, "wrong_password", "Password is incorrect.")
    cand = ctx().db.one("SELECT * FROM candidates WHERE user_id=?", (g.user["id"],))
    erase_candidate(ctx(), cand)
    return jsonify({"ok": True})


@bp.delete("/candidates/<cid>")
@require(*REC)
def delete_candidate(cid):
    cand = get_candidate(cid)
    if g.user["role"] == "recruiter" and (cand["user_id"] or cand["managed_by_org_id"] != my_org()):
        raise ApiError(403, "forbidden", "Only records your organisation created (and the candidate has not claimed) can be deleted.")
    erase_candidate(ctx(), cand)
    return jsonify({"ok": True})


# ------------------------------------------------------------------ jobs
JOB_SCHEMA = O({
    "title": S(minLength=3, maxLength=140), "kind": S(enum=["job", "competition"]), "description": S(maxLength=4000),
    "required_skills": A(S(minLength=1, maxLength=60), minItems=1, maxItems=25), "preferred_skills": A(S(minLength=1, maxLength=60), maxItems=25),
    "custom_requirements": A(S(minLength=3, maxLength=200), maxItems=10), "min_years": N(minimum=0, maximum=50),
    "education_level": S(enum=["none", "high_school", "diploma", "bachelor", "master", "phd"]),
    "task_brief": S(maxLength=1500, nullable=True), "status": S(enum=["draft", "open", "closed"]),
    "auto_assessment": {"type": "boolean"}, "test_questions": I(minimum=3, maximum=6),
    "deadline": S(maxLength=10, nullable=True, pattern=r"^\d{4}-\d{2}-\d{2}$")}, ["title"])


def suggest_skills(text):
    """Skills from the built-in list that a job description names, in order of first appearance."""
    from . import skills_data as sd
    found = sd.find_skills(text or "")
    # bare ambiguous words (R, Go ...) are skipped on purpose: they are only trusted inside an explicit skills list
    ordered = sorted(found.items(), key=lambda kv: kv[1][0][0])
    return [{"name": sd.display(k), "family": sd.FAMILY.get(k)} for k, _ in ordered]


@bp.post("/jobs/suggest-skills")
@require(*REC)
def suggest_job_skills():
    d = body(O({"description": S(maxLength=4000)}, ["description"]))
    return jsonify({"skills": suggest_skills(d["description"])})


@bp.post("/jobs")
@require(*REC)
def create_job():
    if g.user["role"] == "admin": raise ApiError(403, "forbidden", "Create jobs from a recruiter account.")
    d = body(JOB_SCHEMA)
    if not d.get("required_skills"):       # a pasted job description is enough: take the skills it names
        found = suggest_skills(d.get("description", ""))
        if not found:
            raise ApiError(422, "validation_failed", "Some fields are invalid.",
                           {"required_skills": "add at least one required skill (none could be found in the description)"})
        d["required_skills"] = [x["name"] for x in found][:8]
    jid, t = uid(), now()
    ctx().db.execute("""INSERT INTO jobs (id,organization_id,created_by,title,kind,description,required_skills,preferred_skills,custom_requirements,
        min_years,education_level,task_brief,status,deadline,auto_assessment,test_questions,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (jid, my_org(), g.user["id"], d["title"], d.get("kind", "job"), d.get("description", ""), jd(d["required_skills"]),
                      jd(d.get("preferred_skills", [])), jd(d.get("custom_requirements", [])), d.get("min_years", 0),
                      d.get("education_level", "none"), d.get("task_brief"), d.get("status", "open"), d.get("deadline"),
                      int(bool(d.get("auto_assessment", False))), d.get("test_questions", 4), t, t))
    audit("job.create", "job", jid, {"title": d["title"]})
    return jsonify(job_out(ctx().db.one("SELECT * FROM jobs WHERE id=?", (jid,)))), 201


@bp.get("/jobs")
@require()
def list_jobs():
    page, limit, off = paging()
    c = ctx()
    where, args = [], []
    if g.user["role"] == "candidate":
        where.append("j.status='open'")
    elif g.user["role"] == "recruiter":
        where.append("j.organization_id=?"); args.append(my_org())
    if request.args.get("status") and g.user["role"] != "candidate":
        where.append("j.status=?"); args.append(request.args["status"])
    if request.args.get("q"):
        where.append("LOWER(j.title) LIKE ?"); args.append("%" + request.args["q"].lower() + "%")
    if request.args.get("kind") in ("job", "competition"):
        where.append("j.kind=?"); args.append(request.args["kind"])
    w = " AND ".join(where) or "1=1"
    total = c.db.scalar(f"SELECT COUNT(*) FROM jobs j WHERE {w}", args)
    rows = c.db.all(f"""SELECT j.*, (SELECT COUNT(*) FROM applications a WHERE a.job_id=j.id) AS applicants
                        FROM jobs j WHERE {w} ORDER BY j.created_at DESC, j.id LIMIT ? OFFSET ?""", args + [limit, off])
    shaper = public_job if g.user["role"] == "candidate" else job_out
    return envelope([{**shaper(r), **({"applicants": r["applicants"]} if g.user["role"] != "candidate" else {})} for r in rows], total, page, limit)


@bp.get("/jobs/<jid>")
@require()
def one_job(jid):
    r = get_job(jid, recruiter_only=g.user["role"] != "candidate")
    return jsonify(public_job(r) if g.user["role"] == "candidate" else job_out(r))


@bp.patch("/jobs/<jid>")
@require(*REC)
def edit_job(jid):
    get_job(jid)
    d = body({**JOB_SCHEMA, "required": []})
    if not d: raise ApiError(422, "nothing_to_update", "No changes supplied.")
    for k in ("required_skills", "preferred_skills", "custom_requirements"):
        if k in d: d[k] = jd(d[k])
    if "auto_assessment" in d: d["auto_assessment"] = int(bool(d["auto_assessment"]))
    d["updated_at"] = now()
    ctx().db.execute(f"UPDATE jobs SET {', '.join(k + '=?' for k in d)} WHERE id=?", list(d.values()) + [jid])
    audit("job.update", "job", jid, {"fields": list(d)})
    return jsonify(job_out(ctx().db.one("SELECT * FROM jobs WHERE id=?", (jid,))))


# ------------------------------------------------------------------ applications
def create_application(job, cand, actor_label):
    c = ctx()
    if job["status"] != "open": raise ApiError(409, "job_closed", "This opening is not accepting applications.")
    if not cand["profile"]: raise ApiError(409, "no_profile", "A processed CV/profile is required first.")
    prev = c.db.one("SELECT id FROM applications WHERE job_id=? AND candidate_id=?", (job["id"], cand["id"]))
    if prev:      # one application per person per opening; the repeat attempt is kept in that application's history for the reviewer
        pl.log(c, "application.repeat_attempt", "application", prev["id"], {"note": "tried to apply to this opening again; one application is kept", "by": actor_label},
               g.user["id"], g.user["role"], request.remote_addr)
        raise ApiError(409, "already_applied", "Already applied to this opening.")
    cv = c.db.one("SELECT id, identity_status FROM cvs WHERE id=? AND candidate_id=? AND stage='ready'", (cand["active_cv_id"], cand["id"])) \
        if cand.get("active_cv_id") else None
    if cv and not identity.usable(cv["identity_status"]):
        raise ApiError(409, "identity_mismatch", "The CV on this profile appears to belong to someone else. Resolve that first.")
    aid, t = uid(), now()
    try:   # the application is pinned to this CV and this profile: later uploads or edits cannot change what was submitted
        c.db.execute("INSERT INTO applications (id,job_id,candidate_id,cv_id,status,profile_snapshot,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                     (aid, job["id"], cand["id"], cv["id"] if cv else None, "applied", cand["profile"], t, t))
    except Exception as e:      # UNIQUE(job_id, candidate_id): a double click raced the check above
        if "unique" in str(e).lower(): raise ApiError(409, "already_applied", "Already applied to this opening.")
        raise
    audit("application.create", "application", aid, {"job_id": job["id"], "by": actor_label, "cv_id": cv["id"] if cv else None})
    pl.recompute_match(c, aid)
    pl.enqueue(c, "analyse_application", {"application_id": aid})
    pl.enqueue(c, "originality", {"application_id": aid, "kind": "cv"})
    return aid


@bp.post("/jobs/<jid>/apply")
@require("candidate")
def apply(jid):
    job = get_job(jid, recruiter_only=False)
    cand = ctx().db.one("SELECT * FROM candidates WHERE user_id=?", (g.user["id"],))
    if cand["profile_status"] != "confirmed": raise ApiError(409, "profile_not_confirmed", "Confirm your profile before applying.")
    return jsonify({"id": create_application(job, cand, "candidate")}), 201


@bp.post("/jobs/<jid>/applications")
@require("recruiter")
def add_application(jid):
    d = body(O({"candidate_id": S(minLength=1, maxLength=64)}, ["candidate_id"]))
    job = get_job(jid)
    cand = get_candidate(d["candidate_id"])
    return jsonify({"id": create_application(job, cand, "recruiter")}), 201


def _latest_assessment(aid):
    return ctx().db.one("SELECT * FROM assessments WHERE application_id=? ORDER BY attempt DESC LIMIT 1", (aid,))


def _candidate_eval(s):
    """The evaluation as the candidate may see it: scores, criteria, feedback. Never recruiter notes, overrides or decisions."""
    if not s or s["status"] != "evaluated" or not ctx().cfg.candidate_sees_results:
        return None
    e = ctx().db.one("SELECT * FROM evaluations WHERE assessment_id=?", (s["id"],))
    if not e:
        return None
    r = jl(e["result"])
    prompts = {q["id"]: q["prompt"] for q in jl(s["task"])["questions"]}
    resp = ctx().db.one("SELECT answers FROM assessment_responses WHERE assessment_id=?", (s["id"],))
    answers = jl(resp["answers"], {}) if resp else {}
    return {"overall": r["overall"], "confidence": r["confidence"], "criteria": r["criteria"], "strengths": r["strengths"], "gaps": r["gaps"],
            "summary": r["summary"], "language_notes": r.get("language_notes", []), "flags": r.get("flags", []), "engine": e["model"],
            "scorable_answers": r.get("scorable_answers"), "method": r.get("method"),
            "per_question": [{**{k: q.get(k) for k in ("question_id", "score", "max_points", "rationale", "evidence", "answer_status", "covered", "missed")},
                              "prompt": prompts.get(q["question_id"], ""), "answer": answers.get(q["question_id"], "")} for q in r["per_question"]]}


@bp.get("/me/applications")
@require("candidate")
def my_applications():
    rows = ctx().db.all("""SELECT a.id, a.job_id, a.status, a.match_score, a.created_at, a.updated_at, j.title, j.kind,
        (SELECT s.id FROM assessments s WHERE s.application_id=a.id AND s.status IN ('sent','started') ORDER BY s.attempt DESC LIMIT 1) AS open_assessment_id,
        (SELECT ev.overall FROM evaluations ev JOIN assessments s ON s.id=ev.assessment_id WHERE s.application_id=a.id ORDER BY s.attempt DESC LIMIT 1) AS assessment_score
        FROM applications a JOIN jobs j ON j.id=a.job_id JOIN candidates c ON c.id=a.candidate_id
        WHERE c.user_id=? ORDER BY a.created_at DESC LIMIT 100""", (g.user["id"],))
    show = ctx().cfg.candidate_sees_results
    return jsonify({"data": [{**r, "status_label": workflow.CANDIDATE_LABEL[r["status"]],
                              "match_score": r["match_score"] if show else None, "assessment_score": r["assessment_score"] if show else None} for r in rows]})


@bp.get("/me/applications/<aid>")
@require("candidate")
def my_application(aid):
    c = ctx()
    a = get_application(aid)                        # 404 unless it is this candidate's own application
    m = c.db.one("SELECT * FROM matches WHERE application_id=?", (aid,))
    s = _latest_assessment(aid)
    match = match_public(jl(m["breakdown"])) if m and c.cfg.candidate_sees_results else None
    cv = c.db.one("SELECT id, original_name FROM cvs WHERE id=?", (a["cv_id"],)) if a["cv_id"] else None
    return jsonify({"id": aid, "job": {"id": a["job_id"], "title": a["job_title"]}, "status": a["status"], "status_label": workflow.CANDIDATE_LABEL[a["status"]],
                    "created_at": a["created_at"], "match": match, "cv": cv,
                    "assessment": ({"id": s["id"], "status": s["status"], "minutes": s["minutes"], "due_at": s["due_at"], "state": assessment_state(s),
                                    "available": s["status"] in ("sent", "started")} if s and s["status"] not in ("generating", "draft", "failed") else
                                   {"status": "preparing", "state": assessment_state(s)} if s and s["status"] in ("generating", "draft") else None),
                    "evaluation": _candidate_eval(s), "messages": application_messages(aid, for_candidate=True),
                    "attempt": s["attempt"] if s else None})


def assessment_state(s, response=None, evaluation=None):
    """One plain status for an attempt: (code, label). Distinguishes 'no usable answers' and 'scoring failed' from a low score."""
    c = ctx()
    if s is None: return None
    if response is None:
        response = c.db.one("SELECT saved_at, submitted_at FROM assessment_responses WHERE assessment_id=?", (s["id"],))
    st, ev = s["status"], s.get("eval_status")
    if st == "generating": return {"code": "preparing", "label": "Being prepared"}
    if st == "failed": return {"code": "generation_failed", "label": "Could not be generated"}
    if st == "draft": return {"code": "not_sent", "label": "Not sent yet"}
    if st == "sent": return {"code": "sent", "label": "Sent, not started"}
    if st == "started": return {"code": "draft", "label": "Draft saved" if response else "In progress", "saved_at": response["saved_at"] if response else None}
    if st == "submitted":
        if ev == "failed": return {"code": "needs_review", "label": "Needs review: automatic scoring failed (answers are safe)", "error": s.get("eval_error")}
        if ev == "retrying": return {"code": "processing", "label": "Processing (retrying scoring)"}
        return {"code": "processing", "label": "Submitted, being scored"}
    if st == "evaluated":
        if evaluation is None:
            e = c.db.one("SELECT result FROM evaluations WHERE assessment_id=?", (s["id"],))
            evaluation = jl(e["result"]) if e else {}
        if evaluation.get("scorable_answers") == 0:
            return {"code": "needs_review", "label": "Needs review: no answer was long enough to score"}
        return {"code": "scored", "label": "Scored"}
    return {"code": st, "label": st}


@bp.get("/me/match/<jid>")
@require("candidate")
def preview_match(jid):
    """How the candidate's current profile lines up with an opening BEFORE applying. Nothing is stored. Uses the same
    calculation as the stored application match, so applying now gives the same CV match."""
    c = ctx()
    job = job_out(get_job(jid, recruiter_only=False))
    cand = c.db.one("SELECT * FROM candidates WHERE user_id=?", (g.user["id"],))
    if not cand["profile"]: raise ApiError(409, "no_profile", "Upload a CV first so there is something to compare.")
    cv = c.db.one("SELECT extracted_text FROM cvs WHERE id=?", (cand["active_cv_id"],)) if cand["active_cv_id"] else None
    m = pl.match_for(c, jl(cand["profile"]), job, None, cv["extracted_text"] if cv else None)
    return jsonify({"job": {"id": job["id"], "title": job["title"]}, "profile_status": cand["profile_status"], **match_public(m)})


MATCH_KEYS = ("score", "cv_score", "provisional", "components", "skills", "experience", "education", "requirements", "similarity",
              "limitations", "assessment", "scoring_version", "method", "as_of")


def match_public(m):
    return {k: m.get(k) for k in MATCH_KEYS}


SORTS = {"match": "a.match_score DESC, a.id", "newest": "a.created_at DESC, a.id", "name": "LOWER(c.full_name), a.id"}


@bp.get("/jobs/<jid>/applications")
@require(*REC)
def job_applications(jid):
    get_job(jid)
    page, limit, off = paging()
    where, args = ["a.job_id=?"], [jid]
    if request.args.get("stage"):
        where.append("a.status=?"); args.append(request.args["stage"])
    if request.args.get("q"):
        where.append("(LOWER(c.full_name) LIKE ? OR LOWER(c.email) LIKE ?)"); q = "%" + request.args["q"].lower() + "%"; args += [q, q]
    if request.args.get("min_score"):
        where.append("a.match_score>=?"); args.append(float(request.args["min_score"]))
    if request.args.get("flagged") == "1":      # open similarity findings: flagged and not yet cleared by a reviewer
        where.append("""EXISTS (SELECT 1 FROM originality_checks o WHERE o.application_id=a.id AND o.level IN ('medium','high')
                                AND (o.verdict IS NULL OR o.verdict != 'cleared'))""")
    w = " AND ".join(where)
    order = SORTS.get(request.args.get("sort", "match"), SORTS["match"])
    total = ctx().db.scalar(f"SELECT COUNT(*) FROM applications a JOIN candidates c ON c.id=a.candidate_id WHERE {w}", args)
    rows = ctx().db.all(f"""SELECT a.id, a.status, a.match_score, a.cv_match_score, a.created_at, a.profile_snapshot, c.id AS candidate_id, c.full_name, c.email,
        (SELECT ev.overall FROM evaluations ev JOIN assessments s ON s.id=ev.assessment_id WHERE s.application_id=a.id ORDER BY s.attempt DESC LIMIT 1) AS assessment_score,
        (SELECT s.eval_status FROM assessments s WHERE s.application_id=a.id ORDER BY s.attempt DESC LIMIT 1) AS eval_status
        FROM applications a JOIN candidates c ON c.id=a.candidate_id WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?""", args + [limit, off])
    from .profile import summary_fields
    levels = originality.summary_levels(ctx(), [r["id"] for r in rows])
    for r in rows:      # years and skills come from the profile this application was made with, like everything else on it
        p = jl(r.pop("profile_snapshot")) or {}
        r["total_years"], r["top_skills"] = summary_fields(p) if p else (None, [])
        r["status_label"] = workflow.LABEL[r["status"]]
        r["originality"] = levels.get(r["id"])
    return envelope(rows, total, page, limit)


@bp.get("/applications/<aid>")
@require(*REC)
def application_detail(aid):
    c = ctx()
    a = get_application(aid)
    cand = c.db.one("SELECT * FROM candidates WHERE id=?", (a["candidate_id"],))
    m = c.db.one("SELECT * FROM matches WHERE application_id=?", (aid,))
    ass = []
    for s in c.db.all("SELECT * FROM assessments WHERE application_id=? ORDER BY attempt", (aid,)):
        r = c.db.one("SELECT answers, saved_at, submitted_at, task_hash FROM assessment_responses WHERE assessment_id=?", (s["id"],))
        e = c.db.one("SELECT * FROM evaluations WHERE assessment_id=?", (s["id"],))
        ev = {**jl(e["result"]), "model": e["model"], "prompt_version": e["prompt_version"], "scored_at": e["created_at"]} if e else None
        task = jl(s["task"])
        answers = jl(r["answers"]) if r else None
        # answers are shown next to the exact question they answer; the candidate-facing draft is only visible once submitted
        shown = answers if (r and r["submitted_at"]) else None
        ass.append({**{k: s[k] for k in ("id", "attempt", "status", "minutes", "sent_at", "started_at", "submitted_at", "due_at", "eval_status", "eval_error")},
                    "questions_by": s["model"],
                    "task": task, "answers": shown, "draft_saved_at": r["saved_at"] if r and not r["submitted_at"] else None,
                    "state": assessment_state(s, r, (ev or {})), "evaluation": ev,
                    "activity": integrity.summary(c, s["id"]),
                    "can_retry_scoring": s["status"] == "submitted" and s["eval_status"] == "failed"})
    reviews = c.db.all("""SELECT r.task_score, r.note, r.decision, r.created_at, COALESCE(rc.full_name, u.email) AS reviewer FROM reviews r
                          JOIN users u ON u.id=r.reviewer_id LEFT JOIN recruiters rc ON rc.user_id=u.id WHERE r.application_id=? ORDER BY r.created_at""", (aid,))
    sids = [x["id"] for x in ass]
    timeline = c.db.all(f"""SELECT action, actor_role, detail, created_at FROM activity_logs
                            WHERE (entity_type='application' AND entity_id=?) {"OR (entity_type='assessment' AND entity_id IN (" + ",".join("?" * len(sids)) + "))" if sids else ""}
                            ORDER BY created_at, id""", [aid] + sids)
    cv = c.db.one("SELECT * FROM cvs WHERE id=?", (a["cv_id"],)) if a["cv_id"] else None
    history = c.db.all("SELECT score, computed_at, replaced_at, reason FROM match_history WHERE application_id=? ORDER BY replaced_at DESC LIMIT 20", (aid,))
    return jsonify({"id": aid, "status": a["status"], "created_at": a["created_at"], "job": {"id": a["job_id"], "title": a["job_title"]},
                    "candidate": cand_out(cand, full=False), "profile": jl(a["profile_snapshot"]),
                    "cv": cv_out(cv, cand["active_cv_id"]) if cv else None,
                    "match": {**jl(m["breakdown"]), "ai_analysis": jl(m["ai_analysis"]), "computed_at": m["computed_at"]} if m else None,
                    "match_history": history, "assessments": ass, "reviews": reviews,
                    "originality": originality.view(c, aid, None if g.user["role"] == "admin" else a["org_id"]),
                    "messages": application_messages(aid), "second_attempt_hint": second_attempt_hint(m, ass),
                    "timeline": [{**t, "detail": jl(t["detail"])} for t in timeline],
                    "allowed_next": allowed_next(a, ass)})


def second_attempt_hint(m, ass):
    """Plain words for the reviewer when the CV and the test disagree. A prompt to look, never an action."""
    last = ass[-1] if ass else None
    ev = (last or {}).get("evaluation")
    cv = (jl(m["breakdown"]) or {}).get("cv_score") if m else None
    if not ev or cv is None or last["status"] != "evaluated":
        return None
    if cv >= 70 and ev["overall"] < 50:
        return (f"The CV matches this opening well ({round(cv)}%) but the skill test went poorly ({round(ev['overall'])}/100). "
                "If you think the test did not show what this person can do, you can offer a second attempt. It is entirely your call.")
    return None


def allowed_next(a, ass):
    nxt = workflow.TRANSITIONS[a["status"]] & workflow.MANUAL
    if a["status"] == "assessment_submitted" and not any(x["can_retry_scoring"] for x in ass):
        nxt = nxt - {"human_review"}            # only when automatic scoring has failed; otherwise wait for the score
    return [s for s in workflow.STAGES if s in nxt]


@bp.post("/applications/<aid>/transition")
@require("recruiter")
def transition(aid):
    c = ctx()
    d = body(O({"to": S(enum=sorted(workflow.MANUAL)), "note": S(maxLength=500)}, ["to"]))
    a = get_application(aid)
    if not workflow.can(a["status"], d["to"]):
        raise ApiError(409, "invalid_transition", f"Cannot move from {workflow.LABEL[a['status']]} to {workflow.LABEL[d['to']]}.")
    if a["status"] == "assessment_submitted" and not c.db.one(
            "SELECT 1 AS x FROM assessments WHERE application_id=? AND status='submitted' AND eval_status='failed'", (aid,)):
        raise ApiError(409, "scoring_pending", "The assessment is still being scored. Wait for the result or for scoring to fail.")
    with c.db.tx():
        if c.db.scalar("SELECT status FROM applications WHERE id=?", (aid,)) != a["status"]:
            raise ApiError(409, "stale", "Someone else changed this application. Reload and try again.")
        pl.set_status(c, aid, d["to"], g.user, d.get("note"), request.remote_addr)
    return jsonify({"ok": True, "status": d["to"]})


@bp.post("/assessments/<sid>/rescore")
@require("recruiter")
def rescore(sid):
    """Retry automatic scoring after it failed. The submitted answers are untouched; a scored attempt cannot be rescored."""
    c = ctx()
    s = get_assessment(sid)
    if s["status"] != "submitted" or s["eval_status"] not in ("failed", None):
        raise ApiError(409, "not_rescorable", "Only a submitted assessment whose scoring failed can be scored again.")
    c.db.execute("UPDATE assessments SET eval_status='queued', eval_error=NULL WHERE id=?", (sid,))
    pl.enqueue(c, "evaluate_assessment", {"assessment_id": sid})
    audit("assessment.rescore_requested", "assessment", sid, {"application_id": s["app_id"]})
    return jsonify({"ok": True, "eval_status": "queued"}), 202


# ------------------------------------------------------------------ assessments (recruiter side)
@bp.post("/applications/<aid>/assessment")
@require("recruiter")
def create_assessment(aid):
    c = ctx()
    a = get_application(aid)
    if a["status"] not in ("applied", "cv_reviewed", "ai_evaluated"):
        raise ApiError(409, "invalid_stage", "An assessment can't be created at this stage.")
    live = c.db.one("SELECT id FROM assessments WHERE application_id=? AND status NOT IN ('failed','evaluated')", (aid,))
    if live: raise ApiError(409, "assessment_exists", "This application already has an assessment in progress.")
    n = (c.db.scalar("SELECT MAX(attempt) FROM assessments WHERE application_id=?", (aid,)) or 0) + 1
    sid = uid()
    c.db.execute("INSERT INTO assessments (id,application_id,attempt,status,created_at) VALUES (?,?,?,?,?)", (sid, aid, n, "generating", now()))
    pl.enqueue(c, "generate_assessment", {"assessment_id": sid})
    audit("assessment.create", "assessment", sid, {"application_id": aid, "attempt": n})
    return jsonify({"id": sid, "status": "generating"}), 202


@bp.patch("/assessments/<sid>")
@require("recruiter")
def edit_assessment(sid):
    s = get_assessment(sid)
    if s["status"] != "draft": raise ApiError(409, "not_editable", "Only drafts can be edited.")
    data = request.get_json(silent=True)
    try:
        task = validate(data, ASSESSMENT_SCHEMA)
    except ValidationError as e:
        raise ApiError(422, "validation_failed", "Assessment has invalid fields.", e.errors)
    old = {q["id"]: q for q in (jl(s["task"], {}) or {}).get("questions", [])}
    for q in task["questions"]:          # the private scoring points survive an edit unless the editor sends new ones
        if "expected_points" not in q and old.get(q["id"], {}).get("expected_points"):
            q["expected_points"] = old[q["id"]]["expected_points"]
    task = normalise_task(task)
    ctx().db.execute("UPDATE assessments SET task=?, minutes=? WHERE id=?", (jd(task), task["minutes"], sid))
    audit("assessment.edit", "assessment", sid)
    return jsonify({"ok": True, "task": task})


@bp.post("/assessments/<sid>/send")
@require("recruiter")
def send_assessment(sid):
    c = ctx()
    s = get_assessment(sid)
    if s["status"] != "draft" or not s["task"]: raise ApiError(409, "not_sendable", "Only a generated draft can be sent.")
    app_ = get_application(s["app_id"])
    if not workflow.can(app_["status"], "assessment_sent"):
        raise ApiError(409, "invalid_stage", f"Cannot send an assessment while the application is '{app_['status']}'.")
    cand = c.db.one("SELECT full_name, email FROM candidates WHERE id=?", (s["candidate_id"],))
    t = now()
    due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="microseconds")
    from .mail import queue_email, render
    with c.db.tx():
        c.db.execute("UPDATE assessments SET status='sent', sent_at=?, due_at=? WHERE id=?", (t, due, sid))
        pl.set_status(c, app_["id"], "assessment_sent", g.user, None, request.remote_addr)
        queue_email(c, cand["email"], *render("assessment_ready", name=cand["full_name"], job=app_["job_title"], minutes=s["minutes"],
                                               url=f"{c.cfg.public_url}/#/assessment/{sid}"), kind="assessment_ready")
    audit("assessment.send", "assessment", sid, {"to_candidate": s["candidate_id"]})
    return jsonify({"ok": True})


@bp.post("/assessments/<sid>/retake")
@require("recruiter")
def retake(sid):
    """A reviewer offers a second attempt (their decision alone: e.g. a strong CV with a weak test, or a bad day). The earlier
    attempt, its answers and its score are kept. `fresh` writes new questions instead of reusing the same ones; `send` gives it
    to the candidate straight away instead of leaving a draft to edit."""
    c = ctx()
    try:      # the body is optional: a plain POST creates a draft with the same questions, as before
        d = validate(request.get_json(silent=True) or {}, O({"fresh": {"type": "boolean"}, "send": {"type": "boolean"}, "note": S(maxLength=500)}))
    except ValidationError as e:
        raise ApiError(422, "validation_failed", "Some fields are invalid.", e.errors)
    s = get_assessment(sid)
    if not (s["status"] == "evaluated" or (s["status"] == "submitted" and s["eval_status"] == "failed")):
        raise ApiError(409, "not_retakable", "Only a scored attempt, or one whose scoring failed, can be retaken.")
    if c.db.one("SELECT id FROM assessments WHERE application_id=? AND status NOT IN ('failed','evaluated') AND id != ?", (s["app_id"], sid)):
        raise ApiError(409, "assessment_exists", "A newer attempt is already in progress.")
    if s["attempt"] != c.db.scalar("SELECT MAX(attempt) FROM assessments WHERE application_id=?", (s["app_id"],)):
        raise ApiError(409, "not_latest", "Only the latest attempt can be retaken.")
    n = c.db.scalar("SELECT MAX(attempt) FROM assessments WHERE application_id=?", (s["app_id"],)) + 1
    nid = uid()
    fresh, send = bool(d.get("fresh")), bool(d.get("send"))
    app_status = c.db.scalar("SELECT status FROM applications WHERE id=?", (s["app_id"],))
    if send and not workflow.can(app_status, "assessment_sent"):
        raise ApiError(409, "invalid_stage", f"A second attempt cannot be sent while the application is '{workflow.LABEL.get(app_status, app_status)}'.")
    if fresh:
        c.db.execute("INSERT INTO assessments (id,application_id,attempt,status,created_at) VALUES (?,?,?,?,?)", (nid, s["app_id"], n, "generating", now()))
        pl.enqueue(c, "generate_assessment", {"assessment_id": nid, "auto_send": send})
        status = "generating"
    else:
        c.db.execute("INSERT INTO assessments (id,application_id,attempt,status,task,minutes,model,created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (nid, s["app_id"], n, "draft", s["task"], s["minutes"], s["model"], now()))
        status = "sent" if send and pl.send_assessment_now(c, nid) else "draft"
    audit("assessment.retake", "assessment", nid, {"previous": sid, "attempt": n, "fresh": fresh, "sent": send})
    pl.log(c, "assessment.second_attempt_offered", "application", s["app_id"],
           {"note": d.get("note") or ("new questions" if fresh else "same questions"), "attempt": n}, g.user["id"], g.user["role"], request.remote_addr)
    return jsonify({"id": nid, "status": status, "attempt": n}), 201


# ------------------------------------------------------------------ follow-up messages (recruiter -> candidate)
@bp.post("/applications/<aid>/email")
@require("recruiter")
def send_follow_up(aid):
    """A reviewer writes to the candidate about this application. The message is e-mailed when an e-mail service is set up, and
    is always shown to the candidate on their own application page, so a follow-up never depends on a paid service."""
    from .mail import queue_email
    c = ctx()
    d = body(O({"subject": S(minLength=3, maxLength=150), "body": S(minLength=10, maxLength=4000)}, ["subject", "body"]))
    a = get_application(aid)
    cand = c.db.one("SELECT full_name, email FROM candidates WHERE id=?", (a["candidate_id"],))
    rec = c.db.one("SELECT r.full_name, o.name AS org FROM recruiters r JOIN organizations o ON o.id=r.organization_id WHERE r.user_id=?", (g.user["id"],))
    text = (d["body"].rstrip() + f"\n\n{rec['full_name']}, {rec['org']}\nAbout your application for {a['job_title']}: "
            f"{c.cfg.public_url}/#/application/{aid}")
    deliverable = "@invalid.local" not in cand["email"]
    with c.db.tx():
        if deliverable:
            mid = queue_email(c, cand["email"], d["subject"], text, kind="follow_up")
        else:                              # a record created from a CV without an address: kept for the in-app view only
            mid = uid()
            c.db.execute("INSERT INTO email_outbox (id,to_email,subject,body,status,kind,error,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (mid, cand["email"], d["subject"], text, "failed", "follow_up", "No e-mail address on this record.", now()))
        c.db.execute("UPDATE email_outbox SET application_id=?, sender_id=? WHERE id=?", (aid, g.user["id"], mid))
        pl.log(c, "application.message_sent", "application", aid, {"note": d["subject"]}, g.user["id"], g.user["role"], request.remote_addr)
    m = c.mailer.describe() if hasattr(c.mailer, "describe") else {}
    return jsonify({"ok": True, "id": mid, "emailed": bool(deliverable and m.get("real_delivery")),
                    "note": "E-mailed and shown in the candidate's account." if deliverable and m.get("real_delivery") else
                            "Shown in the candidate's account. No e-mail service is set up, so nothing was e-mailed."}), 201


def application_messages(aid, for_candidate=False):
    rows = ctx().db.all("""SELECT m.subject, m.body, m.created_at, m.status, m.delivery, m.error, COALESCE(r.full_name, 'Hiring team') AS sender
                           FROM email_outbox m LEFT JOIN recruiters r ON r.user_id=m.sender_id
                           WHERE m.application_id=? AND m.kind='follow_up' ORDER BY m.created_at DESC LIMIT 50""", (aid,))
    keep = ("subject", "body", "created_at", "sender") if for_candidate else ("subject", "body", "created_at", "sender", "status", "delivery", "error")
    return [{k: r[k] for k in keep} for r in rows]


@bp.post("/applications/<aid>/review")
@require("recruiter")
def review(aid):
    c = ctx()
    d = body(O({"task_score": N(minimum=0, maximum=100, nullable=True), "note": S(maxLength=2000),
                "decision": S(enum=["shortlisted", "rejected"], nullable=True)}))
    a = get_application(aid)
    if d.get("decision") and a["status"] != "human_review":
        raise ApiError(409, "invalid_stage", "Move the application to human review before deciding.")
    if d.get("task_score") is not None and not c.db.one("SELECT 1 AS x FROM assessments WHERE application_id=? AND status='evaluated'", (aid,)):
        raise ApiError(409, "no_evaluation", "There is no evaluated assessment to adjust.")
    c.db.execute("INSERT INTO reviews (id,application_id,reviewer_id,task_score,note,decision,created_at) VALUES (?,?,?,?,?,?,?)",
                 (uid(), aid, g.user["id"], d.get("task_score"), d.get("note", ""), d.get("decision"), now()))
    audit("review.save", "application", aid, {"override": d.get("task_score"), "decision": d.get("decision")})
    if d.get("decision"):
        pl.set_status(c, aid, d["decision"], g.user, d.get("note"), request.remote_addr)
    if d.get("task_score") is not None:
        pl.recompute_match(c, aid, reason="reviewer set the assessment score")
    return jsonify({"ok": True})


@bp.get("/applications/export.csv")
@require(*REC)
def export_csv():
    job_id = request.args.get("job_id")
    if not job_id: raise ApiError(400, "job_required", "job_id is required.")
    job = get_job(job_id)
    rows = ctx().db.all("""SELECT a.id AS application_id, c.id AS candidate_id, c.full_name, c.email, c.phone, a.created_at, a.status,
        a.cv_match_score, a.match_score, a.scoring_version, v.original_name AS cv_file, a.profile_snapshot,
        (SELECT ev.overall FROM evaluations ev JOIN assessments s ON s.id=ev.assessment_id WHERE s.application_id=a.id ORDER BY s.attempt DESC LIMIT 1) AS assessment,
        (SELECT s.status || '/' || COALESCE(s.eval_status,'') FROM assessments s WHERE s.application_id=a.id ORDER BY s.attempt DESC LIMIT 1) AS assessment_state,
        (SELECT r.decision FROM reviews r WHERE r.application_id=a.id AND r.decision IS NOT NULL ORDER BY r.created_at DESC LIMIT 1) AS decision,
        (SELECT o.level || CASE WHEN o.verdict IS NOT NULL THEN ' (' || o.verdict || ')' ELSE '' END FROM originality_checks o
          WHERE o.application_id=a.id AND o.kind='cv') AS cv_similarity,
        (SELECT o.level || CASE WHEN o.verdict IS NOT NULL THEN ' (' || o.verdict || ')' ELSE '' END FROM originality_checks o
          WHERE o.application_id=a.id AND o.kind='answers') AS answer_similarity
        FROM applications a JOIN candidates c ON c.id=a.candidate_id LEFT JOIN cvs v ON v.id=a.cv_id
        WHERE a.job_id=? ORDER BY a.match_score DESC, a.id LIMIT 5000""", (job_id,))

    def safe(v):
        s = "" if v is None else str(v)
        return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s     # neutralise spreadsheet formula injection
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Application ID", "Candidate ID", "Name", "Email", "Phone", "Applied", "Stage", "Dated experience (yrs)", "CV used",
                "CV match %", "Overall match %", "Assessment /100", "Assessment state", "Decision", "Scoring version",
                "CV similarity to other applicants", "Answer similarity to other applicants"])
    for r in rows:
        yrs = (jl(r["profile_snapshot"]) or {}).get("total_experience_years")
        w.writerow([safe(x) for x in (r["application_id"], r["candidate_id"], r["full_name"], r["email"], r["phone"], r["created_at"][:10],
                                      workflow.LABEL.get(r["status"], r["status"]), yrs, r["cv_file"], r["cv_match_score"], r["match_score"],
                                      r["assessment"], r["assessment_state"], r["decision"], r["scoring_version"],
                                      r["cv_similarity"] or "not checked", r["answer_similarity"] or "not checked")])
    audit("export.csv", "job", job_id, {"rows": len(rows)})
    fname = re.sub(r"[^A-Za-z0-9]+", "-", job["title"]).strip("-").lower() or "applications"
    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={fname}-applications.csv"})


# ------------------------------------------------------------------ originality (recruiter): evidence and the reviewer's own verdict
@bp.post("/applications/<aid>/originality/<kind>/review")
@require("recruiter")
def review_originality(aid, kind):
    """A person records what a similarity finding means. 'cleared' = looked at, not a concern (the flag stops counting as open);
    'confirmed' = a real concern. Neither changes a score or a stage: the hiring decision is made separately, by the reviewer."""
    c = ctx()
    if kind not in ("cv", "answers"): raise ApiError(404, "not_found", "Not found.")
    d = body(O({"verdict": S(enum=["cleared", "confirmed", "open"]), "note": S(maxLength=1000)}, ["verdict"]))
    get_application(aid)
    row = c.db.one("SELECT id FROM originality_checks WHERE application_id=? AND kind=?", (aid, kind))
    if not row: raise ApiError(409, "not_checked", "This has not been compared yet.")
    v = None if d["verdict"] == "open" else d["verdict"]
    c.db.execute("UPDATE originality_checks SET verdict=?, verdict_note=?, verdict_by=?, verdict_at=? WHERE id=?",
                 (v, d.get("note") or None, g.user["id"] if v else None, now() if v else None, row["id"]))
    pl.log(c, "originality.reviewed", "application", aid, {"kind": kind, "verdict": d["verdict"], "note": d.get("note")}, g.user["id"], g.user["role"], request.remote_addr)
    return jsonify({"ok": True, "originality": originality.view(c, aid, my_org())})


@bp.post("/applications/<aid>/originality/recheck")
@require(*REC)
def recheck_originality(aid):
    c = ctx()
    get_application(aid)
    originality.check_cv(c, aid)
    originality.check_answers(c, aid)
    audit("originality.recheck", "application", aid)
    return jsonify({"ok": True, "originality": originality.view(c, aid, None if g.user["role"] == "admin" else my_org())})


@bp.get("/jobs/<jid>/originality")
@require(*REC)
def job_originality(jid):
    """Who among this opening's applicants shares CV text / a template, or submitted overlapping answers."""
    get_job(jid)
    return jsonify(originality.job_overview(ctx(), jid, None if g.user["role"] == "admin" else my_org()))


@bp.post("/jobs/<jid>/originality/scan")
@require(*REC)
def scan_job_originality(jid):
    """Compare every applicant of this opening again (after importing candidates, or to be sure nothing is stale)."""
    c = ctx()
    get_job(jid)
    ids = [r["id"] for r in c.db.all("SELECT id FROM applications WHERE job_id=? ORDER BY created_at LIMIT 2000", (jid,))]
    for aid in ids:
        pl.enqueue(c, "originality", {"application_id": aid, "kind": "cv"})
        pl.enqueue(c, "originality", {"application_id": aid, "kind": "answers"})
    audit("originality.scan", "job", jid, {"applications": len(ids)})
    return jsonify({"ok": True, "queued": len(ids)}), 202


# ------------------------------------------------------------------ skill test (recruiter): preview and send to everyone waiting
PREVIEW_PROFILE = {"full_name": "the candidate", "skills": [], "work_history": [], "projects": [], "education": [], "certifications": []}


@bp.post("/jobs/<jid>/skill-test/preview")
@require(*REC)
def preview_skill_test(jid):
    """The skill test this opening produces, written now by the configured engine, for the recruiter to read before anyone
    receives one. Nothing is stored or sent. A real applicant's test also draws on their own CV."""
    from . import ai as ai_mod
    c = ctx()
    job = pl.job_dict(get_job(jid))
    d = body(O({"test_questions": I(minimum=3, maximum=6)}))
    if d.get("test_questions"): job["test_questions"] = d["test_questions"]
    task = ai_mod.generate_assessment(c.ai, PREVIEW_PROFILE, job)
    engine = task.pop("engine", ai_mod.RULES)
    audit("skill_test.preview", "job", jid, {"engine": engine, "questions": len(task["questions"])})
    return jsonify({"task": task, "engine": engine,
                    "note": "Preview without a candidate. Each applicant's own test also refers to work on their CV and to the required skills their CV does not show."})


@bp.post("/jobs/<jid>/skill-test/send")
@require("recruiter")
def send_skill_tests(jid):
    """Write and send a skill test to every applicant of this opening who is waiting for one. Each test is generated for that
    applicant; applicants who already have a test (in progress or scored) are left alone."""
    c = ctx()
    get_job(jid)
    made = []
    for a in c.db.all("""SELECT a.id FROM applications a WHERE a.job_id=? AND a.status IN ('applied','cv_reviewed') AND a.profile_snapshot IS NOT NULL
                         AND NOT EXISTS (SELECT 1 FROM assessments s WHERE s.application_id=a.id AND s.status != 'failed')""", (jid,)):
        n = (c.db.scalar("SELECT MAX(attempt) FROM assessments WHERE application_id=?", (a["id"],)) or 0) + 1
        sid = uid()
        try:
            c.db.execute("INSERT INTO assessments (id,application_id,attempt,status,created_at) VALUES (?,?,?,?,?)", (sid, a["id"], n, "generating", now()))
        except Exception:
            continue                          # someone else created one in the meantime
        if c.db.scalar("SELECT status FROM applications WHERE id=?", (a["id"],)) == "applied":
            pl.set_status(c, a["id"], "cv_reviewed", g.user, "skill test requested", request.remote_addr)
        pl.enqueue(c, "generate_assessment", {"assessment_id": sid, "auto_send": True})
        made.append(a["id"])
    audit("skill_test.send_all", "job", jid, {"applications": len(made)})
    return jsonify({"ok": True, "queued": len(made)}), 202


# ------------------------------------------------------------------ comparison + overview (recruiter)
@bp.get("/jobs/<jid>/compare")
@require(*REC)
def compare_applications(jid):
    """Side-by-side view of 2-5 applications for ONE opening, built from stored results only."""
    c = ctx()
    job = get_job(jid)
    ids = [x for x in (request.args.get("ids") or "").split(",") if x]
    if not 2 <= len(ids) <= 5 or len(set(ids)) != len(ids):
        raise ApiError(400, "bad_ids", "Choose between 2 and 5 different applications to compare.")
    out = []
    for aid in ids:
        a = c.db.one("""SELECT a.id, a.status, a.match_score, a.job_id, ca.full_name, ca.email, ca.total_years FROM applications a
                        JOIN candidates ca ON ca.id=a.candidate_id WHERE a.id=? AND a.job_id=?""", (aid, jid))
        if not a: raise ApiError(404, "not_found", "Application not found for this opening.")
        m = c.db.one("SELECT breakdown, ai_analysis FROM matches WHERE application_id=?", (aid,))
        b = jl(m["breakdown"]) if m else {}
        ai_ = jl(m["ai_analysis"]) if m and m["ai_analysis"] else {}
        s = c.db.one("""SELECT ev.result, ev.overall FROM evaluations ev JOIN assessments s ON s.id=ev.assessment_id
                        WHERE s.application_id=? ORDER BY s.attempt DESC LIMIT 1""", (aid,))
        ev = jl(s["result"]) if s else None
        out.append({"id": aid, "candidate": a["full_name"], "email": a["email"], "years": (b.get("experience") or {}).get("years"), "status": a["status"],
                    "score": a["match_score"], "cv_score": b.get("cv_score"),
                    "provisional": b.get("provisional"), "components": b.get("components", {}), "skills": b.get("skills", []),
                    "similarity": (b.get("similarity") or {}).get("score"), "assessment": ev["overall"] if ev else None,
                    "criteria": ev["criteria"] if ev else None, "flags": ev["flags"] if ev else [],
                    "originality": originality.summary_levels(c, [aid]).get(aid),
                    "strengths": ai_.get("strengths", []), "gaps": ai_.get("gaps", [])})
    audit("compare.view", "job", jid, {"applications": len(ids)})
    return jsonify({"job": {"id": jid, "title": job["title"]}, "applications": out})


@bp.get("/dashboard/summary")
@require(*REC)
def dashboard_summary():
    c = ctx()
    where, args = "1=1", []
    if g.user["role"] == "recruiter":
        where, args = "j.organization_id=?", [my_org()]
    jobs = c.db.one(f"SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN j.status='open' THEN 1 ELSE 0 END),0) AS open FROM jobs j WHERE {where}", args)
    by_stage = {r["status"]: r["n"] for r in c.db.all(
        f"SELECT a.status, COUNT(*) AS n FROM applications a JOIN jobs j ON j.id=a.job_id WHERE {where} GROUP BY a.status", args)}
    total = sum(by_stage.values())
    avg = c.db.scalar(f"SELECT AVG(a.match_score) FROM applications a JOIN jobs j ON j.id=a.job_id WHERE {where} AND a.match_score IS NOT NULL", args)
    assessed = c.db.scalar(f"""SELECT COUNT(DISTINCT s.application_id) FROM assessments s JOIN applications a ON a.id=s.application_id
                               JOIN jobs j ON j.id=a.job_id WHERE {where} AND s.status='evaluated'""", args)
    top = c.db.all(f"""SELECT a.id, a.match_score, a.status, ca.full_name, j.title AS job_title FROM applications a JOIN jobs j ON j.id=a.job_id
                       JOIN candidates ca ON ca.id=a.candidate_id WHERE {where} AND a.match_score IS NOT NULL ORDER BY a.match_score DESC, a.id LIMIT 5""", args)
    failed = c.db.scalar(f"""SELECT COUNT(DISTINCT s.application_id) FROM assessments s JOIN applications a ON a.id=s.application_id
                             JOIN jobs j ON j.id=a.job_id WHERE {where} AND s.status='submitted' AND s.eval_status='failed'""", args)
    candidates = c.db.scalar(f"SELECT COUNT(DISTINCT a.candidate_id) FROM applications a JOIN jobs j ON j.id=a.job_id WHERE {where}", args)
    similar = c.db.scalar(f"""SELECT COUNT(DISTINCT o.application_id) FROM originality_checks o JOIN applications a ON a.id=o.application_id
                              JOIN jobs j ON j.id=a.job_id WHERE {where} AND o.level IN ('medium','high')
                              AND (o.verdict IS NULL OR o.verdict != 'cleared')""", args)
    # definitions (shown in the UI): awaiting review = scored and not yet decided (Scored + Human review) + scoring failed
    waiting = by_stage.get("ai_evaluated", 0) + by_stage.get("human_review", 0) + failed
    in_assessment = sum(by_stage.get(k, 0) for k in ("assessment_sent", "assessment_started", "assessment_submitted"))
    return jsonify({"jobs": {"total": jobs["total"], "open": jobs["open"]}, "applications": {"total": total, "by_stage": by_stage, "candidates": candidates,
                    "avg_match": round(avg, 1) if avg is not None else None, "assessed": assessed, "awaiting_review": waiting,
                    "scoring_failed": failed, "in_assessment": in_assessment, "similarity_flags": similar}, "top": top})


# ------------------------------------------------------------------ candidate pool (recruiter)
CSORT = {"newest": "c.created_at DESC, c.id", "name": "LOWER(c.full_name), c.id", "experience": "c.total_years DESC, c.id"}


@bp.get("/candidates")
@require(*REC)
def list_candidates():
    page, limit, off = paging()
    where, args = [], []
    if g.user["role"] == "recruiter":
        o = my_org(); where.append(org_scope_sql()); args += [o, o]
    if request.args.get("q"):
        q = "%" + request.args["q"].lower() + "%"
        where.append("(LOWER(c.full_name) LIKE ? OR LOWER(c.email) LIKE ?)"); args += [q, q]
    if request.args.get("skill"):
        where.append("LOWER(c.top_skills) LIKE ?"); args.append('%"' + request.args["skill"].lower() + '"%')
    if request.args.get("profile_status"):
        where.append("c.profile_status=?"); args.append(request.args["profile_status"])
    if request.args.get("min_years"):
        where.append("c.total_years>=?"); args.append(float(request.args["min_years"]))
    w = " AND ".join(where) or "1=1"
    order = CSORT.get(request.args.get("sort", "newest"), CSORT["newest"])
    total = ctx().db.scalar(f"SELECT COUNT(*) FROM candidates c WHERE {w}", args)
    org_apps = "AND j.organization_id=?" if g.user["role"] == "recruiter" else ""
    rows = ctx().db.all(f"""SELECT c.*, (SELECT COUNT(*) FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.candidate_id=c.id {org_apps}) AS n_apps,
                            (SELECT COUNT(*) FROM cvs v WHERE v.candidate_id=c.id AND v.identity_status='mismatch') AS n_mismatch
                            FROM candidates c WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?""",
                        ([my_org()] if org_apps else []) + args + [limit, off])
    return envelope([{**cand_out(r, full=False), "applications": r["n_apps"], "cv_warnings": r["n_mismatch"]} for r in rows], total, page, limit)


@bp.post("/candidates")
@require("recruiter")
def create_candidate():
    d = body(O({"full_name": S(minLength=2, maxLength=120), "email": S(format="email", maxLength=200), "phone": S(maxLength=40)}, ["full_name", "email"]))
    c = ctx()
    email = d["email"].lower()
    if c.db.one("SELECT 1 AS x FROM candidates WHERE email=?", (email,)):
        raise ApiError(409, "candidate_exists", "A candidate with this email already exists.")
    cid, t = uid(), now()
    c.db.execute("INSERT INTO candidates (id,managed_by_org_id,email,full_name,phone,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                 (cid, my_org(), email, d["full_name"], d.get("phone"), t, t))
    audit("candidate.create", "candidate", cid, {"by_recruiter": True})
    return jsonify(cand_out(c.db.one("SELECT * FROM candidates WHERE id=?", (cid,)))), 201


@bp.get("/candidates/<cid>")
@require(*REC)
def candidate_detail(cid):
    c = ctx()
    cand = get_candidate(cid)
    q = """SELECT a.id, a.status, a.match_score, a.cv_match_score, a.cv_id, a.created_at, j.title, v.original_name AS cv_name
           FROM applications a JOIN jobs j ON j.id=a.job_id LEFT JOIN cvs v ON v.id=a.cv_id WHERE a.candidate_id=?"""
    args = [cid]
    if g.user["role"] == "recruiter":
        q += " AND j.organization_id=?"; args.append(my_org())
    apps = c.db.all(q + " ORDER BY a.created_at DESC", args)
    for a in apps: a["status_label"] = workflow.LABEL[a["status"]]
    cvs = []
    for x in c.db.all("SELECT * FROM cvs WHERE candidate_id=? ORDER BY created_at DESC LIMIT 20", (cid,)):
        try:
            get_cv(x["id"])         # only the CVs this viewer may open (e.g. not a CV used for another organisation)
        except ApiError:
            continue
        cvs.append({**cv_out(x, cand["active_cv_id"]), "used_for": [a["title"] for a in apps if a["cv_id"] == x["id"]]})
    audit("candidate.view", "candidate", cid)
    return jsonify({**cand_out(cand), "cvs": cvs, "applications": apps, "managed": bool(cand["managed_by_org_id"]), "has_account": bool(cand["user_id"])})


# ------------------------------------------------------------------ assessments (candidate side)
def task_for_candidate(task):
    return {"title": task["title"], "scenario": task["scenario"],
            "questions": [{"id": q["id"], "prompt": q["prompt"], "max_points": q["max_points"]} for q in task["questions"]]}   # rubric stays private


@bp.get("/assessments/<sid>")
@require()
def view_assessment(sid):
    c = ctx()
    s = get_assessment(sid)
    r = c.db.one("SELECT answers FROM assessment_responses WHERE assessment_id=?", (sid,))
    base = {"id": sid, "application_id": s["app_id"], "status": s["status"], "minutes": s["minutes"], "attempt": s["attempt"], "job_title": s["job_title"],
            "started_at": s["started_at"], "due_at": s["due_at"]}
    if g.user["role"] == "candidate":
        started = s["status"] in ("started", "submitted", "evaluated")
        return jsonify({**base, "task": task_for_candidate(jl(s["task"])) if started else {"title": jl(s["task"])["title"]},
                        "answers": jl(r["answers"]) if r else {}})
    return jsonify({**base, "task": jl(s["task"]), "answers": jl(r["answers"]) if r else None})


ANSWERS = {"type": "object", "additionalProperties": True}


def _answers(s, raw):
    ids = {q["id"] for q in jl(s["task"])["questions"]}
    if not isinstance(raw, dict) or not set(raw) <= ids:
        raise ApiError(422, "validation_failed", "Answers must be keyed by question id.")
    out = {}
    for k, v in raw.items():
        if not isinstance(v, str) or len(v) > 8000:
            raise ApiError(422, "validation_failed", f"Answer {k} must be text up to 8000 characters.")
        out[k] = v
    return out


def _own_open_assessment(sid, statuses):
    s = get_assessment(sid)
    if s["status"] not in statuses: raise ApiError(409, "invalid_state", f"This assessment is {s['status']}.")
    return s


@bp.post("/assessments/<sid>/start")
@require("candidate")
def start_assessment(sid):
    c = ctx()
    s = _own_open_assessment(sid, ("sent",))
    if s["due_at"] and s["due_at"] < now(): raise ApiError(409, "expired", "This assessment has expired. Ask the recruiter for a new link.")
    t = now()
    c.db.execute("UPDATE assessments SET status='started', started_at=? WHERE id=?", (t, sid))
    pl.set_status(c, s["app_id"], "assessment_started", g.user, None, request.remote_addr)
    return jsonify({"ok": True, "started_at": t, "deadline": (datetime.fromisoformat(t) + timedelta(minutes=s["minutes"])).isoformat()})


@bp.put("/assessments/<sid>/draft")
@require("candidate")
def save_draft(sid):
    c = ctx()
    s = get_assessment(sid)
    d = body(O({"answers": ANSWERS}, ["answers"]))
    ans = _answers(s, d["answers"])
    t = now()
    with c.db.tx():
        # re-read inside the transaction: an autosave that arrives after Submit must never overwrite the submitted answers
        if c.db.scalar("SELECT status FROM assessments WHERE id=?", (sid,)) != "started":
            raise ApiError(409, "invalid_state", "This assessment has already been submitted; the draft was not saved.")
        c.db.execute("""INSERT INTO assessment_responses (id,assessment_id,answers,saved_at,task_hash) VALUES (?,?,?,?,?)
                        ON CONFLICT(assessment_id) DO UPDATE SET answers=excluded.answers, saved_at=excluded.saved_at, task_hash=excluded.task_hash
                        WHERE assessment_responses.submitted_at IS NULL""", (uid(), sid, jd(ans), t, pl.task_hash(jl(s["task"]))))
    return jsonify({"ok": True, "saved_at": t, "answers_saved": sum(1 for v in ans.values() if v.strip())})


@bp.post("/assessments/<sid>/activity")
@require("candidate")
def test_activity(sid):
    """The test page reports how the test is being taken (see integrity.py): counts and durations, never text. The candidate is told
    about this before starting and sees a notice on screen whenever something is noted. Accepted only while the test is open."""
    c = ctx()
    s = get_assessment(sid)
    d = body(O({"events": A(O({"kind": S(enum=list(integrity.KINDS)), "question_id": S(maxLength=20, nullable=True),
                                "seconds": N(minimum=0, maximum=86400), "chars": I(minimum=0, maximum=200000)}, ["kind"]), maxItems=60)}, ["events"]))
    if s["status"] != "started":
        return jsonify({"ok": True, "recorded": 0})
    ids = {q["id"] for q in jl(s["task"])["questions"]}
    events = [e for e in d["events"] if not e.get("question_id") or e["question_id"] in ids]
    return jsonify({"ok": True, "recorded": integrity.record(c, sid, events)})


@bp.post("/assessments/<sid>/submit")
@require("candidate")
def submit_assessment(sid):
    c = ctx()
    s = get_assessment(sid)
    d = body(O({"answers": ANSWERS}, ["answers"]))
    ans = _answers(s, d["answers"])
    if s["status"] in ("submitted", "evaluated"):     # double click / retried request: same answers -> same result, never a second record
        prev = c.db.one("SELECT answers FROM assessment_responses WHERE assessment_id=?", (sid,))
        if prev and jl(prev["answers"]) == ans:
            return jsonify({"ok": True, "already_submitted": True, "late": False})
        raise ApiError(409, "already_submitted", "This assessment was already submitted. The first submission is the one that counts.")
    if s["status"] != "started": raise ApiError(409, "invalid_state", f"This assessment is {s['status']}.")
    if not any(v.strip() for v in ans.values()): raise ApiError(422, "empty_answers", "Write at least one answer before submitting.")
    grace = datetime.fromisoformat(s["started_at"]) + timedelta(minutes=s["minutes"] + 5)
    late = datetime.now(timezone.utc) > grace
    t = now()
    with c.db.tx():
        # the status flip is conditional, so two concurrent submits cannot both succeed
        if c.db.execute("UPDATE assessments SET status='submitted', submitted_at=?, eval_status='queued' WHERE id=? AND status='started'", (t, sid)).rowcount != 1:
            raise ApiError(409, "already_submitted", "This assessment was already submitted.")
        c.db.execute("""INSERT INTO assessment_responses (id,assessment_id,answers,saved_at,submitted_at,task_hash) VALUES (?,?,?,?,?,?)
                        ON CONFLICT(assessment_id) DO UPDATE SET answers=excluded.answers, saved_at=excluded.saved_at, submitted_at=excluded.submitted_at,
                        task_hash=excluded.task_hash""", (uid(), sid, jd(ans), t, t, pl.task_hash(jl(s["task"]))))
        pl.set_status(c, s["app_id"], "assessment_submitted", g.user, "late" if late else None, request.remote_addr)
        pl.log(c, "assessment.submitted", "assessment", sid, {"application_id": s["app_id"], "answered": sum(1 for v in ans.values() if v.strip()),
                                                               "questions": len(jl(s["task"])["questions"]), "late": late}, g.user["id"], "candidate")
        # queued in the same transaction: a crash cannot leave a submission that is never scored
        pl.enqueue(c, "evaluate_assessment", {"assessment_id": sid})
        cand = c.db.one("SELECT full_name, email FROM candidates WHERE id=?", (s["candidate_id"],))
        from .mail import queue_email, render
        queue_email(c, cand["email"], *render("assessment_submitted", name=cand["full_name"], job=s["job_title"], when=t[:16].replace("T", " ") + " UTC",
                                               url=f"{c.cfg.public_url}/#/application/{s['app_id']}"), kind="assessment_submitted")
    return jsonify({"ok": True, "late": late})
