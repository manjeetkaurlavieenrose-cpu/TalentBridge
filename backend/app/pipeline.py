"""Background processing: a DB-backed task queue (SKIP LOCKED on PostgreSQL) plus the handlers.
Run a worker with:  python -m app.worker"""
import time, traceback
from datetime import datetime, timezone, timedelta
from .db import now, uid, jd, jl
from . import ai as ai_mod
from .ai import AIError
from .extract import extract_document, ExtractionError
from .files import FileRejected
from .matching import compute_match
from .profile import normalise, summary_fields
from . import workflow, identity


from .mail import MailError, get_mailer      # noqa: E402  (kept importable from here for older code)


# ------------------------------------------------------------------ shared helpers
def log(c, action, etype, eid, detail=None, actor_id=None, actor_role="system", ip=None):
    c.db.execute("INSERT INTO activity_logs (id,actor_id,actor_role,action,entity_type,entity_id,detail,ip,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (uid(), actor_id, actor_role, action, etype, eid, jd(detail) if detail is not None else None, ip, now()))


def set_status(c, app_id, to, actor=None, note=None, ip=None):
    a = c.db.one("SELECT status FROM applications WHERE id=?", (app_id,))
    if not workflow.can(a["status"], to):
        raise ValueError(f"Cannot move application from {a['status']} to {to}.")
    c.db.execute("UPDATE applications SET status=?, updated_at=? WHERE id=?", (to, now(), app_id))
    log(c, "application.transition", "application", app_id, {"from": a["status"], "to": to, "note": note},
        actor["id"] if actor else None, actor["role"] if actor else "system", ip)


def effective_assessment_score(c, app_id):
    r = c.db.one("SELECT task_score FROM reviews WHERE application_id=? AND task_score IS NOT NULL ORDER BY created_at DESC, id LIMIT 1", (app_id,))
    if r: return r["task_score"]
    e = c.db.one("""SELECT ev.overall FROM evaluations ev JOIN assessments s ON s.id=ev.assessment_id
                    WHERE s.application_id=? ORDER BY s.attempt DESC LIMIT 1""", (app_id,))
    return e["overall"] if e else None


def job_dict(row):
    return {**row, "required_skills": jl(row["required_skills"], []), "preferred_skills": jl(row["preferred_skills"], []),
            "custom_requirements": jl(row.get("custom_requirements"), [])}


def application_profile(c, a):
    """The profile an application is judged on: the snapshot taken when it was submitted (later profile edits or CV uploads
    do not silently change an application that has already been made)."""
    if a.get("profile_snapshot"):
        return jl(a["profile_snapshot"])
    cand = c.db.one("SELECT profile FROM candidates WHERE id=?", (a["candidate_id"],))
    return jl(cand["profile"]) if cand and cand["profile"] else None


def match_for(c, profile, job, assessment_score=None, cv_text=None):
    """The ONE place a match is computed: preview, stored application match, recruiter view and export all come from here."""
    from .local_ai import check_requirement
    reqs = [check_requirement(r, profile) for r in job.get("custom_requirements") or []]
    return compute_match(profile, job, assessment_score, reqs or None, cv_text=cv_text, encoder=getattr(c, "encoder", None))


def recompute_match(c, app_id, ai_analysis=None, reason=None):
    a = c.db.one("SELECT * FROM applications WHERE id=?", (app_id,))
    profile = application_profile(c, a) if a else None
    if not profile:
        return None
    job = job_dict(c.db.one("SELECT * FROM jobs WHERE id=?", (a["job_id"],)))
    old = c.db.one("SELECT * FROM matches WHERE application_id=?", (app_id,))
    analysis = ai_analysis if ai_analysis is not None else (jl(old["ai_analysis"]) if old else None)
    cv_row = c.db.one("SELECT extracted_text FROM cvs WHERE id=?", (a["cv_id"],)) if a["cv_id"] else None
    m = match_for(c, profile, job, effective_assessment_score(c, app_id), cv_row["extracted_text"] if cv_row else None)
    t = now()
    with c.db.tx():
        if old and (old["score"] != m["score"] or (jl(old["breakdown"]) or {}).get("inputs") != m["inputs"]):
            c.db.execute("INSERT INTO match_history (id,application_id,score,breakdown,computed_at,replaced_at,reason) VALUES (?,?,?,?,?,?,?)",
                         (uid(), app_id, old["score"], old["breakdown"], old["computed_at"], t, reason))
        c.db.execute("""INSERT INTO matches (id,application_id,score,provisional,breakdown,ai_analysis,computed_at) VALUES (?,?,?,?,?,?,?)
                        ON CONFLICT(application_id) DO UPDATE SET score=excluded.score, provisional=excluded.provisional,
                        breakdown=excluded.breakdown, ai_analysis=excluded.ai_analysis, computed_at=excluded.computed_at""",
                     (uid(), app_id, m["score"], int(m["provisional"]), jd(m), jd(analysis) if analysis else None, t))
        c.db.execute("UPDATE applications SET match_score=?, cv_match_score=?, scoring_version=?, updated_at=? WHERE id=?",
                     (m["score"], m["cv_score"], m["scoring_version"], t, app_id))
    return m


# ------------------------------------------------------------------ CV ownership
def apply_cv_to_candidate(c, cv_id):
    """Make a processed CV the candidate's active CV: its extraction becomes the (draft) profile the candidate reviews.
    Contact details from the CV only fill empty fields; they never overwrite the record's own name, email or phone."""
    cv = c.db.one("SELECT * FROM cvs WHERE id=?", (cv_id,))
    profile = jl(cv["extraction"])
    yrs, top = summary_fields(profile)
    c.db.execute("""UPDATE candidates SET profile=?, profile_status='draft', total_years=?, top_skills=?, active_cv_id=?,
                    phone=COALESCE(NULLIF(phone,''), ?), updated_at=? WHERE id=?""",
                 (jd(profile), yrs, jd(top), cv_id, profile.get("phone"), now(), cv["candidate_id"]))


def reassign_cv(c, cv_id, target_id, actor=None, ip=None):
    """Move a CV, and every application made with it (with its assessments, answers and results), to the record of the
    person the CV belongs to. Used by recruiters/admins and by scripts/repair_identity.py. Returns moved application ids."""
    cv = c.db.one("SELECT * FROM cvs WHERE id=?", (cv_id,))
    src = cv["candidate_id"]
    apps = [r["id"] for r in c.db.all("SELECT id FROM applications WHERE cv_id=?", (cv_id,))]
    for aid in apps:
        if c.db.one("SELECT 1 AS x FROM applications a JOIN applications b ON b.job_id=a.job_id WHERE a.id=? AND b.candidate_id=?", (aid, target_id)):
            raise ValueError("The target candidate already has an application for the same opening.")
    who = (actor or {}).get("id"), (actor or {}).get("role", "system")
    with c.db.tx():
        c.db.execute("UPDATE cvs SET candidate_id=?, identity_status='reassigned', updated_at=? WHERE id=?", (target_id, now(), cv_id))
        for aid in apps:
            c.db.execute("UPDATE applications SET candidate_id=?, updated_at=? WHERE id=?", (target_id, now(), aid))
            log(c, "application.reassigned", "application", aid, {"from_candidate": src, "to_candidate": target_id, "cv_id": cv_id}, who[0], who[1], ip)
        if c.db.scalar("SELECT active_cv_id FROM candidates WHERE id=?", (src,)) == cv_id:
            c.db.execute("UPDATE candidates SET active_cv_id=NULL WHERE id=?", (src,))
        log(c, "cv.reassigned", "cv", cv_id, {"from_candidate": src, "to_candidate": target_id, "applications": len(apps)}, who[0], who[1], ip)
    tgt = c.db.one("SELECT profile FROM candidates WHERE id=?", (target_id,))
    if not tgt["profile"] and cv["stage"] == "ready" and cv["extraction"]:
        apply_cv_to_candidate(c, cv_id)
    return apps


# ------------------------------------------------------------------ queue
def enqueue(c, kind, payload, delay=0):
    t = datetime.now(timezone.utc)
    c.db.execute("INSERT INTO task_queue (id,kind,payload,status,max_attempts,run_after,created_at) VALUES (?,?,?,?,?,?,?)",
                 (uid(), kind, jd(payload), "queued", c.cfg.task_max_attempts,
                  (t + timedelta(seconds=delay)).isoformat(timespec="microseconds"), t.isoformat(timespec="microseconds")))


def claim(c, ignore_backoff=False):
    t = now()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="microseconds")
    c.db.execute("UPDATE task_queue SET status='queued' WHERE status='running' AND locked_at<?", (stale,))
    cond = "" if ignore_backoff else "AND run_after<=?"
    args = [t] + ([] if ignore_backoff else [t])
    return c.db.one(f"""UPDATE task_queue SET status='running', locked_at=?, attempts=attempts+1
        WHERE id=(SELECT id FROM task_queue WHERE status='queued' {cond} ORDER BY created_at LIMIT 1 {{SKIP}}) RETURNING *""", args)


def run_one(c, ignore_backoff=False):
    t = claim(c, ignore_backoff)
    if not t:
        return False
    payload = jl(t["payload"], {})
    try:
        HANDLERS[t["kind"]](c, payload)
        c.db.execute("UPDATE task_queue SET status='done', last_error=NULL WHERE id=?", (t["id"],))
    except Exception as e:
        if t["kind"] == "evaluate_assessment":   # visible as "retrying" until it succeeds or finally fails
            c.db.execute("UPDATE assessments SET eval_status='retrying', eval_error=? WHERE id=? AND status='submitted'",
                         ((getattr(e, "message", None) or str(e))[:300], payload.get("assessment_id")))
        retryable = getattr(e, "retryable", True) and not isinstance(e, (ExtractionError, FileRejected))
        final = (not retryable) or t["attempts"] >= t["max_attempts"]
        msg = getattr(e, "message", None) or str(e)
        code = getattr(e, "code", type(e).__name__)
        if final:
            c.db.execute("UPDATE task_queue SET status='failed', last_error=? WHERE id=?", (f"{code}: {msg}"[:500], t["id"]))
            try: FAIL_HOOKS.get(t["kind"], lambda *a: None)(c, payload, code, msg)
            except Exception: traceback.print_exc()
        else:
            delay = 30 * 2 ** t["attempts"]
            c.db.execute("UPDATE task_queue SET status='queued', last_error=?, run_after=? WHERE id=?",
                         (f"{code}: {msg}"[:500], (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="microseconds"), t["id"]))
        if not isinstance(e, (AIError, ExtractionError, MailError, FileRejected, EvaluationInputError)):
            traceback.print_exc()
    return True


def recover_interrupted(c):
    """Single-process (laptop) mode: tasks left 'running' by a stopped app can never finish, so queue them again at start-up."""
    n = c.db.execute("UPDATE task_queue SET status='queued', run_after=? WHERE status='running'", (now(),)).rowcount
    c.db.execute("UPDATE assessments SET eval_status='queued' WHERE status='submitted' AND eval_status IN ('scoring','retrying')")
    return n


def backfill(c):
    """Fill the columns added by migration 3 for rows created by older versions. Idempotent; never changes a stored score."""
    with c.db.tx():
        for cand in c.db.all("SELECT id FROM candidates WHERE active_cv_id IS NULL AND profile IS NOT NULL"):
            cv = c.db.one("SELECT id FROM cvs WHERE candidate_id=? AND stage='ready' ORDER BY created_at DESC LIMIT 1", (cand["id"],))
            if cv:
                c.db.execute("UPDATE candidates SET active_cv_id=? WHERE id=?", (cv["id"], cand["id"]))
        for cv in c.db.all("""SELECT v.id, v.extraction, ca.full_name, ca.email FROM cvs v JOIN candidates ca ON ca.id=v.candidate_id
                              WHERE v.identity_status IS NULL AND v.extraction IS NOT NULL"""):
            st, det = identity.check(jl(cv["extraction"]), cv["full_name"], cv["email"])
            c.db.execute("UPDATE cvs SET identity_status=?, identity_detail=? WHERE id=?", (st, jd(det), cv["id"]))
        for a in c.db.all("""SELECT a.id, a.cv_id, ca.profile, ca.active_cv_id, v.extraction FROM applications a JOIN candidates ca ON ca.id=a.candidate_id
                             LEFT JOIN cvs v ON v.id=a.cv_id WHERE a.profile_snapshot IS NULL"""):
            # the candidate's confirmed profile if the application was made with the CV it came from, otherwise that CV's own extraction
            snap = a["profile"] if a["cv_id"] and a["cv_id"] == a["active_cv_id"] else (a["extraction"] or a["profile"])
            if snap:
                c.db.execute("UPDATE applications SET profile_snapshot=? WHERE id=?", (snap, a["id"]))
        c.db.execute("UPDATE assessments SET eval_status='scored' WHERE status='evaluated' AND eval_status IS NULL")
        c.db.execute("UPDATE assessments SET eval_status='queued' WHERE status='submitted' AND eval_status IS NULL")
    # applications made before originality checks existed are compared once (queued: start-up is never slowed down)
    for a in c.db.all("""SELECT a.id, (SELECT 1 FROM assessments s JOIN assessment_responses r ON r.assessment_id=s.id
                                       WHERE s.application_id=a.id AND r.submitted_at IS NOT NULL LIMIT 1) AS answered
                         FROM applications a WHERE NOT EXISTS (SELECT 1 FROM originality_checks o WHERE o.application_id=a.id)
                         AND NOT EXISTS (SELECT 1 FROM task_queue t WHERE t.kind='originality' AND t.status IN ('queued','running')
                                         AND t.payload LIKE '%' || a.id || '%')"""):
        enqueue(c, "originality", {"application_id": a["id"], "kind": "cv"})
        if a["answered"]:
            enqueue(c, "originality", {"application_id": a["id"], "kind": "answers"})
    # results from an older scoring method are recalculated so every number on screen matches the documented method;
    # the previous result is kept in match_history with the reason
    from .matching import SCORING_VERSION
    for a in c.db.all("SELECT id FROM applications WHERE (scoring_version IS NULL OR scoring_version != ?) AND profile_snapshot IS NOT NULL", (SCORING_VERSION,)):
        recompute_match(c, a["id"], reason=f"scoring method updated to {SCORING_VERSION}")


def run_pending(c, limit=1000, ignore_backoff=True):
    n = 0
    while n < limit and run_one(c, ignore_backoff):
        n += 1
    return n


# ------------------------------------------------------------------ handlers
def _cv_stage(c, cv_id, stage, **kw):
    c.db.execute("UPDATE cvs SET stage=?, error_code=?, error_message=?, updated_at=? WHERE id=?",
                 (stage, kw.get("code"), kw.get("message"), now(), cv_id))


def h_process_cv(c, p):
    cv = c.db.one("SELECT * FROM cvs WHERE id=?", (p["cv_id"],))
    if not cv:
        return
    _cv_stage(c, cv["id"], "extracting")
    kind = "pdf" if cv["mime"] == "application/pdf" else "docx"
    text, method = extract_document(c.storage.get(cv["storage_key"]), kind, c.cfg)
    c.db.execute("UPDATE cvs SET extracted_text=? WHERE id=?", (text, cv["id"]))
    _cv_stage(c, cv["id"], "analysing")
    cand_row = c.db.one("SELECT full_name, email FROM candidates WHERE id=?", (cv["candidate_id"],))
    # no fallback name: a CV without a readable name must not silently take the account holder's name
    profile = normalise(ai_mod.extract_profile(c.ai, text, None))
    if method.startswith("ocr:"):
        profile["text_source"] = method
        profile["gaps"] = ["This CV is a scanned image and was read with OCR: check names, dates and skills before confirming"] + \
            [g for g in profile.get("gaps", [])][:7]
    status, detail = identity.check(profile, cand_row["full_name"], cand_row["email"])
    c.db.execute("UPDATE cvs SET extraction=?, identity_status=?, identity_detail=? WHERE id=?", (jd(profile), status, jd(detail), cv["id"]))
    if identity.usable(status):
        apply_cv_to_candidate(c, cv["id"])
    _cv_stage(c, cv["id"], "ready")
    # applications keep the profile they were made with; a new CV only affects future applications
    log(c, "cv.processed", "cv", cv["id"], {"confidence": profile.get("confidence"), "identity": status, "text": method,
                                          "extracted_by": profile.get("extracted_by")})


def f_process_cv(c, p, code, msg):
    _cv_stage(c, p["cv_id"], "failed", code=code, message=msg)
    log(c, "cv.failed", "cv", p["cv_id"], {"code": code})


def h_analyse_application(c, p):
    a = c.db.one("SELECT * FROM applications WHERE id=?", (p["application_id"],))
    if not a:
        return
    m = recompute_match(c, a["id"])           # deterministic part first, so the recruiter sees something immediately
    if m is None:
        raise AIError("no_profile", "Candidate has no profile yet.", retryable=False)
    job = job_dict(c.db.one("SELECT * FROM jobs WHERE id=?", (a["job_id"],)))
    analysis = ai_mod.analyse_application(c.ai, application_profile(c, a), job)
    recompute_match(c, a["id"], analysis)
    if c.db.scalar("SELECT status FROM applications WHERE id=?", (a["id"],)) == "applied":
        set_status(c, a["id"], "cv_reviewed")
    start_auto_assessment(c, a["id"])


def start_auto_assessment(c, app_id):
    """If the opening allows it, write the candidate's assessment straight away (it is sent to them when generated).
    Idempotent: does nothing if an assessment already exists, so retries and refreshes cannot create duplicates."""
    a = c.db.one("SELECT a.id, a.status, j.auto_assessment FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.id=?", (app_id,))
    if not a or not a["auto_assessment"] or a["status"] != "cv_reviewed":
        return None
    if c.db.one("SELECT id FROM assessments WHERE application_id=?", (app_id,)):
        return None
    sid = uid()
    try:
        c.db.execute("INSERT INTO assessments (id,application_id,attempt,status,created_at) VALUES (?,?,?,?,?)", (sid, app_id, 1, "generating", now()))
    except Exception:       # UNIQUE(application_id, attempt): another worker got there first
        return None
    enqueue(c, "generate_assessment", {"assessment_id": sid, "auto_send": True})
    log(c, "assessment.auto_created", "assessment", sid, {"application_id": app_id})
    return sid


def h_generate_assessment(c, p):
    s = c.db.one("SELECT * FROM assessments WHERE id=?", (p["assessment_id"],))
    if not s or s["status"] != "generating":
        return
    a = c.db.one("SELECT * FROM applications WHERE id=?", (s["application_id"],))
    job = job_dict(c.db.one("SELECT * FROM jobs WHERE id=?", (a["job_id"],)))
    task = ai_mod.generate_assessment(c.ai, application_profile(c, a), job)
    engine = task.pop("engine", ai_mod.RULES)
    c.db.execute("UPDATE assessments SET task=?, minutes=?, model=?, status='draft' WHERE id=?",
                 (jd(task), task["minutes"], engine, s["id"]))
    log(c, "assessment.generated", "assessment", s["id"], {"questions": len(task["questions"]), "engine": engine})
    if p.get("auto_send"):
        send_assessment_now(c, s["id"])


def send_assessment_now(c, sid):
    """Mark a generated draft as sent (candidate sees it in the app). Used by auto-assessment; no e-mail is needed."""
    from datetime import datetime, timezone, timedelta
    s = c.db.one("SELECT * FROM assessments WHERE id=?", (sid,))
    a = c.db.one("SELECT * FROM applications WHERE id=?", (s["application_id"],))
    if s["status"] != "draft" or not workflow.can(a["status"], "assessment_sent"):
        return False
    due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="microseconds")
    from .mail import queue_email, render
    cand = c.db.one("SELECT full_name, email FROM candidates WHERE id=?", (a["candidate_id"],))
    job = c.db.scalar("SELECT title FROM jobs WHERE id=?", (a["job_id"],))
    with c.db.tx():
        c.db.execute("UPDATE assessments SET status='sent', sent_at=?, due_at=? WHERE id=?", (now(), due, sid))
        set_status(c, a["id"], "assessment_sent", None, "sent automatically")
        queue_email(c, cand["email"], *render("assessment_ready", name=cand["full_name"], job=job, minutes=s["minutes"],
                                               url=f"{c.cfg.public_url}/#/assessment/{sid}"), kind="assessment_ready")
    return True


def f_generate_assessment(c, p, code, msg):
    c.db.execute("UPDATE assessments SET status='failed' WHERE id=?", (p["assessment_id"],))
    log(c, "assessment.generation_failed", "assessment", p["assessment_id"], {"code": code})


def task_hash(task):
    """Fingerprint of the exact question set; stored with the answers so they can never drift onto other questions."""
    from .matching import fingerprint
    return fingerprint([{"id": q["id"], "prompt": q["prompt"]} for q in (task or {}).get("questions", [])])


class EvaluationInputError(Exception):
    """The persisted submission cannot be scored (missing or bound to other questions). Not retryable: a person must look."""
    def __init__(self, code, message):
        self.code, self.message, self.retryable = code, message, False
        super().__init__(message)


def h_evaluate_assessment(c, p):
    s = c.db.one("SELECT * FROM assessments WHERE id=?", (p["assessment_id"],))
    if not s or s["status"] != "submitted":
        return
    if c.db.one("SELECT 1 AS x FROM evaluations WHERE assessment_id=?", (s["id"],)):
        return                                   # duplicate task (retry, double enqueue): the first result stands
    c.db.execute("UPDATE assessments SET eval_status='scoring', eval_error=NULL WHERE id=?", (s["id"],))
    # score exactly what was persisted at submission, never an in-memory or newer draft copy
    r = c.db.one("SELECT answers, task_hash, submitted_at FROM assessment_responses WHERE assessment_id=?", (s["id"],))
    task = jl(s["task"])
    if not r or not r["submitted_at"]:
        raise EvaluationInputError("no_submission", "No submitted answers were found for this assessment.")
    if r["task_hash"] and r["task_hash"] != task_hash(task):
        raise EvaluationInputError("question_mismatch", "The stored answers belong to a different version of the questions.")
    answers = jl(r["answers"], {})
    a = c.db.one("SELECT * FROM applications WHERE id=?", (s["application_id"],))
    job = job_dict(c.db.one("SELECT * FROM jobs WHERE id=?", (a["job_id"],)))
    res = ai_mod.evaluate(c.ai, task, answers, application_profile(c, a), job)
    with c.db.tx():
        c.db.execute("INSERT INTO evaluations (id,assessment_id,result,overall,confidence,needs_attention,model,prompt_version,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (uid(), s["id"], jd(res), res["overall"], res["confidence"], int(res["needs_attention"]), res.get("engine") or ai_mod.RULES, ai_mod.PROMPT_VERSION, now()))
        c.db.execute("UPDATE assessments SET status='evaluated', eval_status='scored', eval_error=NULL WHERE id=?", (s["id"],))
        if workflow.can(c.db.scalar("SELECT status FROM applications WHERE id=?", (a["id"],)), "ai_evaluated"):
            set_status(c, a["id"], "ai_evaluated")
        log(c, "assessment.scored", "assessment", s["id"], {"application_id": a["id"], "overall": res["overall"],
                                                            "engine": res.get("engine"), "flags": res.get("flags", [])})
    recompute_match(c, a["id"], reason="assessment scored")
    enqueue(c, "originality", {"application_id": a["id"], "kind": "answers"})


def f_evaluate_assessment(c, p, code, msg):
    """Scoring failed for good: the submission stays exactly as it was; the assessment is marked for a person to look at.
    It is never turned into a score of 0."""
    c.db.execute("UPDATE assessments SET eval_status='failed', eval_error=? WHERE id=? AND status='submitted'", (f"{code}: {msg}"[:300], p["assessment_id"]))
    app_id = c.db.scalar("SELECT application_id FROM assessments WHERE id=?", (p["assessment_id"],))
    log(c, "assessment.evaluation_failed", "assessment", p["assessment_id"], {"code": code, "message": msg, "application_id": app_id})
    if app_id:
        enqueue(c, "originality", {"application_id": app_id, "kind": "answers"})


def h_originality(c, p):
    """Compare a CV or a set of answers with other candidates' submissions. Evidence for the reviewer only: it runs after
    (and apart from) matching and scoring, so it can never change a score or hold up an application."""
    from . import originality
    (originality.check_cv if p.get("kind") == "cv" else originality.check_answers)(c, p["application_id"])


def h_send_email(c, p):
    m = c.db.one("SELECT * FROM email_outbox WHERE id=?", (p["outbox_id"],))
    if not m or m["status"] == "sent":
        return
    delivery = c.mailer.send(m["to_email"], m["subject"], m["body"]) or "sent"
    if str(delivery).startswith("held:"):       # not on the allow-list: kept in the file outbox, not delivered
        c.db.execute("UPDATE email_outbox SET status='failed', delivery=?, error=? WHERE id=?",
                     (delivery[:200], "Held, not sent: recipient is not on EMAIL_ALLOWED_RECIPIENTS.", m["id"]))
        return
    c.db.execute("UPDATE email_outbox SET status='sent', sent_at=?, delivery=?, error=NULL WHERE id=?", (now(), str(delivery)[:200], m["id"]))


def f_send_email(c, p, code, msg):
    c.db.execute("UPDATE email_outbox SET status='failed', error=? WHERE id=?", (msg[:300], p["outbox_id"]))


HANDLERS = {"process_cv": h_process_cv, "analyse_application": h_analyse_application, "generate_assessment": h_generate_assessment,
            "evaluate_assessment": h_evaluate_assessment, "send_email": h_send_email, "originality": h_originality}
FAIL_HOOKS = {"process_cv": f_process_cv, "generate_assessment": f_generate_assessment,
              "evaluate_assessment": f_evaluate_assessment, "send_email": f_send_email}


def worker_loop(c, poll=2.0):
    last_purge = 0.0
    while True:
        if time.time() - last_purge > 3600:  # keep the shared rate-limit table small
            if hasattr(c.limiter, "purge"):
                c.limiter.purge()
            last_purge = time.time()
        if not run_one(c):
            time.sleep(poll)
