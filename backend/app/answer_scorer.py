"""Transparent, rule-based scoring of free-text assessment answers (the local engine's evaluator).

How a question is scored (all numbers are reproducible; nothing is hidden):
  coverage   share of the question's `expected_points` the answer addresses. A point needs 2 of its cue terms for full credit
             (1 cue = half credit). Cues are matched as whole words/prefixes, so "prioritise" matches "prioritisation".
  depth      length (full marks ~90 words) and specificity (numbers, named tools, concrete-example phrases).
  structure  several sentences, sequencing words (first/then/because), paragraphs or list markers.
  clarity    sentence length in a readable range, capital letters, common misspellings.
  score      max_points x coverage x (0.6 + 0.4 x quality)  with quality = 0.5 depth + 0.25 structure + 0.25 clarity.
             An answer that covers nothing scores 0 however long or well written it is.
Synonyms: a point the answer makes in other words still counts: each point can earn one extra cue through the concept
             table below ("double-check" for "validate", "line manager" for "stakeholder"...).
Guards: answers that are a keyword list, are extremely repetitive, mostly copy the question, are non-answers ("I don't
know") or are not meaningful text (keyboard mashing) have coverage reduced or set to zero.

This engine measures coverage of expected topics; it does not judge factual correctness. With an AI model configured,
each answer is also scored by the model, which checks correctness, and this rubric becomes the cross-check.
"""
import re
from . import skills_data as sd
from .cv_parser import SPELLING

STOP = set("""a an the and or but if then else of to in on at for with without by from as is are was were be been being it its this that these those
i me my we our you your they their he she his her them us do does did done have has had having can could should would will may might must
not no yes so than too very just also about into over under up down out off again more most some any each other such own same only
what which who whom when where why how all both few many much one two three there here""".split())
SEQ = {"first", "second", "third", "then", "next", "finally", "after", "before", "because", "therefore", "however", "so", "also", "lastly", "afterwards", "meanwhile", "since", "while", "once"}
EXAMPLE = ("for example", "for instance", "e.g.", "such as", "in my previous", "at my", "i built", "i used", "i worked", "i led", "i wrote", "when i")


CONCEPTS = [s.split("|") for s in """validate|verify|check|double-check|double check|sanity check|cross-check|reconcile|confirm|spot-check
stakeholder|manager|line manager|client|business owner|leadership|team lead|product owner|decision maker|sponsor
measure|track|monitor|metric|kpi|analytics|benchmark
clean|tidy|standardise|standardize|normalise|normalize|dedupe|deduplicate|fix the data
duplicate|dedupe|deduplicate|repeated row|distinct
missing|null|blank|empty value|nan|incomplete
present|presentation|communicate|explain|walk through|share findings|storytelling
dashboard|visualisation|visualization|chart|graph|report
prioritise|prioritize|rank|triage|most important first|order of importance
experiment|a/b|ab test|pilot|trial|split test
automate|script|scheduled|pipeline|cron|workflow automation
document|documentation|write up|write-up|runbook|readme|notes
feedback|survey|interview|user research|input from
risk|concern|threat|downside|trade-off|tradeoff
cache|caching|memoize|memoise|cdn|redis
scale|scaling|horizontal|load balancer|replica|throughput|autoscal
secure|security|authentication|authorisation|authorization|encrypt|access control|least privilege
error|exception|failure|edge case|fallback|retry
budget|cost|spend|roi|return on investment
goal|objective|target|aim|outcome|success criteria
audience|persona|customer segment|target market|end user
deadline|timeline|milestone|roadmap|schedule
root cause|investigate|diagnose|debug|troubleshoot|five whys|5 whys
customer|client|user|buyer|consumer
revenue|sales|income|turnover
improve|optimise|optimize|increase|boost|enhance
collaborate|work with|partner with|coordinate|align with
deploy|release|ship|roll out|rollout|go live
review|code review|pull request|peer review|feedback session""".splitlines()]
SYN = {}
for _g in CONCEPTS:
    for _w in _g:
        SYN.setdefault(_w, set()).update(x for x in _g if x != _w)
NON_ANSWERS = ("i don't know", "i dont know", "i do not know", "no idea", "not sure", "idk", "n/a", "lorem ipsum", "asdf", "qwerty",
               "skip this", "pass on this", "no answer", "nothing to say", "test test", "blah blah")
BAD_BIGRAMS = set("bq bx cj cx dx fq fx fz gq gx hx jb jc jd jf jg jh jk jl jm jn jp jr jt jv jw jx jz kq kx kz mx pq px pz qb qc qd qe "
                  "qf qg qh qj qk qm qn qo qp qq qr qs qt qv qw qx qy qz sx tq vb vc vf vg vh vj vk vm vn vp vq vt vw vx wj wq wx xb xd xf "
                  "xg xj xk xm xn xq xr xs xw xz yq yy zb zc zf zg zj zk zq zx sj hw".split())


def implausible_word(w):
    """A word that cannot be English (or a usual transliteration): no vowel, 6+ consonants in a row, or a letter pair that
    does not occur in words. Used only to spot keyboard mashing such as 'xhwhiw sjdniw'."""
    if len(w) < 4 or not w.isalpha() or sd.canonical(w):
        return False
    if not re.search(r"[aeiouy]", w) or re.search(r"[^aeiouy]{6,}", w):
        return True
    return any(w[i:i + 2] in BAD_BIGRAMS for i in range(len(w) - 1))


def non_answer_reason(text):
    """-> None, or why this text is not a real answer (it is then scored 0 and flagged for the reviewer)."""
    norm = re.sub(r"\s+", " ", (text or "").lower()).strip(" .!")
    toks = [t for t in words(text or "") if t.isalpha() and len(t) >= 3 and t not in STOP]
    if toks and sum(1 for t in toks if implausible_word(t)) / len(toks) >= 0.5:
        return "the answer does not read as meaningful text"
    if len(toks) <= 12 and any(p in norm for p in NON_ANSWERS):
        return "the answer says the candidate does not know or skips the question"
    return None


def words(text):
    return re.findall(r"[a-z0-9][a-z0-9'+#/.-]*[a-z0-9+#]|[a-z0-9]", text.lower())


def stem(w):
    w = w.lower().strip(".-'")
    for suf in ("ization", "isation", "ations", "ation", "ingly", "edly", "ings", "ing", "ies", "es", "ed", "s", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def content_words(text):
    return [w for w in words(text) if w not in STOP and len(w) > 2]


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


class Answer:
    def __init__(self, text):
        self.raw = text or ""
        self.norm = re.sub(r"\s+", " ", self.raw).strip().lower()
        self.tokens = words(self.raw)
        self.stems = {stem(t) for t in self.tokens}
        self.sentences = split_sentences(self.raw)

    def has_cue(self, cue):
        cue = cue.lower().strip()
        if not cue:
            return False
        if cue == "i":
            return "i" in self.tokens
        if cue.endswith(" ") or cue.startswith(" ") or re.search(r"[^a-z]", cue):
            c = cue.strip()
            pre = r"(?<![a-z0-9])" if c[:1].isalnum() else ""
            post = r"(?![a-z0-9])" if (len(c) <= 3 and c[-1:].isalnum()) else ""
            return bool(re.search(pre + re.escape(c) + post, self.norm))
        s = stem(cue)
        if len(s) < 3:
            return cue in self.tokens
        return any(t.startswith(s) or stem(t) == s for t in self.tokens) if len(s) >= 5 else any(stem(t) == s for t in self.tokens)

    def synonym_for(self, cue):
        """-> the synonym of `cue` found in the answer, or None."""
        for syn in SYN.get(cue.lower().strip(), ()):
            if self.has_cue(syn):
                return syn
        return None

    def sentence_with(self, cues):
        for s in self.sentences:
            a = Answer(s)
            if any(a.has_cue(c) for c in cues):
                return s
        return None


# ------------------------------------------------------------------ expected points
def points_for(q):
    """Use the question's own expected_points; otherwise derive them from the private rubric / prompt."""
    pts = [p for p in (q.get("expected_points") or []) if p.get("cues")]
    if pts:
        return pts
    rubric = q.get("rubric", "")
    segs = [s.strip() for s in re.split(r";|\n|\d\)|\.\s", rubric) if len(s.strip()) > 12]
    out = []
    for s in segs[:6]:
        cues = list(dict.fromkeys(content_words(s)))[:10]
        if len(cues) >= 2:
            out.append({"point": s[:120], "cues": cues})
    if out:
        return out
    cues = list(dict.fromkeys(content_words(q.get("prompt", "") + " " + rubric)))[:12]
    return [{"point": "Addresses the question", "cues": cues or ["answer"]}]


# ------------------------------------------------------------------ pieces of the score
def spelling_issues(text):
    out = []
    for w, fix in SPELLING.items():
        m = re.search(rf"\b{w}\b", text, re.I)
        if m:
            out.append({"text": m.group(0), "fix": fix})
    for m in re.finditer(r"\b(\w{3,})\s+\1\b", text, re.I):
        out.append({"text": m.group(0)[:160], "fix": m.group(1)})
    return out


def _depth(a, n_words):
    length = min(1.0, n_words / 90)
    nums = len(re.findall(r"\b\d+(?:\.\d+)?%?", a.raw))
    tools = len(sd.find_skills(a.raw))
    ex = sum(1 for e in EXAMPLE if e in a.norm)
    spec = min(1.0, (min(nums, 2) + min(tools, 3) + min(ex, 2)) / 4)
    return round(0.6 * length + 0.4 * spec, 3)


def _structure(a):
    seq = sum(1 for t in a.tokens if t in SEQ)
    lists = 1 if re.search(r"(?m)^\s*(?:[-•*]|\d+[.)])\s+", a.raw) or "\n\n" in a.raw.strip() else 0
    return round(0.4 * min(1, len(a.sentences) / 4) + 0.4 * min(1, seq / 3) + 0.2 * lists, 3)


def _clarity(a, n_words):
    if not a.sentences:
        return 0.0
    avg = n_words / len(a.sentences)
    rng = 1.0 if 8 <= avg <= 32 else max(0.0, 1 - (8 - avg) / 8) if avg < 8 else max(0.0, 1 - (avg - 32) / 40)
    caps = sum(1 for s in a.sentences if s[:1].isupper()) / len(a.sentences)
    spell = min(0.45, 0.15 * len(spelling_issues(a.raw)))
    return round(max(0.0, 0.6 * rng + 0.4 * caps - spell), 3)


def _is_copy(a, prompt):
    pt = words(prompt)
    tri = {tuple(pt[i:i + 3]) for i in range(len(pt) - 2)}
    at = words(a.raw)
    atri = [tuple(at[i:i + 3]) for i in range(len(at) - 2)]
    return bool(atri) and sum(1 for x in atri if x in tri) / len(atri) > 0.5


def score_question(q, text):
    a = Answer(text)
    n = len(a.tokens)
    points = points_for(q)
    notes, hits_detail = [], []
    for p in points:
        hit_cues = [c for c in p["cues"] if a.has_cue(c)]
        need = 2 if len(p["cues"]) >= 4 else 1
        if len(hit_cues) < need:          # the same idea in other words: at most one extra cue per point
            for c in p["cues"]:
                syn = c not in hit_cues and a.synonym_for(c)
                if syn and syn not in p["cues"]:
                    hit_cues.append(syn)
                    break
        hits_detail.append({"point": p["point"], "cues": p["cues"], "hit": hit_cues, "credit": min(1.0, len(hit_cues) / need)})
    coverage = sum(h["credit"] for h in hits_detail) / len(hits_detail)
    strict = sum(1 for h in hits_detail if h["credit"] >= 1.0) / len(hits_detail)

    total_hits = sum(len(h["hit"]) for h in hits_detail)
    if n >= 30 and len(set(a.tokens)) / n < 0.45:
        coverage, strict = coverage * 0.5, strict * 0.5
        notes.append("the answer is very repetitive")
    if len(a.sentences) <= 1 and n >= 8 and total_hits / max(n, 1) > (0.3 if n >= 15 else 0.5):
        coverage, strict = coverage * 0.5, strict * 0.5
        notes.append("the answer reads as a list of keywords rather than an explanation")
    if _is_copy(a, q.get("prompt", "")):
        coverage, strict = coverage * 0.1, strict * 0.1
        notes.append("the answer mostly repeats the question")
    why = non_answer_reason(text)
    if why:
        coverage, strict = 0.0, 0.0
        notes.append(why)

    depth, structure, clarity = _depth(a, n), _structure(a), _clarity(a, n)
    quality = 0.5 * depth + 0.25 * structure + 0.25 * clarity
    frac = max(0.0, min(1.0, coverage * (0.6 + 0.4 * quality)))

    qprompt = set(stem(w) for w in content_words(q.get("prompt", "")))
    overlap = len(qprompt & a.stems) / len(qprompt) if qprompt else 0.0
    relevance = min(1.0, 0.7 * coverage + 0.3 * min(1.0, overlap * 1.5))

    evidence = []
    for h in hits_detail:
        if h["hit"]:
            s = a.sentence_with(h["hit"])
            if s and s[:240] not in evidence:
                evidence.append(s[:240])
    covered = [h["point"] for h in hits_detail if h["credit"] >= 1.0]
    partial = [h["point"] for h in hits_detail if 0 < h["credit"] < 1.0]
    missed = [h["point"] for h in hits_detail if h["credit"] == 0]
    depth_word = "detailed" if depth >= 0.7 else "adequate" if depth >= 0.4 else "thin"
    rationale = f"Covered {len(covered)} of {len(hits_detail)} expected points fully" + (f", {len(partial)} partly" if partial else "") + "."
    if missed:
        rationale += " Not addressed: " + "; ".join(missed[:3]) + "."
    rationale += f" Depth {depth_word}."
    if notes:
        rationale += " Note: " + ", ".join(notes) + "."
    return {"frac": frac, "coverage": coverage, "strict": strict, "depth": depth, "structure": structure, "clarity": clarity,
            "relevance": relevance, "evidence": evidence[:4], "rationale": rationale[:500], "covered": covered, "partial": partial,
            "missed": missed, "language": spelling_issues(a.raw)}


def score_answers(task, answers):
    """-> dict shaped like EVAL_SCHEMA (before server-side finalisation)."""
    per, agg, wsum = [], {"relevance": 0, "depth": 0, "strict": 0, "clarity": 0, "structure": 0}, 0.0
    strengths, gaps, lang = [], [], []
    for q in task["questions"]:
        text = (answers.get(q["id"]) or "").strip()
        mp = float(q["max_points"])
        status = answer_status(text)
        if status != "scored":
            r = {"frac": 0.0, "relevance": 0, "depth": 0, "strict": 0, "clarity": 0, "structure": 0, "evidence": [], "covered": [], "missed": [],
                 "language": [], "rationale": STATUS_TEXT[status].format(n=len(words(text)))}
        else:
            r = score_question(q, text)
        per.append({"question_id": q["id"], "score": round(mp * r["frac"], 2), "rationale": r["rationale"], "evidence": r["evidence"],
                    "answer_status": status, "covered": r["covered"][:6], "missed": r["missed"][:6]})
        for k in agg:
            agg[k] += r[k if k != "strict" else "strict"] * mp
        wsum += mp
        strengths += r["covered"]
        gaps += r["missed"]
        lang += r["language"]
    wsum = wsum or 1.0
    crit = {"relevance": agg["relevance"], "depth": agg["depth"], "accuracy": agg["strict"], "communication": agg["clarity"], "structure": agg["structure"]}
    criteria = {k: round(min(100.0, max(0.0, v / wsum * 100)), 1) for k, v in crit.items()}
    got = sum(p["score"] for p in per)
    total = sum(float(q["max_points"]) for q in task["questions"]) or 1.0
    answered = sum(1 for p in per if p["score"] > 0)
    scorable = sum(1 for p in per if p["answer_status"] == "scored")
    blank = sum(1 for p in per if p["answer_status"] == "blank")
    short = sum(1 for p in per if p["answer_status"] == "too_short")
    if scorable == 0:
        summary = (f"No answer could be scored: {blank} blank and {short} too short (under {MIN_WORDS} words). The 0/100 reflects that nothing "
                   "scorable was submitted, not a judgement of the candidate's ability; read the submitted text below.")
    else:
        summary = (f"Automated rule-based scoring: {round(got / total * 100)}/100. {scorable} of {len(per)} answers were long enough to score"
                   + (f" ({blank} blank, {short} too short)" if blank or short else "") +
                   f"; {answered} addressed at least part of what was expected. The score measures coverage of expected topics plus depth, "
                   "structure and clarity; it cannot verify that statements are factually correct, so a person should read the answers before deciding.")
    seen_l, lang_out = set(), []
    for l in lang:
        if l["text"].lower() not in seen_l:
            seen_l.add(l["text"].lower())
            lang_out.append(l)
    answered_frac = answered / len(per) if per else 0
    return {"per_question": per, "criteria": criteria, "strengths": list(dict.fromkeys(strengths))[:6], "gaps": list(dict.fromkeys(gaps))[:6],
            "language_notes": lang_out[:10], "summary": summary[:700], "confidence": round(0.35 + 0.35 * answered_frac, 2),
            "engine": "local-rules-v1"}


MIN_WORDS = 5
STATUS_TEXT = {"blank": "No answer was given.",
               "too_short": "Too short to score ({n} word(s); at least 5 are needed). The text is shown so a person can read it."}


def answer_status(text):
    """blank | too_short | scored. Kept separate from the score so 'no usable answer' is never confused with 'a poor answer'."""
    n = len(words(text or ""))
    return "blank" if n == 0 else "too_short" if n < MIN_WORDS else "scored"
