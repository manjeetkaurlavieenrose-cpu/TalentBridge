"""The local engine: everything the AI layer does, with no network and no paid service.

CV parsing .......... cv_parser.py   (patterns + a built-in skills list)
Match explanation ... matching.py + this file (requirement-by-requirement evidence lookup in the candidate's own text)
Question writing .... question_bank.py (templates personalised with facts from the CV and the job)
Answer scoring ...... answer_scorer.py (explicit rubric: coverage of expected points + depth/structure/clarity)

It is deterministic: the same inputs always give the same outputs. It is not a language model and does not claim to be.
"""
import re
from .cv_parser import parse_cv
from .question_bank import build_assessment
from .answer_scorer import score_answers, content_words, stem
from .matching import compute_match
from . import skills_data as sd

ENGINE = "local-rules-v1"
GENERIC_REQ = set("experience skills skill knowledge ability strong good excellent working proven demonstrated understanding years".split())


def _entries(profile):
    """Evidence grouped by where it came from: [(where, [sentence, ...])]. A sentence is the unit we quote back."""
    def sents(*texts):
        out = []
        for t in texts:
            for p in re.split(r"(?<=[.!?])\s+|\s*[•\n]\s*", t or ""):
                if len(p.strip()) > 3:
                    out.append(p.strip())
        return out
    ents = []
    for w in profile.get("work_history", []):
        ents.append((f"{w.get('title', '')} at {w.get('company', '')}".strip(), sents(w.get("description", ""), *w.get("achievements", []))))
    for p in profile.get("projects", []):
        ents.append((f"project {p.get('name', '')}", sents(p.get("name", ""), p.get("description", ""))))
    for s_ in profile.get("skills", []):
        if s_.get("context"):
            ents.append((f"skill {s_['name']}", sents(s_["context"])))
    for c in profile.get("certifications", []):
        ents.append(("certification", sents(c.get("name", ""))))
    ents.append(("achievements", sents(*profile.get("achievements", []))))
    if profile.get("summary"):
        ents.append(("summary", sents(profile["summary"])))
    for e in profile.get("education", []):
        ents.append(("education", sents(" ".join(filter(None, [e.get("degree"), e.get("field")])))))
    return [(w, ss) for w, ss in ents if ss]


def check_requirement(req, profile):
    """-> {'requirement', 'status', 'evidence'}. Evidence is one verbatim sentence from the CV, never invented.
    met      all/most requirement words in one sentence, or all of them within the same role/project
    partial  some of the words appear in one sentence, or spread across the profile
    unmet    nothing relevant found"""
    want = list(dict.fromkeys(stem(w) for w in content_words(req) if w not in GENERIC_REQ))
    if not want:
        return {"requirement": req, "status": "unmet", "evidence": "The requirement could not be checked automatically."}

    def hits(text):
        st = {stem(w) for w in content_words(text)}
        return {w for w in want if any(s.startswith(w) or (w.startswith(s) and len(s) >= 4) for s in st)}
    best_sent, best_frac, best_entry_frac, entry_best, overall = None, 0.0, 0.0, None, set()
    for where, ss in _entries(profile):
        ent_hits = set()
        for sent in ss:
            h = hits(sent)
            ent_hits |= h
            overall |= h
            if len(h) / len(want) > best_frac:
                best_frac, best_sent = len(h) / len(want), (sent, where)
        if len(ent_hits) / len(want) > best_entry_frac:
            best_entry_frac = len(ent_hits) / len(want)
            entry_best = (where, ss)
    if best_sent is None:
        return {"requirement": req, "status": "unmet", "evidence": "No supporting text found in the CV."}
    entry_hits = round(best_entry_frac * len(want))
    if best_frac >= 0.6 or best_entry_frac >= 0.99:
        status = "met"
    elif entry_hits >= 2 or (len(want) <= 2 and overall):
        status = "partial"
    else:
        return {"requirement": req, "status": "unmet", "evidence": "No supporting text found in the CV."}
    sent, where = best_sent
    shown = [sent]
    if status == "met" and best_frac < 0.6 and entry_best:      # words are spread over sentences of ONE role/project: quote those sentences
        where, ss = entry_best
        left, shown = set(want), []
        while left:
            pick = max(ss, key=lambda t: len(hits(t) & left))
            gain = hits(pick) & left
            if not gain:
                break
            shown.append(pick)
            left -= gain
    ev = " ".join(re.sub(" +", " ", x) for x in shown[:2])
    return {"requirement": req, "status": status, "evidence": f"“{ev[:230]}” ({where})"[:300]}


class LocalAI:
    """Same four capabilities as the model-based providers, implemented with rules."""
    is_local = True
    engine = ENGINE

    def extract_profile(self, text, fallback_name=None):
        return parse_cv(text, fallback_name)

    def analyse_application(self, profile, job):
        reqs = [check_requirement(r, profile) for r in (job.get("custom_requirements") or [])]
        m = compute_match(profile, {**job, "custom_requirements": []}, None, None)
        sk = m["skills"]
        req = [s for s in sk if s["kind"] == "required"]
        got = [s["skill"] for s in req if s["status"] == "match"]
        part = [s["skill"] for s in req if s["status"] == "partial"]
        miss = [s["skill"] for s in req if s["status"] == "missing"]
        yrs, need = m["experience"]["years"], m["experience"]["required"]
        strengths = []
        if got:
            strengths.append("Shown in use for required skills: " + ", ".join(got[:6]))
        pref = [s["skill"] for s in sk if s["kind"] == "preferred" and s["status"] == "match"]
        if pref:
            strengths.append("Preferred skills shown: " + ", ".join(pref[:5]))
        if need and yrs >= need:
            strengths.append(f"{yrs} years of dated experience (role asks {need}+)")
        for r in reqs:
            if r["status"] == "met":
                strengths.append(f"Evidence for “{r['requirement']}”")
        gaps = [f"No evidence of {s} in the CV" for s in miss] + [f"{s}: listed or related, but not clearly shown in use" for s in part]
        gaps += [f"“{r['requirement']}”: nothing in the CV supports this" for r in reqs if r["status"] == "unmet"]
        risks = []
        if need and yrs < need:
            risks.append(f"Dated experience ({yrs} yrs) is below the {need} yrs requested; undated roles are not counted")
        if any(w.get("start") == "unknown" for w in profile.get("work_history", [])):
            risks.append("Some roles have no readable dates, so experience length is understated")
        if profile.get("confidence", 1) < 0.6:
            risks.append("The CV was only partly understood by the parser; check the profile")
        qs = []
        for s in miss + part:
            qs.append(f"Your CV does not clearly show {s} in use. Have you worked with it, and how quickly could you be productive?")
        for s in req:
            if s["status"] == "match":
                qs.append(f"Walk us through a concrete example of using {s['skill']}. {s['evidence'].replace('Demonstrated: ', '')[:150]}")
                break
        for r in reqs:
            if r["status"] != "met":
                qs.append(f"The role asks for “{r['requirement']}”. What is your closest experience?")
        total = len(req) or 1
        summary = (f"{len(got)} of {total} required skills are shown in use in the CV" + (f"; {len(part)} only partly" if part else "") +
                   (f"; {len(miss)} not found" if miss else "") + f". Dated experience: {yrs} years (role asks {need}+)." if need else
                   f"{len(got)} of {total} required skills are shown in use in the CV. Dated experience: {yrs} years.")
        return {"summary": summary[:900], "strengths": strengths[:8], "gaps": gaps[:8], "risks": risks[:6], "requirements_check": reqs[:15],
                "interview_questions": [q[:300] for q in qs[:8]], "confidence": round(min(0.8, float(profile.get("confidence") or 0.5)), 2)}

    def generate_assessment(self, profile, job):
        return build_assessment(profile, job)

    def evaluate(self, task, answers, profile, job):
        return score_answers(task, answers)
