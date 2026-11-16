"""What the browser can honestly tell us about how a test was taken. Evidence for a reviewer, never a verdict.

Recorded while the candidate has the test open (they are told before they start, and warned on screen as it happens):
  left_page    the page lost focus or the tab was hidden, and for how many seconds (switching tab/window, another app)
  pointer_out  the mouse pointer was outside the page for a while (a weak signal: people do this when they think)
  paste        text was pasted into an answer: how many characters, into which question
  typed        how many characters were typed into an answer (counts only)
Only counts and durations are stored. Never the text of what was pasted, never anything typed elsewhere, no camera, no screen
capture, no keystroke logging, nothing outside the test page.

What this cannot see: a second phone or laptop, a person helping in the room, an AI used on another device, answers memorised
from an earlier session. A candidate can also keep a chatbot window beside the test without ever leaving the page, and a browser
extension or assistive technology can look like pasting. So a quiet record is not proof of honesty and a busy one is not proof of
misconduct. It is context for a person who also reads the answers and compares them with other candidates' answers.
"""
from .db import now, uid, jl

KINDS = ("left_page", "pointer_out", "paste", "typed")
MAX_EVENTS = 600
AWAY_NOTABLE_SECONDS, AWAY_NOTABLE_COUNT = 120, 5
PASTE_NOTABLE_CHARS, PASTE_NOTABLE_SHARE = 200, 0.5


def record(c, assessment_id, events):
    """Store up to MAX_EVENTS per assessment. -> number stored."""
    have = c.db.scalar("SELECT COUNT(*) FROM assessment_events WHERE assessment_id=?", (assessment_id,)) or 0
    room = max(0, MAX_EVENTS - have)
    t = now()
    stored = 0
    for e in events[:room]:
        c.db.execute("INSERT INTO assessment_events (id,assessment_id,kind,question_id,seconds,chars,at) VALUES (?,?,?,?,?,?,?)",
                     (uid(), assessment_id, e["kind"], e.get("question_id"), e.get("seconds"), e.get("chars"), t))
        stored += 1
    return stored


def summary(c, assessment_id, started_at=None, submitted_at=None):
    """-> None when nothing was recorded, else counts, per-question typed/pasted split and plain-language notes."""
    rows = c.db.all("SELECT kind, question_id, seconds, chars FROM assessment_events WHERE assessment_id=?", (assessment_id,))
    if not rows:
        return None
    left = [r for r in rows if r["kind"] == "left_page"]
    ptr = [r for r in rows if r["kind"] == "pointer_out"]
    pasted = [r for r in rows if r["kind"] == "paste"]
    per_q = {}
    for r in rows:
        if r["kind"] in ("paste", "typed") and r["question_id"]:
            q = per_q.setdefault(r["question_id"], {"typed": 0, "pasted": 0, "pastes": 0})
            if r["kind"] == "paste":
                q["pasted"] += r["chars"] or 0
                q["pastes"] += 1
            else:
                q["typed"] += r["chars"] or 0
    for q in per_q.values():
        total = q["typed"] + q["pasted"]
        q["pasted_share"] = round(q["pasted"] / total, 2) if total else 0.0
    out = {"left_count": len(left), "left_seconds": round(sum(r["seconds"] or 0 for r in left)),
           "longest_away_seconds": round(max((r["seconds"] or 0 for r in left), default=0)),
           "pointer_out_count": len(ptr), "pointer_out_seconds": round(sum(r["seconds"] or 0 for r in ptr)),
           "paste_count": len(pasted), "pasted_chars": sum(r["chars"] or 0 for r in pasted),
           "typed_chars": sum(q["typed"] for q in per_q.values()), "per_question": per_q, "notes": [], "notable": False}
    total = out["typed_chars"] + out["pasted_chars"]
    out["pasted_share"] = round(out["pasted_chars"] / total, 2) if total else 0.0
    if out["left_seconds"] >= AWAY_NOTABLE_SECONDS or out["left_count"] >= AWAY_NOTABLE_COUNT:
        out["notable"] = True
        out["notes"].append(f"The candidate left the test page {out['left_count']} time(s), {out['left_seconds']} seconds in all "
                            f"(longest {out['longest_away_seconds']} s). There are many innocent reasons: a notification, a calculator, the wrong window.")
    heavy = [qid for qid, q in per_q.items() if q["pasted"] >= PASTE_NOTABLE_CHARS and q["pasted_share"] >= PASTE_NOTABLE_SHARE]
    if heavy or (out["pasted_chars"] >= PASTE_NOTABLE_CHARS and out["pasted_share"] >= PASTE_NOTABLE_SHARE):
        out["notable"] = True
        where = " Mostly pasted: " + ", ".join(f"{qid} ({round(per_q[qid]['pasted_share'] * 100)}%)" for qid in heavy) + "." if heavy else ""
        out["notes"].append(f"{out['pasted_chars']} characters were pasted in {out['paste_count']} paste(s) and {out['typed_chars']} typed.{where} "
                            "Pasting from the candidate's own notes is possible; the test asks for their own words.")
    if not out["notes"]:
        out["notes"].append("Nothing unusual: the page was mostly in focus and most of the text was typed.")
    return out
