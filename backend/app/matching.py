"""Explainable match score. Pure function of (profile, job, assessment score, requirement check). Version: SCORING_VERSION.

How the overall job-match score is calculated (the same function feeds every screen, the CSV export and the dashboard)
  1. CV match (0-100): weighted average of the components that apply to the opening
        required skills 35 · preferred skills 10 · experience 15 · education 10 · other requirements 10
     A component the opening does not use (no preferred skills, no other requirements) is left out and the remaining
     weights are rescaled to 100. Nothing is left out because the CV lacks information: missing evidence scores 0.
  2. Overall: while no assessment has been scored, overall = CV match and the result is marked provisional.
     Once an assessment is scored:  overall = 0.8 x CV match + 0.2 x assessment score.
Skill credit:  shown in use (work/project text) 1.0 · mentioned in work/project text 0.6 · listed only 0.5 ·
               related skill 0.4 · not found 0. "Not found" means the CV does not mention it, not that the person lacks it.
Experience:    years from dated roles only (overlaps counted once). Undated roles earn no credit and are reported as
               "not verifiable", never as zero experience.
"""
import hashlib, json, re
from datetime import date

SCORING_VERSION = "match-v2"
ALIASES = {"powerbi": "power bi", "ms excel": "excel", "microsoft excel": "excel", "js": "javascript", "ts": "typescript",
           "postgres": "postgresql", "psql": "postgresql", "ml": "machine learning", "gcp": "google cloud",
           "k8s": "kubernetes", "node": "node.js", "nodejs": "node.js", "reactjs": "react", "ga": "google analytics",
           "structured query language": "sql", "data analytics": "data analysis", "dataviz": "data visualization"}
RELATED = {"power bi": ["tableau", "looker", "data visualization", "qlik"], "tableau": ["power bi", "looker", "data visualization"],
           "sql": ["postgresql", "mysql", "sqlite", "bigquery"], "postgresql": ["sql", "mysql"],
           "excel": ["google sheets"], "python": ["r", "pandas"], "pandas": ["python"], "react": ["vue", "angular", "javascript"],
           "javascript": ["typescript"], "typescript": ["javascript"], "data analysis": ["statistics", "data visualization"],
           "research": ["qualitative research", "quantitative research", "policy analysis"]}
# Using one of these in work IS using the general skill (writing PostgreSQL queries is writing SQL). Not used the other way round.
SPECIALISATIONS = {"sql": ["postgresql", "mysql", "sqlite", "bigquery", "oracle", "snowflake"], "python": ["pandas", "numpy", "django", "flask", "fastapi"],
                   "javascript": ["react", "typescript", "node.js"], "data visualization": ["power bi", "tableau", "looker", "dashboards"],
                   "machine learning": ["scikit-learn", "tensorflow", "pytorch"]}
EDU_RANK = {"none": 0, "high_school": 1, "diploma": 2, "bachelor": 3, "master": 4, "phd": 5}
EDU_NAME = {0: "none", 1: "high school", 2: "diploma", 3: "bachelor's", 4: "master's", 5: "doctorate"}
WEIGHTS = {"required": 35, "preferred": 10, "experience": 15, "education": 10, "custom": 10}
ASSESSMENT_SHARE = 0.2
NOT_FOUND = "Not found in the CV (this does not prove the candidate lacks it)"


def canon(s):
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    s = ALIASES.get(s, s)
    from .skills_data import canonical      # shared taxonomy: "MS Excel" == "Excel", "Postgres" == "PostgreSQL" ...
    return canonical(s) or s


def edu_rank(profile):
    best = 0
    for e in profile.get("education", []):
        d = (e.get("degree") or "").lower()
        r = 5 if re.search(r"ph\.?d|doctor", d) else 4 if re.search(r"master|m\.?sc|m\.?a\b|mba|m\.?tech|postgrad", d) else \
            3 if re.search(r"bachelor|b\.?sc|b\.?a\b|b\.?tech|b\.?e\b|undergrad|honours", d) else \
            2 if "diploma" in d else 1 if re.search(r"high school|secondary|12th|a-level", d) else 0
        best = max(best, r)
    return best


def _evidence_text(profile):
    chunks = [w.get("description", "") + " " + " ".join(w.get("achievements", [])) for w in profile.get("work_history", [])]
    chunks += [p.get("name", "") + " " + p.get("description", "") + " " + " ".join(p.get("skills", [])) for p in profile.get("projects", [])]
    return " ".join(chunks).lower()


def _mentions(c, text):
    return bool(re.search(r"(?<![a-z])" + re.escape(c) + r"(?![a-z])", text))


def skill_status(skill, idx, text):
    """-> (status, credit, evidence). status: match (shown in use) | partial (listed / related / mentioned) | missing."""
    c = canon(skill)
    s = idx.get(c)
    if s and s.get("level") == "demonstrated":
        return "match", 1.0, f"Shown in use: {s.get('context') or 'described in work or projects'}"
    for sp in SPECIALISATIONS.get(c, []):
        x = idx.get(sp)
        if x and x.get("level") == "demonstrated":
            return "match", 1.0, f"Shown in use through {x['name']}: {x.get('context') or 'described in work or projects'}"
    if s:
        if _mentions(c, text):
            return "match", 1.0, "Appears in work or project descriptions"
        if (s.get("context") or "").lower().startswith("certification"):
            return "partial", 0.5, f"{s['context']} (a certificate, not shown in use)"
        return "partial", 0.5, "Listed in the skills section; no usage described"
    if _mentions(c, text):
        return "partial", 0.6, "Mentioned in work or project text"
    for r in RELATED.get(c, []):
        if r in idx:
            return "partial", 0.4, f"Related skill: {idx[r]['name']}"
    return "missing", 0.0, NOT_FOUND


def _experience(profile, need):
    roles = profile.get("work_history", []) or []
    dated = [w for w in roles if re.match(r"^\d{4}", str(w.get("start") or ""))]
    undated = len(roles) - len(dated)
    yrs = profile.get("total_experience_years") or 0
    out = {"years": yrs, "required": need, "dated_roles": len(dated), "undated_roles": undated}
    if need <= 0:
        return 100.0, {**out, "ok": True, "status": "not_required", "note": "The opening sets no minimum."}
    if not roles:
        return 0.0, {**out, "ok": False, "status": "missing", "note": "No employment history was found in the CV."}
    if not dated:
        return 0.0, {**out, "ok": False, "status": "unverified",
                     "note": f"{undated} role(s) found but none has readable dates, so length of experience could not be verified."}
    note = f"{yrs} years from {len(dated)} dated role(s)"
    if undated:
        note += f"; {undated} undated role(s) not counted"
    ok = yrs >= need
    return min(yrs / need, 1) * 100, {**out, "ok": ok, "status": "met" if ok else "below", "note": note + "."}


def _education(profile, need):
    have = edu_rank(profile)
    out = {"have": have, "required": need, "have_label": EDU_NAME[have], "required_label": EDU_NAME[need]}
    if need == 0:
        return 100.0, {**out, "ok": True, "status": "not_required", "note": "The opening sets no minimum."}
    if not profile.get("education"):
        return 0.0, {**out, "ok": False, "status": "missing", "note": "No education entry was found in the CV."}
    if have >= need:
        return 100.0, {**out, "ok": True, "status": "met", "note": f"Highest level found: {EDU_NAME[have]} (asks {EDU_NAME[need]})."}
    if have == need - 1:
        return 50.0, {**out, "ok": False, "status": "partial", "note": f"Highest level found: {EDU_NAME[have]}, one level below {EDU_NAME[need]}."}
    return 0.0, {**out, "ok": False, "status": "below", "note": f"Highest level found: {EDU_NAME[have] if have else 'not recognised'}."}


def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def compute_match(profile, job, assessment_score=None, requirements_check=None, cv_text=None, encoder=None, as_of=None):
    idx = {canon(s["name"]): s for s in profile.get("skills", [])}
    text = _evidence_text(profile)
    skills, comps = [], {}
    parsed = bool(profile.get("skills") or profile.get("work_history") or profile.get("projects"))

    def skill_group(kind):
        names = job.get(f"{kind}_skills", [])
        if not names: return None
        pts = 0.0
        for n in names:
            st, pt, why = skill_status(n, idx, text)
            if st == "missing" and not parsed:
                st, why = "unknown", "The CV could not be read for skills; nothing can be concluded"
            skills.append({"skill": n, "kind": kind, "status": st, "credit": pt, "evidence": why}); pts += pt
        return pts / len(names) * 100

    for kind in ("required", "preferred"):
        v = skill_group(kind)
        if v is not None: comps[kind] = v

    need = job.get("min_years") or 0
    comps["experience"], experience = _experience(profile, need)
    comps["education"], education = _education(profile, EDU_RANK.get(job.get("education_level", "none"), 0))
    if requirements_check:
        val = {"met": 1, "partial": .5, "unmet": 0}
        comps["custom"] = sum(val[r["status"]] for r in requirements_check) / len(requirements_check) * 100

    used = {k: WEIGHTS[k] for k in comps}
    tot = sum(used.values()) or 1
    cv_score = round(sum(comps[k] * w for k, w in used.items()) / tot, 1)
    has_a = assessment_score is not None
    share = (1 - ASSESSMENT_SHARE) if has_a else 1.0
    overall = round(cv_score * share + (float(assessment_score) * ASSESSMENT_SHARE if has_a else 0), 1)
    components = {k: {"score": round(v, 1), "weight": round(used[k] * 100 / tot * share, 1)} for k, v in comps.items()}
    if has_a:
        components["assessment"] = {"score": round(float(assessment_score), 1), "weight": round(ASSESSMENT_SHARE * 100, 1)}

    sim = None
    if cv_text:
        from . import similarity
        sim = similarity.compare(cv_text, similarity.job_text(job), encoder)
    limits = ["Skills are matched by name using a built-in skills list; a synonym outside that list can be missed, so check 'not found' skills by hand.",
              "Experience years come from dated roles on the CV; undated roles are reported but not counted.",
              "A skill counts as shown in use only when the CV describes using it; a skills-list entry or a certificate earns partial credit.",
              "The score ranks CV evidence (and, once scored, the assessment) against the opening. It is not a prediction of job performance."]
    if sim:
        limits.append("The text-similarity figure is a rough word-overlap pointer. It is not semantic understanding and is not part of the score.")
    inputs = {"profile": fingerprint(profile), "job": fingerprint({k: job.get(k) for k in ("required_skills", "preferred_skills", "min_years",
              "education_level", "custom_requirements")}), "assessment": assessment_score}
    return {"score": overall, "cv_score": cv_score, "provisional": not has_a, "similarity": sim, "limitations": limits,
            "components": components, "skills": skills, "experience": experience, "education": education,
            "requirements": requirements_check or [], "assessment": assessment_score,
            "scoring_version": SCORING_VERSION, "inputs": inputs, "as_of": (as_of or date.today()).isoformat(),
            "method": ("Overall = CV match" if not has_a else "Overall = 0.8 × CV match + 0.2 × assessment") +
                      ". CV match = weighted average of the listed components (weights rescaled to the components this opening uses)."}
