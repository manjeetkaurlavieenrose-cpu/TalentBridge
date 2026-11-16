#!/usr/bin/env python3
"""Find and fix CVs that sit on the wrong person's record (one account uploading other people's CVs).

    python3 scripts/repair_identity.py              dry run: prints what it would do, changes nothing
    python3 scripts/repair_identity.py --apply      backs up data/ first, then applies the plan

What it does, only where the owner can be established reliably from the CV itself (its name AND/OR email):
  1. Each CV flagged "appears to belong to someone else" is moved to that person's record: an existing record with the
     CV's email, otherwise a new recruiter-managed record (name/email/phone from the CV). Applications made WITH that CV
     move with it, including their assessments, answers and results, so they show the right person.
  2. The record the CVs were wrongly attached to gets its profile back from its own CV (status: draft, to be re-confirmed).
  3. Applications whose stored profile is exactly the machine extraction (nobody edited it) are re-read with the current
     parser; previous scores are kept in match_history.
Anything it cannot resolve is listed as UNRESOLVED and left untouched. Stop the app before running with --apply.
"""
import argparse, json, os, shutil, sqlite3, sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

SERVER_OWNED = ("confidence", "total_experience_years")


def same_machine_profile(a, b):
    strip = lambda p: {k: v for k, v in (p or {}).items() if k not in SERVER_OWNED}
    return strip(a) == strip(b)


def backup(data_dir):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(ROOT, "backups", f"before-repair-{ts}")
    os.makedirs(dest, exist_ok=True)
    src = sqlite3.connect(os.path.join(data_dir, "talentbridge.db"))
    dst = sqlite3.connect(os.path.join(dest, "talentbridge.db"))
    src.backup(dst); dst.close(); src.close()
    if os.path.isdir(os.path.join(data_dir, "uploads")):
        shutil.copytree(os.path.join(data_dir, "uploads"), os.path.join(dest, "uploads"))
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "data"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--org", help="organisation name for records of CVs not used in any application (default: the only organisation, if there is one)")
    args = ap.parse_args()
    data = os.path.abspath(args.data_dir)
    if not os.path.exists(os.path.join(data, "talentbridge.db")):
        sys.exit(f"No database at {data}")
    if args.apply:
        print("Backup written to", backup(data))
    os.environ.update(DATABASE_URL="sqlite:///" + os.path.join(data, "talentbridge.db"), UPLOAD_DIR=os.path.join(data, "uploads"),
                      EMBEDDED_WORKER="0", DEMO_SEED="0")
    from app.config import Config
    from app import create_app, pipeline as pl
    from app.db import jl, jd, uid, now
    from app.cv_parser import parse_cv
    from app.profile import normalise
    c = create_app(Config()).ctx               # applies migrations + backfill (identity flags, application snapshots)
    db = c.db
    orgs = db.all("SELECT id, name FROM organizations")
    default_org = next((o["id"] for o in orgs if args.org and o["name"].lower() == args.org.lower()), None) or \
        (orgs[0]["id"] if len(orgs) == 1 else None)
    system = {"id": None, "role": "system"}
    plan, unresolved, touched_sources, touched_apps, targets = [], [], set(), set(), set()

    for cv in db.all("""SELECT v.*, ca.full_name AS owner_name, ca.email AS owner_email FROM cvs v JOIN candidates ca ON ca.id=v.candidate_id
                        WHERE v.identity_status='mismatch' ORDER BY v.created_at"""):
        det = jl(cv["identity_detail"]) or {}
        apps = db.all("SELECT a.id, j.organization_id, j.title FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.cv_id=?", (cv["id"],))
        email = (det.get("cv_email") or "").lower() or None
        target = db.one("SELECT * FROM candidates WHERE email=?", (email,)) if email else None
        app_orgs = {a["organization_id"] for a in apps}
        org = next(iter(app_orgs)) if len(app_orgs) == 1 else (default_org if not apps else None)
        line = f"CV '{cv['original_name']}' on record of {cv['owner_name']} <{cv['owner_email']}> reads as {det.get('cv_name')} <{email}>"
        if not det.get("cv_name"):
            unresolved.append(line + ": no readable name"); continue
        if target is None and org is None:
            unresolved.append(line + ": cannot tell which organisation should manage the new record (use --org)"); continue
        plan.append((cv, det, email, target, org, apps))
        print("PLAN  ", line)
        print("       ->", f"existing record {target['full_name']}" if target else f"new record '{det['cv_name']}' (recruiter-managed)",
              f"; moves {len(apps)} application(s): {', '.join(a['title'] for a in apps) or 'none'}")

    for u in unresolved:
        print("UNRESOLVED", u)
    if not plan:
        print("Nothing to repair.")
    if not args.apply:
        print("\nDry run only. Re-run with --apply to make these changes (a backup is taken first).")
        return

    for cv, det, email, target, org, apps in plan:
        if target is None:
            ext = jl(cv["extraction"]) or {}
            tid, t = uid(), now()
            db.execute("INSERT INTO candidates (id,managed_by_org_id,email,full_name,phone,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                       (tid, org, email or f"no-email+{tid[:12]}@invalid.local", det["cv_name"], ext.get("phone"), t, t))
            pl.log(c, "candidate.created_by_repair", "candidate", tid, {"from_cv": cv["id"]})
        else:
            tid = target["id"]
        touched_sources.add(cv["candidate_id"]); targets.add(tid)
        moved = pl.reassign_cv(c, cv["id"], tid, system)
        touched_apps.update(moved)
        print("MOVED ", cv["original_name"], "->", det["cv_name"], f"({len(moved)} application(s))")

    # re-read touched CVs with the current parser; machine-only snapshots follow, human-edited ones are left as submitted
    people = touched_sources | targets
    for cv in db.all(f"SELECT * FROM cvs WHERE candidate_id IN ({','.join('?' * len(people))})", list(people)) if people else []:
        if cv["stage"] != "ready" or not cv["extracted_text"]:
            continue
        old = jl(cv["extraction"])
        new = normalise(parse_cv(cv["extracted_text"]))
        db.execute("UPDATE cvs SET extraction=? WHERE id=?", (jd(new), cv["id"]))
        for a in db.all("SELECT id, profile_snapshot FROM applications WHERE cv_id=?", (cv["id"],)):
            if same_machine_profile(jl(a["profile_snapshot"]), old):
                db.execute("UPDATE applications SET profile_snapshot=? WHERE id=?", (jd(new), a["id"]))
                pl.log(c, "application.snapshot_reparsed", "application", a["id"], {"cv_id": cv["id"], "reason": "identity repair; profile had no human edits"})
                touched_apps.add(a["id"])
        cand = db.one("SELECT * FROM candidates WHERE id=?", (cv["candidate_id"],))
        if cand["active_cv_id"] == cv["id"] or (cand["active_cv_id"] is None and cv["identity_status"] in ("match", "reassigned")):
            pl.apply_cv_to_candidate(c, cv["id"])

    # source records: profile back from their own CV
    for sid in touched_sources:
        own = db.one("SELECT id FROM cvs WHERE candidate_id=? AND stage='ready' AND identity_status IN ('match','confirmed') ORDER BY created_at DESC LIMIT 1", (sid,))
        if own:
            pl.apply_cv_to_candidate(c, own["id"])
            pl.log(c, "candidate.profile_restored", "candidate", sid, {"from_cv": own["id"], "reason": "identity repair"})
            print("RESTORED profile of", db.scalar("SELECT full_name FROM candidates WHERE id=?", (sid,)), "from their own CV (draft, needs re-confirming)")
            touched_apps.update(r["id"] for r in db.all("SELECT id FROM applications WHERE candidate_id=?", (sid,)))
        else:
            print("UNRESOLVED", db.scalar("SELECT full_name FROM candidates WHERE id=?", (sid,)), "has no CV of their own; profile left as is")

    for aid in sorted(touched_apps):
        before = db.scalar("SELECT match_score FROM applications WHERE id=?", (aid,))
        m = pl.recompute_match(c, aid, reason="identity repair")
        print(f"RESCORED application {aid[:8]}: {before} -> {m['score'] if m else None} (previous kept in match_history)")
    print("Done.")


if __name__ == "__main__":
    main()
