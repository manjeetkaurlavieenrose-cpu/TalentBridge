"""Originality checks: CV similarity / shared templates, and plagiarism between assessment answers.

What is compared (everything is deterministic and reproducible; no model is needed):

  CVs      Each application's CV text is compared with the CVs of OTHER candidates who applied to the same organisation.
           verbatim   share of 5-word sequences the two CVs have in common (numbers ignored, contact details removed).
           template   the same, after names, tools, numbers and other proper nouns are blanked out. Two CVs written from one
                      template ("Improved <X> by <N>% using <TOOL> at <COMPANY>") match here even when every fill-in differs.
           same file  the identical file uploaded from another account.
           Wording copied from the job advertisement is ignored: tailoring a CV to the ad is normal.

  Answers  Each submitted answer is compared with the answers other candidates gave for the same opening.
           overlap    share of 4-word sequences in common, after removing the wording of the question itself.
           identical  the same text, ignoring case, spacing and punctuation.
           chatbot    phrases that normally only appear in a pasted chatbot reply ("As an AI language model", "I hope this helps").
           speed      more words than a person can type in the time between Start and Submit.
           meaning    (only when an embedding model is configured) answers that say the same thing in different words. Shown for
                      information; it never raises a flag on its own, because two correct answers are naturally close in meaning.

What it is not: it is not an "AI detector". Whether a text was written by a person or a model cannot be decided reliably from the
text, and this module does not try. It reports evidence a reviewer can read and verify: the matching passages, who they match,
and how much. A flag never changes a score and never moves an application; a person decides what it means.
"""
import hashlib, re
from datetime import datetime
from functools import lru_cache
from .db import now, uid, jd, jl

VERSION = "originality-v1"
LEVELS = ("none", "low", "medium", "high")
RANK = {k: i for i, k in enumerate(LEVELS)}
FLAGGED = ("medium", "high")

# thresholds, in one place so they can be read and tuned
CV_HIGH, CV_MEDIUM, CV_LOW = 0.55, 0.25, 0.12            # verbatim overlap
TPL_MEDIUM, TPL_LOW, TPL_MIN_SENTENCES = 0.45, 0.30, 4    # template overlap needs several shared sentence shapes
ANS_HIGH, ANS_MEDIUM, ANS_LOW = 0.60, 0.30, 0.15
ANS_MIN_WORDS = 20            # shorter answers have too little text to compare (identical ones are still caught from 8 words)
SPEED_WPM, SPEED_MIN_WORDS = 90, 150
MEANING_MIN = 0.93
POOL_LIMIT = 1500

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin|github)\.com/\S+", re.I)
PHONE = re.compile(r"\+?\d[\d ()\-]{7,}\d")
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#'’]*")

# Stock résumé phrasing. Common in generated CVs, but also in plenty written by people: shown as context, never flagged alone.
STOCK = [
    "results-driven", "results driven", "detail-oriented", "detail oriented", "highly motivated", "proven track record", "track record of",
    "dynamic professional", "seasoned professional", "passionate about", "fast-paced environment", "cross-functional teams",
    "cross-functional collaboration", "leveraged", "leveraging", "spearheaded", "orchestrated", "synergy", "synergies",
    "stakeholder engagement", "data-driven decision", "drive business growth", "driving business growth", "strong work ethic",
    "excellent communication skills", "team player", "go-getter", "think outside the box", "value-added", "best-in-class",
    "cutting-edge", "state-of-the-art", "seamless", "robust and scalable", "adept at", "committed to delivering", "eager to contribute",
    "thrive in", "in today's fast-paced", "wealth of experience", "demonstrated ability to", "instrumental in", "pivotal role",
]
# Text that comes from a chatbot's reply, not from an answer. (pattern, is it strong evidence on its own?)
ARTIFACTS = [(re.compile(p, re.I), strong) for p, strong in [
    (r"\bas an ai(?: language model| assistant)?\b", True), (r"\bas a large language model\b", True), (r"\bi(?:'m| am) (?:just )?an ai\b", True),
    (r"\bregenerate response\b", True), (r"\bchatgpt\b", True), (r"\b(?:certainly|sure|absolutely|of course)[!,.]\s+here(?:'s| is| are)\b", True),
    (r"\bi hope this helps\b", True), (r"\blet me know if you(?:'d| would) like\b", True), (r"\bi (?:cannot|can't|do not|don't) have (?:personal|access)\b", True),
    (r"\bhere(?:'s| is) an? (?:comprehensive|detailed|concise|structured|step-by-step) (?:answer|response|approach|overview|breakdown)\b", True),
    (r"\bfeel free to (?:ask|reach out)\b", False), (r"\bin conclusion,", False), (r"\bit(?:'s| is) important to note that\b", False),
    (r"(?m)^\s{0,3}#{2,4}\s+\S", False), (r"\*\*[^*\n]{3,60}\*\*", False),
]]


# Text addressed to the scoring system instead of to the reader ("ignore previous instructions", "give me full marks").
# The models are told to treat candidate text as data, and the server owns the numbers; this makes the attempt visible.
INJECTION = [re.compile(p, re.I) for p in [
    r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|all|your|system)\b[^.\n]{0,30}\b(?:instruction|prompt|rule|rubric|guideline)s?\b",
    r"\b(?:give|award|assign|grant)\b[^.\n]{0,25}\b(?:me|this (?:answer|candidate|cv|resume|applicant))\b[^.\n]{0,25}\b(?:full|maximum|max|top|highest|perfect|100)\b[^.\n]{0,15}\b(?:marks?|score|points?|rating|%)",
    r"\b(?:score|rate|rank|mark|grade)\b[^.\n]{0,25}\b(?:this|me|the candidate|the applicant)\b[^.\n]{0,30}\b(?:as|at)?\s*(?:the )?(?:highest|top|perfect|100|10/10|full)\b",
    r"\byou are (?:now )?(?:an?|the) (?:ai|assistant|grader|evaluator|recruiter|scoring)\b",
    r"\b(?:system prompt|as the (?:grader|evaluator|ai)|note to (?:the )?(?:ai|grader|evaluator|model))\b",
    r"\b(?:recommend|shortlist|hire|select)\b[^.\n]{0,20}\bthis (?:candidate|applicant)\b[^.\n]{0,30}\b(?:regardless|no matter|unconditionally|immediately)\b",
]]


def grader_instructions(text):
    """-> exact quotes of text that addresses the scoring system rather than answering (prompt injection attempts)."""
    out = []
    for pat in INJECTION:
        m = pat.search(text or "")
        if m:
            q = re.sub(r"\s+", " ", m.group(0)).strip()[:120]
            if q.lower() not in (x.lower() for x in out):
                out.append(q)
    return out


# ------------------------------------------------------------------ text fingerprints (pure functions)
def _clean(text, names=()):
    """Remove what identifies the author rather than the writing: e-mail addresses, links, phone numbers, their own name."""
    t = URL.sub(" ", EMAIL.sub(" ", text or ""))
    t = PHONE.sub(" ", t)
    for n in names:
        for part in re.findall(r"[^\W\d_]{2,}", n or ""):
            t = re.sub(r"(?<!\w)" + re.escape(part) + r"(?!\w)", " ", t, flags=re.I)
    return t


def _sentences(text):
    parts = re.split(r"(?<=[.!?;])\s+|\s*[\n\r•●▪■◦·|]+\s*|\s+[-–—]\s+(?=[A-Z])", text or "")
    return [p.strip(" \t-–—*") for p in parts if p and p.strip(" \t-–—*")]


def _plain(sentence):
    """Lower-case words; anything with a digit becomes '#', so '12%' and '15%' do not hide a copied sentence."""
    return ["#" if any(ch.isdigit() for ch in w) else w.lower().replace("’", "'") for w in WORD.findall(sentence)]


def _masked(sentence):
    """The sentence's shape: numbers -> '#', proper nouns / acronyms / tool names -> '§' (runs collapsed)."""
    out, first = [], True
    for w in WORD.findall(sentence):
        if any(ch.isdigit() for ch in w):
            tok = "#"
        elif (w[0].isupper() and not first) or (len(w) > 1 and w.isupper()):
            tok = "§"
        else:
            tok = w.lower().replace("’", "'")
        first = False
        if tok in ("§", "#") and out and out[-1] == tok:
            continue
        out.append(tok)
    return out


def _grams(tokens, k):
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)} if len(tokens) >= k else set()


class Print:
    """Everything needed to compare one text with others. Built once per text (cached by content)."""
    __slots__ = ("sentences", "verbatim", "template", "shapes", "words", "norm")

    def __init__(self, text, names=(), k=5):
        clean = _clean(text, names)
        self.sentences, self.verbatim, self.template, self.shapes, n = [], set(), set(), {}, 0
        for s in _sentences(clean):
            plain, masked = _plain(s), _masked(s)
            n += len(plain)
            g = _grams(plain, k)
            self.verbatim |= g
            self.template |= _grams(masked, k - 1)
            real = [t for t in masked if t not in ("§", "#")]
            if len(real) >= 6:                       # a sentence shape needs enough ordinary words to mean anything
                self.shapes.setdefault(" ".join(masked), s)
            self.sentences.append((s, g))
        self.words = n
        self.norm = " ".join(w for s, _ in self.sentences for w in _plain(s))


@lru_cache(maxsize=4096)
def _print_cached(digest, text, names, k):
    return Print(text, names, k)


def fingerprint(text, names=(), k=5):
    text = text or ""
    return _print_cached(hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest(), text, tuple(names), k)


def _share(a, b, ignore=frozenset(), floor=30):
    """Share of the smaller text's word sequences that the other text also contains. `floor` stops a tiny text from
    scoring 100% on a couple of shared phrases."""
    a, b = a - ignore, b - ignore
    if not a or not b:
        return 0.0, set()
    both = a & b
    return len(both) / max(min(len(a), len(b)), floor), both


def _passages(fp, shared, other, limit=5):
    """Sentences of `fp` that also appear in the other text, to show the reviewer (longest first)."""
    out = []
    for s, g in fp.sentences:
        if len(g) >= 2 and len(g & shared) / len(g) >= 0.7:
            out.append(s)
    shapes = set(fp.shapes) & set(other.shapes)
    out += [fp.shapes[k] for k in shapes if fp.shapes[k] not in out]
    out.sort(key=len, reverse=True)
    return [re.sub(r"\s+", " ", s)[:280] for s in out[:limit]]


def stock_phrases(text):
    low = re.sub(r"\s+", " ", (text or "").lower())
    found = [p for p in STOCK if p in low]
    n = len(WORD.findall(low)) or 1
    return {"count": len(found), "per_100_words": round(100 * len(found) / n, 2), "examples": found[:8]}


def chatbot_artifacts(text):
    """-> [{'quote', 'strong'}]: exact text from the answer, so the reviewer can find it."""
    out, seen = [], set()
    for pat, strong in ARTIFACTS:
        m = pat.search(text or "")
        if m:
            q = re.sub(r"\s+", " ", m.group(0)).strip()[:80]
            if q.lower() not in seen:
                seen.add(q.lower())
                out.append({"quote": q, "strong": strong})
    return out


def compare_cvs(a, b, ignore=frozenset(), same_file=False):
    """a, b: Print. -> {'level', 'verbatim', 'template', 'shared_sentences', 'passages', 'same_file'}"""
    v, shared = _share(a.verbatim, b.verbatim, ignore, floor=40)
    t, _ = _share(a.template, b.template, ignore and {x for x in ignore}, floor=40)
    shapes = len(set(a.shapes) & set(b.shapes))
    if same_file or v >= CV_HIGH:
        level = "high"
    elif v >= CV_MEDIUM or (t >= TPL_MEDIUM and shapes >= TPL_MIN_SENTENCES):
        level = "medium"
    elif v >= CV_LOW or (t >= TPL_LOW and shapes >= 2):
        level = "low"
    else:
        level = "none"
    return {"level": level, "verbatim": round(v * 100, 1), "template": round(t * 100, 1), "shared_sentences": shapes,
            "passages": _passages(a, shared, b) if level != "none" else [], "same_file": bool(same_file)}


def compare_answers(a_text, b_text, ignore=frozenset()):
    """-> {'level', 'overlap', 'identical', 'passages'} for two answers (any two questions)."""
    a, b = fingerprint(a_text, (), 4), fingerprint(b_text, (), 4)
    identical = bool(a.norm) and a.norm == b.norm and a.words >= 8
    if not identical and min(a.words, b.words) < ANS_MIN_WORDS:
        return {"level": "none", "overlap": 0.0, "identical": False, "passages": []}
    c, shared = _share(a.verbatim, b.verbatim, ignore, floor=15)
    level = "high" if identical or c >= ANS_HIGH else "medium" if c >= ANS_MEDIUM else "low" if c >= ANS_LOW else "none"
    return {"level": level, "overlap": 100.0 if identical else round(c * 100, 1), "identical": identical,
            "passages": ([re.sub(r"\s+", " ", a_text.strip())[:280]] if identical else _passages(a, shared, b, 3)) if level != "none" else []}


def typing_speed(n_words, started_at, submitted_at):
    """Words per minute over the whole attempt, or None when it cannot be worked out."""
    try:
        mins = (datetime.fromisoformat(submitted_at) - datetime.fromisoformat(started_at)).total_seconds() / 60
    except Exception:
        return None
    if mins <= 0:
        return None
    return {"words": n_words, "minutes": round(mins, 1), "wpm": round(n_words / mins)}


def groups(pairs):
    """Union-find over (a, b) pairs -> list of sets with 2+ members: who shares text with whom."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in pairs:
        parent[find(a)] = find(b)
    out = {}
    for x in list(parent):
        out.setdefault(find(x), set()).add(x)
    return [g for g in out.values() if len(g) > 1]


# ------------------------------------------------------------------ database side
def _job_ignore(job_row, k):
    """Word sequences of the job advertisement: sharing these with another applicant is not a finding."""
    from .similarity import job_text
    from .pipeline import job_dict
    fp = fingerprint(job_text(job_dict(job_row)), (), k)
    return frozenset(fp.verbatim | fp.template)


def _save(c, app_id, kind, level, score, detail):
    """Store the result. A reviewer's verdict is kept while the evidence is unchanged and cleared when it changes."""
    ev = hashlib.sha256(jd([level, sorted((m["application_id"], m.get("level")) for m in detail.get("matches", [])),
                            sorted(s["code"] for s in detail.get("signals", []))]).encode()).hexdigest()[:16]
    old = c.db.one("SELECT id, level, evidence_hash FROM originality_checks WHERE application_id=? AND kind=?", (app_id, kind))
    t = now()
    if old:
        if old["evidence_hash"] == ev:
            c.db.execute("UPDATE originality_checks SET score=?, detail=?, computed_at=? WHERE id=?", (score, jd(detail), t, old["id"]))
        else:
            c.db.execute("""UPDATE originality_checks SET level=?, score=?, detail=?, evidence_hash=?, computed_at=?, verdict=NULL, verdict_note=NULL,
                            verdict_by=NULL, verdict_at=NULL WHERE id=?""", (level, score, jd(detail), ev, t, old["id"]))
    else:
        c.db.execute("INSERT INTO originality_checks (id,application_id,kind,level,score,detail,evidence_hash,computed_at) VALUES (?,?,?,?,?,?,?,?)",
                     (uid(), app_id, kind, level, score, jd(detail), ev, t))
    if level in FLAGGED and (not old or RANK[old["level"]] < RANK[level]):
        from .pipeline import log
        log(c, "originality.flagged", "application", app_id, {"kind": kind, "level": level, "note": f"{KIND_LABEL[kind]} similarity: {level}"})
    return level


KIND_LABEL = {"cv": "CV", "answers": "answer"}


def _contact(extraction, account_email=None):
    """E-mail addresses and phone number (digits only) that identify the person behind a CV."""
    p = jl(extraction, {}) or {}
    emails = {e.strip().lower() for e in (p.get("email"), account_email) if e and "@invalid.local" not in e}
    phone = re.sub(r"\D", "", p.get("phone") or "")[-10:]
    name = " ".join(sorted(re.findall(r"[^\W\d_]{2,}", (p.get("full_name") or "").lower())))
    return emails, (phone if len(phone) >= 8 else ""), name


def same_person(a, b):
    """-> why two CVs look like one person's (shared e-mail, phone, or the same name), or None."""
    (ea, pa, na), (eb, pb, nb) = a, b
    if ea & eb:
        return "the same e-mail address"
    if pa and pa == pb:
        return "the same phone number"
    if na and na == nb and len(na.split()) >= 2:
        return "the same name"
    return None


def check_cv(c, app_id, propagate=True):
    """Compare this application's CV with the CVs of other candidates who applied to the same organisation."""
    a = c.db.one("""SELECT a.id, a.candidate_id, a.cv_id, a.job_id, j.organization_id AS org, ca.full_name, ca.email AS account_email,
                    v.extracted_text, v.sha256, v.extraction
                    FROM applications a JOIN jobs j ON j.id=a.job_id JOIN candidates ca ON ca.id=a.candidate_id
                    LEFT JOIN cvs v ON v.id=a.cv_id WHERE a.id=?""", (app_id,))
    if not a:
        return None
    if not a["extracted_text"]:
        return _save(c, app_id, "cv", "none", 0, {"version": VERSION, "matches": [], "signals": [], "compared": 0,
                                                  "note": "No CV text is stored for this application, so nothing was compared."})
    job = c.db.one("SELECT * FROM jobs WHERE id=?", (a["job_id"],))
    ignore = _job_ignore(job, 5) | _job_ignore(job, 4)
    mine = fingerprint(a["extracted_text"], (a["full_name"],))
    me = _contact(a["extraction"], a["account_email"])
    others = c.db.all("""SELECT b.id, b.candidate_id, b.job_id, ca.full_name, ca.email AS account_email, v.id AS cv_id, v.extracted_text, v.sha256, v.extraction
                         FROM applications b JOIN jobs j ON j.id=b.job_id JOIN candidates ca ON ca.id=b.candidate_id JOIN cvs v ON v.id=b.cv_id
                         WHERE j.organization_id=? AND b.candidate_id != ? AND v.extracted_text IS NOT NULL
                         ORDER BY b.created_at DESC LIMIT ?""", (a["org"], a["candidate_id"], POOL_LIMIT))
    best = {}                                     # one entry per other candidate (their closest CV)
    for o in others:
        r = compare_cvs(mine, fingerprint(o["extracted_text"], (o["full_name"],)), ignore, same_file=o["sha256"] == a["sha256"])
        # a second account of the same person: the same contact details on both CVs (a shared name alone needs similar text too)
        why = same_person(me, _contact(o["extraction"], o["account_email"]))
        if why == "the same name" and r["level"] not in FLAGGED:
            why = None
        if why:
            r = {**r, "level": "high" if o["job_id"] == a["job_id"] else max(r["level"], "medium", key=RANK.get), "same_person": why}
        if r["level"] == "none":
            continue
        cur = best.get(o["candidate_id"])
        if not cur or (RANK[r["level"]], r["verbatim"], o["job_id"] == a["job_id"]) > (RANK[cur["level"]], cur["verbatim"], cur["same_job"]):
            best[o["candidate_id"]] = {**r, "application_id": o["id"], "same_job": o["job_id"] == a["job_id"]}
    matches = sorted(best.values(), key=lambda m: (-RANK[m["level"]], -m["verbatim"], -m["template"]))[:12]
    flagged = [m for m in matches if m["level"] in FLAGGED]
    level = max((m["level"] for m in matches), key=RANK.get, default="none")
    stock = stock_phrases(a["extracted_text"])
    signals = []
    for m in matches:
        if m.get("same_person"):
            signals.append({"code": "same_person", "text": ("A second application for this opening that appears to come from the same person "
                                                             if m["same_job"] else "Another applicant record that appears to be the same person ")
                                                            + f"under a different account: both CVs carry {m['same_person']}."})
            break
    if any(m["same_file"] for m in matches):
        signals.append({"code": "same_file", "text": "The identical file was uploaded from another candidate's account."})
    if any(m["verbatim"] >= CV_MEDIUM * 100 for m in flagged):
        signals.append({"code": "shared_text", "text": "Passages of this CV appear word for word in another candidate's CV."})
    if any(m["verbatim"] < CV_MEDIUM * 100 and not m.get("same_person") for m in flagged):
        signals.append({"code": "shared_template", "text": "This CV follows the same sentence-by-sentence template as another candidate's CV, "
                                                           "with different names, tools and numbers filled in."})
    if len(flagged) >= 2:
        signals.append({"code": "group", "text": f"{len(flagged) + 1} applicants share this CV text or template."})
    inj = grader_instructions(a["extracted_text"])
    if inj:
        signals.append({"code": "instructions_to_ai", "text": "The CV contains text addressed to an automated screener rather than to a reader: “"
                                                              + inj[0] + "”. It had no effect on the score; a person should read the CV."})
        if RANK[level] < RANK["medium"]:
            level = "medium"
    if stock["count"] >= 5:
        signals.append({"code": "stock_phrasing", "text": f"{stock['count']} stock résumé phrases (for example “{stock['examples'][0]}”). "
                                                          "Common in generated CVs and in many written by people: context only."})
    score = max((max(m["verbatim"], m["template"] if m["level"] in FLAGGED else 0) for m in matches), default=0)
    lvl = _save(c, app_id, "cv", level, score, {"version": VERSION, "matches": matches, "signals": signals, "stock": stock,
                                                "compared": len({o["candidate_id"] for o in others}), "words": mine.words})
    if propagate:                                 # the other side of each match is updated too, so both applications show it
        for m in flagged:
            check_cv(c, m["application_id"], propagate=False)
    return lvl


def _submission(c, app_id):
    """The latest submitted attempt of an application: (assessment row, task, answers) or None."""
    s = c.db.one("""SELECT s.*, r.answers, r.submitted_at AS resp_submitted FROM assessments s JOIN assessment_responses r ON r.assessment_id=s.id
                    WHERE s.application_id=? AND r.submitted_at IS NOT NULL ORDER BY s.attempt DESC LIMIT 1""", (app_id,))
    if not s:
        return None
    return s, jl(s["task"]) or {"questions": []}, jl(s["answers"], {}) or {}


def _prompt_ignore(task):
    out = set(fingerprint(task.get("scenario") or "", (), 4).verbatim)
    for q in task.get("questions", []):
        out |= fingerprint(q.get("prompt") or "", (), 4).verbatim
    return frozenset(out)


def _meaning(c, a_text, b_text):
    enc = getattr(c, "encoder", None)
    if enc is None:
        return None
    try:
        va, vb = _embed(enc, a_text), _embed(enc, b_text)
    except Exception:
        return None
    return sum(x * y for x, y in zip(va, vb))


_EMB = {}


def _embed(enc, text):
    key = (getattr(enc, "label", ""), hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest())
    if key not in _EMB:
        if len(_EMB) > 5000:
            _EMB.clear()
        _EMB[key] = enc.encode([text[:4000]])[0]
    return _EMB[key]


def check_answers(c, app_id, propagate=True):
    """Compare this application's submitted answers with the answers other candidates submitted for the same opening."""
    a = c.db.one("SELECT a.id, a.candidate_id, a.job_id FROM applications a WHERE a.id=?", (app_id,))
    sub = _submission(c, app_id) if a else None
    if not sub:
        return None
    s, task, answers = sub
    prompts = {q["id"]: q["prompt"] for q in task.get("questions", [])}
    ignore = _prompt_ignore(task)
    pool = []
    for o in c.db.all("SELECT b.id FROM applications b WHERE b.job_id=? AND b.candidate_id != ? ORDER BY b.created_at DESC LIMIT ?",
                      (a["job_id"], a["candidate_id"], POOL_LIMIT)):
        other = _submission(c, o["id"])
        if other:
            pool.append((o["id"], other[1], other[2]))
    per_q, by_app, signals = [], {}, []
    total_words = 0
    for qid, text in answers.items():
        text = text or ""
        n = len(WORD.findall(text))
        total_words += n
        row = {"question_id": qid, "words": n, "matches": [], "artifacts": chatbot_artifacts(text), "instructions": grader_instructions(text)}
        for oid, otask, oans in pool:
            oprompts = {q["id"]: q["prompt"] for q in otask.get("questions", [])}
            oignore = ignore | _prompt_ignore(otask)
            for oq, otext in oans.items():
                r = compare_answers(text, otext or "", oignore)
                same_q = prompts.get(qid) is not None and prompts.get(qid) == oprompts.get(oq)
                sem = None
                if r["level"] in ("none", "low") and same_q and min(n, len(WORD.findall(otext or ""))) >= ANS_MIN_WORDS:
                    cos = _meaning(c, text, otext)
                    if cos is not None and cos >= MEANING_MIN:
                        sem = round(cos * 100, 1)
                if r["level"] == "none" and sem is None:
                    continue
                m = {**r, "application_id": oid, "other_question_id": oq, "same_question": same_q}
                if sem is not None:
                    m["meaning"] = sem
                row["matches"].append(m)
                cur = by_app.get(oid)
                if not cur or RANK[r["level"]] > RANK[cur["level"]] or (r["level"] == cur["level"] and r["overlap"] > cur["overlap"]):
                    by_app[oid] = {"application_id": oid, "level": r["level"], "overlap": r["overlap"], "identical": r["identical"]}
        row["matches"].sort(key=lambda m: (-RANK[m["level"]], -m["overlap"]))
        row["matches"] = row["matches"][:6]
        row["level"] = max((m["level"] for m in row["matches"]), key=RANK.get, default="none")
        if (any(x["strong"] for x in row["artifacts"]) or row["instructions"]) and RANK[row["level"]] < RANK["medium"]:
            row["level"] = "medium"
        per_q.append(row)
    qnum = {q["id"]: i for i, q in enumerate(task.get("questions", []), 1)}
    for r in per_q:      # how many OTHER candidates gave this same (or near-identical) answer to this question
        r["same_answer_count"] = len({m["application_id"] for m in r["matches"] if m["level"] in FLAGGED})
    crowd = max(per_q, key=lambda r: r["same_answer_count"], default=None)
    same_max = (crowd["same_answer_count"] + 1) if crowd and crowd["same_answer_count"] else 1
    level = max((r["level"] for r in per_q), key=RANK.get, default="none")
    if same_max >= 3:
        level = "high"
    matches = sorted(by_app.values(), key=lambda m: (-RANK[m["level"]], -m["overlap"]))[:12]
    flagged = [m for m in matches if m["level"] in FLAGGED]
    if same_max >= 3:
        signals.append({"code": "three_or_more", "text": f"{same_max} candidates (this one included) gave the same or near-identical answer to question "
                                                          f"{qnum.get(crowd['question_id'], '?')}. Independent people rarely write the same answer; it usually means a "
                                                          "shared source such as one chatbot reply or a leaked answer sheet."})
    if any(m["identical"] for m in flagged):
        signals.append({"code": "identical_answer", "text": "At least one answer is identical to another candidate's answer."})
    elif flagged:
        signals.append({"code": "shared_answer_text", "text": "Passages of these answers appear word for word in another candidate's answers."})
    if len(flagged) >= 2:
        signals.append({"code": "group", "text": f"{len(flagged) + 1} candidates submitted overlapping answers."})
    arts = [x for r in per_q for x in r["artifacts"]]
    if any(x["strong"] for x in arts):
        signals.append({"code": "chatbot_text", "text": "An answer contains text that normally comes from a pasted chatbot reply: “" +
                                                        next(x["quote"] for x in arts if x["strong"]) + "”."})
    inj = [x for r in per_q for x in r["instructions"]]
    if inj:
        signals.append({"code": "instructions_to_ai", "text": "An answer addresses the scoring system instead of the question: “" + inj[0] +
                                                              "”. Scores are set by the server and candidate text is treated as data, so read "
                                                              "this answer yourself."})
    speed = typing_speed(total_words, s["started_at"], s["submitted_at"]) if s["started_at"] and s["submitted_at"] else None
    if speed and speed["words"] >= SPEED_MIN_WORDS and speed["wpm"] >= SPEED_WPM:
        signals.append({"code": "faster_than_typing", "text": f"{speed['words']} words were submitted {speed['minutes']} minutes after starting "
                                                               f"({speed['wpm']} words a minute): more than can be typed, so text was pasted. "
                                                               "Pasting from one's own notes is not misconduct; read it with the other evidence."})
        if level == "none":
            level = "low"
    if any(m.get("meaning") for r in per_q for m in r["matches"]):
        signals.append({"code": "similar_meaning", "text": "An answer says the same as another candidate's answer in different words "
                                                           "(embedding similarity). Two good answers are often close in meaning: context only."})
    score = max((m["overlap"] for m in matches), default=0)
    lvl = _save(c, app_id, "answers", level, score, {"version": VERSION, "assessment_id": s["id"], "attempt": s["attempt"], "matches": matches,
                                                     "per_question": per_q, "signals": signals, "speed": speed, "compared": len(pool), "same_answer_max": same_max})
    if propagate:
        for m in flagged:
            check_answers(c, m["application_id"], propagate=False)
    return lvl


# ------------------------------------------------------------------ views
def _who(c, app_ids, org=None):
    """application id -> {name, job title, job id}; only applications of `org` (None = any) and only ones that still exist."""
    if not app_ids:
        return {}
    ids = list(dict.fromkeys(app_ids))
    q = f"""SELECT a.id, ca.full_name, j.title, j.id AS job_id FROM applications a JOIN candidates ca ON ca.id=a.candidate_id
            JOIN jobs j ON j.id=a.job_id WHERE a.id IN ({','.join('?' * len(ids))})"""
    args = ids
    if org:
        q += " AND j.organization_id=?"
        args = ids + [org]
    return {r["id"]: {"application_id": r["id"], "candidate": r["full_name"], "job_title": r["title"], "job_id": r["job_id"]} for r in c.db.all(q, args)}


def view(c, app_id, org=None):
    """What a recruiter sees for one application: {'cv': {...} | None, 'answers': {...} | None}. Names are resolved now, never
    stored, so a deleted candidate disappears from every other record's matches."""
    out = {"cv": None, "answers": None}
    for row in c.db.all("SELECT * FROM originality_checks WHERE application_id=?", (app_id,)):
        d = jl(row["detail"], {}) or {}
        ids = [m["application_id"] for m in d.get("matches", [])] + [m["application_id"] for q in d.get("per_question", []) for m in q["matches"]]
        who = _who(c, ids, org)
        d["matches"] = [{**m, **who[m["application_id"]]} for m in d.get("matches", []) if m["application_id"] in who]
        for q in d.get("per_question", []):
            q["matches"] = [{**m, **who[m["application_id"]]} for m in q["matches"] if m["application_id"] in who]
        level = row["level"]
        if level in FLAGGED and not d["matches"] and not any(s["code"] in ("chatbot_text", "instructions_to_ai") for s in d.get("signals", [])):
            level = "none"                      # every matching record has since been deleted
        out[row["kind"]] = {**d, "level": level, "score": row["score"], "computed_at": row["computed_at"],
                            "verdict": row["verdict"], "verdict_note": row["verdict_note"], "verdict_at": row["verdict_at"]}
    return out


def job_overview(c, job_id, org=None):
    """Groups of applicants to one opening who share CV text / a template, or who submitted overlapping answers."""
    rows = c.db.all("""SELECT o.application_id, o.kind, o.level, o.score, o.detail, o.verdict FROM originality_checks o
                       JOIN applications a ON a.id=o.application_id WHERE a.job_id=?""", (job_id,))
    mine = {r["application_id"] for r in rows}
    out = {"checked": {"cv": 0, "answers": 0}, "flagged": {"cv": 0, "answers": 0}, "groups": []}
    for kind in ("cv", "answers"):
        pairs, strength, sample, solo = [], {}, {}, []
        for r in (x for x in rows if x["kind"] == kind):
            out["checked"][kind] += 1
            d = jl(r["detail"], {}) or {}
            hits = [m for m in d.get("matches", []) if m["level"] in FLAGGED]
            if r["level"] in FLAGGED and r["verdict"] != "cleared":
                out["flagged"][kind] += 1
                if not hits:
                    solo.append((r, d))
            for m in hits:
                pairs.append((r["application_id"], m["application_id"]))
                key = frozenset((r["application_id"], m["application_id"]))
                val = m.get("overlap", max(m.get("verbatim", 0), m.get("template", 0)))
                if val >= strength.get(key, (-1,))[0]:
                    strength[key] = (val, m["level"])
                p = (m.get("passages") or [None])[0] or next((x["passages"][0] for q in d.get("per_question", []) for x in q["matches"]
                                                              if x["application_id"] == m["application_id"] and x.get("passages")), None)
                if p:
                    sample.setdefault(key, p)
        for g in groups(pairs):
            who = _who(c, list(g), org)
            members = [who[i] for i in g if i in who]
            if len(members) < 2:
                continue
            keys = [k for k in strength if k <= g]
            top = max(keys, key=lambda k: strength[k][0])
            out["groups"].append({"kind": kind, "level": max((strength[k][1] for k in keys), key=RANK.get), "score": strength[top][0],
                                  "three_or_more": len(members) >= 3,
                                  "members": sorted(members, key=lambda m: (m["job_id"] != job_id, m["candidate"])),
                                  "other_openings": any(m["job_id"] != job_id for m in members),
                                  "sample": next((sample[k] for k in sorted(keys, key=lambda k: -strength[k][0]) if k in sample), None)})
        for r, d in solo:
            who = _who(c, [r["application_id"]], org)
            if who:
                out["groups"].append({"kind": kind, "level": r["level"], "score": r["score"], "members": list(who.values()), "other_openings": False,
                                      "sample": next((s["text"] for s in d.get("signals", [])), None)})
    out["groups"].sort(key=lambda g: (-RANK[g["level"]], -len(g["members"]), -g["score"]))
    out["applications"] = len(mine)
    return out


def summary_levels(c, app_ids):
    """application id -> {'cv': level, 'answers': level, 'open': bool} for list screens (a cleared flag is not 'open')."""
    if not app_ids:
        return {}
    out = {}
    for r in c.db.all(f"SELECT application_id, kind, level, verdict FROM originality_checks WHERE application_id IN ({','.join('?' * len(app_ids))})", list(app_ids)):
        d = out.setdefault(r["application_id"], {"cv": None, "answers": None, "open": False})
        d[r["kind"]] = r["level"]
        if r["level"] in FLAGGED and r["verdict"] != "cleared":
            d["open"] = True
    return out
