"""AI-assisted CV reading with verification.

The rule-based parser (cv_parser.py) always runs first. A language model then reads the same CV and proposes skills, roles,
education and contact details. Nothing the model proposes is accepted unless it can be found in the CV text itself:
  skill        the name appears in the CV; 'shown in use' only when it appears in a role or project description
  role         title AND company both appear in the CV; a date is kept only if its year appears in the CV
  education    the institution appears in the CV
  name/contact only fills a field the parser left empty, and only with text that is in the CV
Every accepted item is listed in `ai_additions`, so a reviewer can see exactly what the model contributed.
"""
import re
from .validation import S, I, A, O
from . import skills_data as sd

PROFILE_ASSIST_SCHEMA = O({
    "full_name": S(maxLength=120, nullable=True), "email": S(maxLength=200, nullable=True), "phone": S(maxLength=40, nullable=True),
    "skills": A(O({"name": S(maxLength=60), "evidence": S(maxLength=300, nullable=True)}, ["name"]), maxItems=40),
    "work_history": A(O({"title": S(maxLength=120), "company": S(maxLength=160), "start": S(maxLength=10, nullable=True),
                         "end": S(maxLength=10, nullable=True)}, ["title", "company"]), maxItems=15),
    "education": A(O({"degree": S(maxLength=120), "field": S(maxLength=120, nullable=True), "institution": S(maxLength=160),
                      "graduation_year": I(minimum=1950, maximum=2100, nullable=True)}, ["degree", "institution"]), maxItems=6),
}, ["skills", "work_history", "education"])

PROMPT = ("Read the CV and list: every skill, tool, technology, method or professional competency it names (with the sentence that "
          "shows it used, copied from the CV, or null if it is only listed); every job (title, company, start and end as YYYY-MM, "
          "YYYY or 'present'); every degree or diploma; and the candidate's name, e-mail and phone. Copy names exactly as written in "
          "the CV. Do not add anything that is not written in the CV.\n")
MAX_MODEL_TEXT = 20000
SOFT = {"communication", "teamwork", "leadership", "problem solving", "time management", "hard working", "hardworking", "team player"}


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w+#./@ -]", " ", (s or "").lower())).strip()


def in_text(value, ntext):
    v = norm(value)
    if len(v) < 2:
        return False
    return bool(re.search(r"(?<![\w])" + re.escape(v) + r"(?![\w])", ntext))


def _evidence(profile):
    parts = []
    for w in profile.get("work_history", []):
        parts += [w.get("description", "")] + list(w.get("achievements", []))
    for p in profile.get("projects", []):
        parts += [p.get("name", ""), p.get("description", "")]
    return [x for x in parts if x]


def _sentence_with(name, chunks):
    for c in chunks:
        for s in re.split(r"(?<=[.!?;])\s+|\n", c):
            if in_text(name, norm(s)):
                return s.strip()[:300]
    return None


def _date(v, ntext):
    v = (v or "").strip().lower()
    if v in ("present", "current", "now"):
        return "present"
    m = re.match(r"^((?:19|20)\d{2})(?:-(\d{1,2}))?$", v)
    if not m or m.group(1) not in ntext:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m.group(2) and 1 <= int(m.group(2)) <= 12 else m.group(1)


def _same(a, b):
    a, b = norm(a), norm(b)
    return bool(a and b) and (a == b or a in b or b in a)


def merge_verified(profile, proposed, text):
    """-> (profile, additions). `profile` is the rule-based result; `proposed` the model's output (PROFILE_ASSIST_SCHEMA)."""
    from .matching import canon
    p = {**profile, "skills": list(profile.get("skills", [])), "work_history": list(profile.get("work_history", [])),
         "education": list(profile.get("education", []))}
    ntext, adds = norm(text), []

    if (not p.get("full_name") or p["full_name"].startswith("Name not found")) and proposed.get("full_name") and in_text(proposed["full_name"], ntext):
        p["full_name"] = proposed["full_name"].strip()[:120]
        adds.append(f"Name: {p['full_name']}")
    for k in ("email", "phone"):
        v = (proposed.get(k) or "").strip()
        if not p.get(k) and v and norm(v) in ntext:
            p[k] = v
            adds.append(f"{k.capitalize()}: {v}")

    for r in proposed.get("work_history", []):
        if not (in_text(r["title"], ntext) and in_text(r["company"], ntext)):
            continue
        start, end = _date(r.get("start"), ntext), _date(r.get("end"), ntext)
        mine = next((w for w in p["work_history"] if _same(w.get("company"), r["company"])
                     or (_same(w.get("title"), r["title"]) and w.get("start") == "unknown")), None)
        if mine:
            if mine.get("start") == "unknown" and start and _same(mine.get("company"), r["company"]):
                mine.update({"start": start, "end": end or "present"})
                adds.append(f"Dates for {mine.get('title')} at {mine.get('company')}: {start} to {end or 'present'}")
            continue
        line = next((ln.strip() for ln in text.splitlines() if in_text(r["company"], norm(ln))), "")
        p["work_history"].append({"title": r["title"].strip()[:120], "company": r["company"].strip()[:160], "start": start or "unknown",
                                  "end": (end or "present") if start else None, "description": line[:1200], "achievements": []})
        adds.append(f"Role: {r['title']} at {r['company']}")

    for e in proposed.get("education", []):
        if not in_text(e["institution"], ntext) or any(_same(x.get("institution"), e["institution"]) for x in p["education"]):
            continue
        unknown = next((x for x in p["education"] if x.get("institution") == "Unknown institution"), None)
        if unknown:
            unknown["institution"] = e["institution"].strip()[:160]
        else:
            yr = e.get("graduation_year") if e.get("graduation_year") and str(e["graduation_year"]) in ntext else None
            p["education"].append({"degree": e["degree"].strip()[:120], "field": e.get("field"), "institution": e["institution"].strip()[:160],
                                   "graduation_year": yr, "grade": None})
        adds.append(f"Education: {e['degree']}, {e['institution']}")

    have = {canon(s["name"]) for s in p["skills"]}
    evidence = _evidence(p)
    added = 0
    for s in proposed.get("skills", []):
        name = re.sub(r"\s+", " ", s["name"]).strip(" .,;")
        key = canon(name)
        if added >= 25 or len(name) < 2 or len(name) > 40 or key in have or not in_text(name, ntext):
            continue
        used = _sentence_with(name, evidence)
        level = "demonstrated" if used and name.lower() not in SOFT else "listed"
        p["skills"].append({"name": sd.display(key) if sd.canonical(name) else name, "level": level, "proficiency": "unknown",
                            "context": used or "Named in the CV (found by the AI reader)"})
        have.add(key)
        added += 1
        adds.append(f"Skill: {name}" + (" (shown in use)" if level == "demonstrated" else ""))

    if adds:
        p["confidence"] = round(min(0.9, float(p.get("confidence") or 0.5) + 0.05), 2)
        p["strengths"] = (p.get("strengths") or [])[:7] + [f"The AI reader added {len(adds)} item(s), each verified against the CV text"]
    p["ai_additions"] = adds[:40]
    return p, adds
