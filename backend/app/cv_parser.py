"""Rule-based CV parser: plain text -> structured profile (the CV_SCHEMA shape).

Principles
- Only report what the text says. Anything not found is None / empty, never guessed.
- A skill is "demonstrated" only when it appears in work, project or education text with a surrounding sentence
  (that sentence is stored as its `context`); a skill found only in a skills list is "listed".
- Proficiency is always "unknown": a CV rarely proves it and this parser does not pretend to.
- This is pattern matching, not language understanding. Unusual layouts will be parsed less completely, which is why the
  candidate reviews and corrects the profile before applying.
"""
import re
from . import skills_data as sd

MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE = rf"(?:{MON}\.?,?\s+(?:19|20)\d{{2}}|\d{{1,2}}[/.-](?:19|20)\d{{2}}|(?:19|20)\d{{2}}[/-]\d{{1,2}}(?!\d)|(?:19|20)\d{{2}})"
RANGE = re.compile(rf"(?P<s>{DATE})\s*(?:-|–|—|to|until|till)\s*(?P<e>{DATE}|present|current|now|ongoing|till date|date)", re.I)
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}

HEADINGS = {
    "summary": ["summary", "profile", "professional summary", "career summary", "career objective", "objective", "about me", "about"],
    "experience": ["experience", "work experience", "professional experience", "employment", "employment history", "work history",
                   "career history", "internships", "internship experience", "relevant experience", "industry experience"],
    "education": ["education", "academic background", "academic qualifications", "qualifications", "education and training",
                  "educational qualifications", "academics"],
    "skills": ["skills", "technical skills", "key skills", "core skills", "core competencies", "skills and tools", "tools and technologies",
               "technologies", "areas of expertise", "competencies", "skills and abilities", "tools", "technical proficiencies"],
    "projects": ["projects", "academic projects", "personal projects", "key projects", "selected projects", "project experience"],
    "certifications": ["certifications", "certificates", "licenses", "licences", "courses", "training", "certifications and courses",
                       "professional development", "certifications and training"],
    "achievements": ["achievements", "awards", "honors", "honours", "accomplishments", "awards and achievements", "extracurricular",
                     "extracurricular activities", "publications", "awards and honours"],
    "languages": ["languages", "language skills"],
    "other": ["contact", "contact information", "personal details", "references", "interests", "hobbies", "declaration", "links"],
}
HEAD_LOOKUP = {h: sec for sec, hs in HEADINGS.items() for h in hs}

BULLET = re.compile(r"^\s*(?:[•●▪■◦·*\-–—>]|\d{1,2}[.)])\s+")
TITLE_WORDS = set("""analyst engineer developer manager intern internship executive officer consultant specialist associate assistant
coordinator lead director head researcher scientist designer architect administrator teacher lecturer professor tutor accountant
auditor writer editor representative advisor adviser trainee fellow freelancer freelance programmer tester supervisor recruiter
strategist technician clerk secretary president founder owner contributor volunteer apprentice""".split())
COMPANY_HINT = re.compile(r"\b(pvt|ltd|limited|inc|llc|corp|corporation|company|co\.|technologies|solutions|systems|labs|group|"
                          r"analytics|consulting|services|university|institute|foundation|agency|studio|bank|school|college)\b", re.I)
INSTITUTION = re.compile(r"\b(university|college|institute|school|academy|polytechnic|iit|iim|nit|vidyalaya|universiti)\b", re.I)

DEGREES = [  # (regex, normalised full name, case-sensitive?)
    (r"\bPh\.?\s?D\.?\b|\bDoctorate\b|\bDoctor of Philosophy\b", "PhD", False),
    (r"\bMBA\b|\bMaster(?:'s)? of Business Administration\b", "Master of Business Administration (MBA)", False),
    # spelled-out degree names before the abbreviations and the generic "Master's/Bachelor's" fallbacks
    (r"\bMaster(?:'s)? of Science\b", "Master of Science (MSc)", False),
    (r"\bMaster(?:'s)? of Arts\b", "Master of Arts (MA)", False),
    (r"\bMaster(?:'s)? of Commerce\b", "Master of Commerce (MCom)", False),
    (r"\bMaster(?:'s)? of (?:Technology|Engineering)\b", "Master of Technology (MTech)", False),
    (r"\bMaster(?:'s)? of Computer Applications\b", "Master of Computer Applications (MCA)", False),
    (r"\bBachelor(?:'s)? of Arts\b", "Bachelor of Arts (BA)", False),
    (r"\bBachelor(?:'s)? of Science\b", "Bachelor of Science (BSc)", False),
    (r"\bBachelor(?:'s)? of Commerce\b", "Bachelor of Commerce (BCom)", False),
    (r"\bBachelor(?:'s)? of (?:Technology|Engineering)\b", "Bachelor of Technology/Engineering", False),
    (r"\bBachelor(?:'s)? of Computer Applications\b", "Bachelor of Computer Applications (BCA)", False),
    (r"\bBachelor(?:'s)? of Business Administration\b", "Bachelor of Business Administration (BBA)", False),
    (r"\bMCA\b", "Master of Computer Applications (MCA)", True),
    (r"\bM\.?\s?Tech\.?(?=[\s,.(:\-–]|$)", "Master of Technology (MTech)", True),
    (r"\bM\.?\s?Sc\.?(?=[\s,.(:\-–]|$)", "Master of Science (MSc)", True),
    (r"\bM\.?\s?Com\.?(?=[\s,.(:\-–]|$)", "Master of Commerce (MCom)", True),
    (r"\bM\.?\s?A\.?(?=[\s,.(:\-–]|$)", "Master of Arts (MA)", True),
    (r"\bM\.?\s?S\.?(?=\s+(?:in|of)\b)", "Master of Science (MS)", True),
    (r"\bMaster(?:'s)?(?: degree)?(?: of| in)?\b", "Master's degree", False),
    (r"\bB\.?\s?Tech\.?(?=[\s,.(:\-–]|$)|\bB\.?\s?E\.?(?=\s+(?:in|\()|\s*[,(])", "Bachelor of Technology/Engineering", True),
    (r"\bBCA\b", "Bachelor of Computer Applications (BCA)", True),
    (r"\bBBA\b", "Bachelor of Business Administration (BBA)", True),
    (r"\bB\.?\s?Sc\.?(?=[\s,.(:\-–]|$)", "Bachelor of Science (BSc)", True),
    (r"\bB\.?\s?Com\.?(?=[\s,.(:\-–]|$)", "Bachelor of Commerce (BCom)", True),
    (r"\bB\.?\s?Ed\.?(?=[\s,.(:\-–]|$)", "Bachelor of Education (BEd)", True),
    (r"\bB\.?\s?A\.?(?=[\s,.(:\-–]|$)", "Bachelor of Arts (BA)", True),
    (r"\bBachelor(?:'s)?(?: degree)?(?: of| in)?\b|\bUndergraduate degree\b", "Bachelor's degree", False),
    (r"\bPost\s?graduate Diploma\b|\bPGDM\b|\bPG Diploma\b", "Postgraduate Diploma", False),
    (r"\bDiploma\b", "Diploma", False),
    (r"\bClass (?:XII|12)\b|\b12th\b|\bHigher Secondary\b|\bHSC\b|\bHigh School\b|\bA[- ]Levels?\b|\bSenior Secondary\b", "High School (Class XII)", False),
]
DEGREE_RES = [(re.compile(p, 0 if cs else re.I), name) for p, name, cs in DEGREES]

SPELLING = {"recieve": "receive", "seperate": "separate", "definately": "definitely", "occured": "occurred", "managment": "management",
            "experiance": "experience", "sucessful": "successful", "acheived": "achieved", "responsibilites": "responsibilities",
            "analyis": "analysis", "adress": "address", "enviroment": "environment", "knowlege": "knowledge", "commited": "committed",
            "refered": "referred", "begining": "beginning", "accomodate": "accommodate", "neccessary": "necessary", "teh": "the",
            "langauge": "language", "dashbord": "dashboard", "colaborated": "collaborated", "organisaton": "organisation"}


# ------------------------------------------------------------------ small helpers
def _lines(text):
    return [re.sub(r"\s+", " ", l).strip() for l in text.replace("\r", "").split("\n")]


def _ym(tok):
    """'Jan 2021' -> '2021-01'; '2021' -> '2021'; 'present' -> None (current)."""
    t = (tok or "").strip().lower().rstrip(".,")
    if t in ("present", "current", "now", "ongoing", "till date", "date"):
        return None
    m = re.match(rf"^({MON})[a-z]*\.?,?\s+((?:19|20)\d{{2}})$", t)
    if m:
        return f"{m.group(2)}-{MONTHS[m.group(1)[:3]]:02d}"
    m = re.match(r"^(\d{1,2})[/.-]((?:19|20)\d{2})$", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.match(r"^((?:19|20)\d{2})[/-](\d{1,2})$", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^((?:19|20)\d{2})$", t)
    return m.group(1) if m else "unknown"


def _head_section(norm):
    """'education and languages' -> 'education'; 'tools and technology' -> 'skills'. Exact names first, then the first part
    of a combined heading. Returns None for anything else."""
    if norm in HEAD_LOOKUP:
        return HEAD_LOOKUP[norm]
    parts = [p.strip() for p in re.split(r"\band\b|/|,", norm) if p.strip()]
    if len(parts) >= 2 and parts[0] in HEAD_LOOKUP:
        return HEAD_LOOKUP[parts[0]]
    if len(parts) >= 2 and all(p in HEAD_LOOKUP or p in ("technology", "technologies", "tools") for p in parts):
        return next(HEAD_LOOKUP[p] for p in parts if p in HEAD_LOOKUP)
    return None


def heading_of(line):
    """Return (section, inline_text) if `line` is a section heading, else (None, None)."""
    raw = line.strip()
    if not raw or len(raw) > 80:
        return None, None
    norm = re.sub(r"[^a-z&/, ]", "", raw.lower().split(":")[0]).replace("&", " and ")
    norm = re.sub(r"\s+", " ", norm).strip(" ,/")
    if ":" in raw:
        head, rest = raw.split(":", 1)
        hn = re.sub(r"\s+", " ", re.sub(r"[^a-z& ]", "", head.lower()).replace("&", " and ")).strip()
        if hn in HEAD_LOOKUP and not BULLET.match(raw):
            return HEAD_LOOKUP[hn], rest.strip()
    sec = _head_section(norm)
    # a combined heading ("EDUCATION & LANGUAGES") must also look like one: capitals or Title Case, so a line such as
    # "training and mentoring of new staff" inside a role is not mistaken for a section break
    styled = norm in HEAD_LOOKUP or raw.isupper() or all(w[:1].isupper() or w.lower() in ("and", "&", "of") for w in raw.split())
    if sec and styled and len(raw.split()) <= 5 and not BULLET.match(raw) and not raw.endswith("."):
        return sec, ""
    return None, None


def split_sections(lines):
    head, secs, cur = [], {}, None
    for ln in lines:
        sec, inline = heading_of(ln)
        if sec:
            cur = sec
            secs.setdefault(cur, [])
            if inline:
                secs[cur].append(inline)
            continue
        (secs.setdefault(cur, []) if cur else head).append(ln)
    return head, secs


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+|\s[•●▪|]\s", text)
    return [p.strip() for p in parts if p and len(p.strip()) > 2]


def _snippet(text, start, end, limit=200):
    """The sentence of `text` around [start, end), shortened to `limit` chars."""
    a = max(text.rfind(".", 0, start), text.rfind("\n", 0, start), text.rfind("•", 0, start))
    b_candidates = [i for i in (text.find(".", end), text.find("\n", end)) if i != -1]
    b = min(b_candidates) if b_candidates else len(text)
    s = re.sub(r"\s+", " ", text[a + 1:b]).strip(" •-–—·")
    if len(s) > limit:
        mid = start - (a + 1)
        lo = max(0, mid - limit // 2)
        s = s[lo:lo + limit].strip()
    return s


# ------------------------------------------------------------------ pieces
def find_name(head_lines):
    for ln in head_lines[:8]:
        l = ln.strip()
        if not l or re.search(r"[@\d/]|http|www\.", l):
            continue
        if re.match(r"^(curriculum vitae|resume|cv|résumé)$", l, re.I):
            continue
        l = re.sub(r"^(name\s*[:\-]\s*)", "", l, flags=re.I)
        toks = l.split()
        if 2 <= len(toks) <= 4 and all(re.match(r"^[A-Z][A-Za-z.'\-]*$", t) for t in toks) and not any(t.lower() in HEAD_LOOKUP for t in toks):
            return l.title() if l.isupper() else l
    return None


def find_contacts(text, head_text):
    out = {"email": None, "phone": None, "location": None, "linkedin": None, "github": None, "links": []}
    m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+", text)
    out["email"] = m.group(0) if m else None
    for m in re.finditer(r"(?<![\w/])(\+?\d[\d\s().\-]{7,18}\d)(?![\w/])", head_text + "\n" + text[:1500]):
        cand = m.group(1).strip()
        digits = re.sub(r"\D", "", cand)
        if 9 <= len(digits) <= 15 and not RANGE.fullmatch(cand):
            out["phone"] = cand
            break
    m = re.search(r"(?:https?://)?(?:[\w]+\.)?linkedin\.com/in/[\w\-%]+/?", text, re.I)
    out["linkedin"] = m.group(0) if m else None
    m = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", text, re.I)
    out["github"] = m.group(0) if m else None
    for m in re.finditer(r"https?://[^\s,;)]+", text):
        u = m.group(0).rstrip(".")
        if "linkedin.com" not in u and "github.com/" not in u and u not in out["links"]:
            out["links"].append(u)
    m = re.search(r"(?:location|address|city|based in)\s*[:\-]\s*([A-Za-z .,\-]{3,60})", text, re.I)
    if m:
        out["location"] = m.group(1).strip(" .,")
    else:
        for seg in re.split(r"\||•|·|\n", head_text):
            seg = seg.strip()
            if re.fullmatch(r"[A-Z][A-Za-z .]+,\s*[A-Z][A-Za-z .]+", seg) and not INSTITUTION.search(seg) and len(seg) < 45:
                out["location"] = seg
                break
    return out


def _join_wrapped(lines):
    """A comma-separated list that wrapped onto the next line ("..., Data" / "Visualization") is one list."""
    out = []
    for ln in lines:
        if out and "," in out[-1] and not re.search(r"[,;|.:]$", out[-1]) and not BULLET.match(ln) \
                and len(ln) < 60 and ":" not in ln and not heading_of(ln)[0]:
            out[-1] = out[-1] + " " + ln
        else:
            out.append(ln)
    return out


def _skill_tokens(lines):
    toks = []
    for ln in _join_wrapped(lines):
        ln = BULLET.sub("", ln)
        if ":" in ln:
            label, rest = ln.split(":", 1)
            if len(label.split()) <= 4:
                ln = rest
        for t in re.split(r"[,;|•·/]\s*|\s{2,}|\s+-\s+", ln):
            t = t.strip(" .()-–—")
            if t and len(t) <= 40 and len(t.split()) <= 4 and not re.search(r"\b(and|with|for|the|of)\b.*\b(and|with|for|the|of)\b", t, re.I):
                toks.append(t)
    return toks


def parse_skills(secs, full_text):
    """-> list of skill dicts. 'demonstrated' needs usage evidence outside a pure skills list."""
    evidence_text = "\n".join(secs.get("experience", []) + secs.get("projects", []) + secs.get("education", [])
                              + secs.get("achievements", []))
    cert_text = "\n".join(secs.get("certifications", []))
    summary_text = "\n".join(secs.get("summary", []))
    skills_lines = secs.get("skills", [])
    out, seen = [], {}

    def add(key, name, level, ctx):
        if key in seen:
            s = out[seen[key]]
            if level == "demonstrated" and s["level"] != "demonstrated":
                s.update(level="demonstrated", context=ctx)
            elif ctx and not s.get("context"):
                s["context"] = ctx
            return
        seen[key] = len(out)
        out.append({"name": name, "level": level, "proficiency": "unknown", "context": ctx})

    # 1) taxonomy skills used in work/project/education text
    for key, spans in sd.find_skills(evidence_text).items():
        a, b = spans[0]
        add(key, sd.display(key), "demonstrated", _snippet(evidence_text, a, b))
    # 1b) a certificate names a skill but does not show it in use: listed, with the certificate as context
    for key, spans in sd.find_skills(cert_text).items():
        a, b = spans[0]
        add(key, sd.display(key), "listed", ("Certification: " + _snippet(cert_text, a, b))[:300])
    # 2) listed in the skills section (taxonomy name if known, else exactly as written)
    for tok in _skill_tokens(skills_lines):
        key = sd.canonical(tok)
        if key:
            add(key, sd.display(key), "listed", "")
        elif re.match(r"^[A-Za-z0-9][A-Za-z0-9 +#.&'/-]*$", tok):
            add("raw:" + tok.lower(), tok, "listed", "")
    # 3) taxonomy skills found anywhere else (summary, header) -> listed only
    for key in sd.find_skills(summary_text):
        add(key, sd.display(key), "listed", "")
    # 3b) free-text scan of anything unsectioned (CVs without headings)
    if not any(secs.get(k) for k in ("experience", "projects", "skills")):
        for key, spans in sd.find_skills(full_text).items():
            a, b = spans[0]
            add(key, sd.display(key), "demonstrated", _snippet(full_text, a, b))
    return out[:80]


def _title_company(parts):
    """Choose (title, company) from header fragments using title words / company hints."""
    parts = [p.strip(" ,|–—-·@") for p in parts if p and p.strip(" ,|–—-·@")]
    titles = [p for p in parts if set(re.findall(r"[a-z]+", p.lower())) & TITLE_WORDS]
    others = [p for p in parts if p not in titles]
    title = titles[0] if titles else None
    company = None
    for p in others:
        if COMPANY_HINT.search(p):
            company = p
            break
    if company is None and others:
        company = others[0]
    if title is None and len(parts) >= 2 and not company:
        title, company = parts[0], parts[1]
    if title is None and others:      # no recognisable title word: first fragment is probably the role
        title = others[0] if company != others[0] or len(others) == 1 else others[1]
        if title == company:
            title = None
    return title, company


def _split_header(h):
    h = re.sub(r"\s+(at|@)\s+", " | ", h, flags=re.I)
    h = re.sub(r"\s+[–—-]\s+", " | ", h)
    return [p for p in re.split(r"\s*[|,·]\s*", h) if p.strip()]


WORK_MODE = re.compile(r"^(remote|hybrid|on-?site|work from home|wfh|part[- ]time|full[- ]time|contract|freelance)$", re.I)


def _undated_entry(header):
    """A role header with no dates ('Freelance Research & Admin Support | Remote'). Dates are recorded as unknown, never guessed."""
    frags = [f for f in _split_header(header) if not WORK_MODE.match(f.strip(" ()"))]
    title, company = _title_company(frags or [header])
    return {"title": (title or header)[:120], "company": (company or "Company not stated")[:160],
            "start": "unknown", "end": "unknown", "description": "", "achievements": []}


def parse_experience(lines, skill_keys_text=None):
    entries, cur, prev_free, last_bullet = [], None, None, False
    for ln in lines:
        if not ln:
            continue
        is_bullet = bool(BULLET.match(ln))
        m = None if is_bullet else RANGE.search(ln)
        if m:
            before, after = ln[:m.start()].strip(" ,|–—-·()"), ln[m.end():].strip(" ,|–—-·().:")
            frags = _split_header(before)
            if prev_free and not (set(re.findall(r"[a-z]+", before.lower())) & TITLE_WORDS and COMPANY_HINT.search(before)):
                if len(frags) < 2:
                    frags = [prev_free] + frags if not (set(re.findall(r"[a-z]+", prev_free.lower())) & TITLE_WORDS and frags and
                                                       set(re.findall(r"[a-z]+", frags[0].lower())) & TITLE_WORDS) else frags
            frags = [f for f in frags if not WORK_MODE.match(f.strip(" ()"))]
            title, company = _title_company(frags)
            end = _ym(m.group("e"))
            cur = {"title": (title or "Unknown role")[:120], "company": (company or "Unknown company")[:160],
                   "start": _ym(m.group("s")) or "unknown", "end": end, "description": after, "achievements": []}
            entries.append(cur)
            prev_free, last_bullet = None, False
        elif is_bullet:
            b = BULLET.sub("", ln).strip()
            fresh = cur is None or (prev_free and (cur["achievements"] or cur["description"]))
            if fresh and prev_free:
                # header line(s) followed directly by bullets, with no date range in between: an undated role
                cur = _undated_entry(prev_free)
                entries.append(cur)
                prev_free = None
            if cur is None:
                continue
            cur["achievements"].append(b[:300])
            cur["description"] = (cur["description"] + " " + b).strip()
            last_bullet = True
        elif cur is not None and last_bullet and cur["achievements"] and (ln[:1].islower() or re.search(r"[,;&]$|\b(and|or|to|of|for|with)$", cur["achievements"][-1])):
            # a bullet that wrapped onto the next line in the PDF
            cur["achievements"][-1] = (cur["achievements"][-1] + " " + ln)[:300]
            cur["description"] = (cur["description"] + " " + ln).strip()
        elif cur is not None:
            if not cur["achievements"] and not cur["description"] and cur["title"] == "Unknown role" and len(ln) <= 70:
                cur["title"] = ln[:120]            # title printed on the line after the dated company line
            elif len(ln) <= 90 and not ln.endswith(".") and entries and \
                    ((set(re.findall(r"[a-z]+", ln.lower())) & TITLE_WORDS) or "|" in ln or COMPANY_HINT.search(ln)) and len(ln.split()) <= 10:
                prev_free = ln        # probably the header of the NEXT entry (dated or not)
            else:
                cur["description"] = (cur["description"] + " " + ln).strip()
            last_bullet = False
        else:
            if len(ln) <= 90:
                prev_free = ln
    if prev_free and cur is None and (set(re.findall(r"[a-z]+", prev_free.lower())) & TITLE_WORDS):
        entries.append(_undated_entry(prev_free))      # a lone role line with no dates and no bullets
    for e in entries:
        e["description"] = re.sub(r"\s+", " ", e["description"])[:1200]
    return entries[:25]


def parse_education(lines, whole_text):
    block = [l for l in lines if l]
    if not block:                                      # no heading: look for degree words anywhere
        block = [l for l in _lines(whole_text) if any(rx.search(l) for rx, _ in DEGREE_RES)]
    out, i = [], 0
    while i < len(block):
        ln = block[i]
        hit = None
        for rx, name in DEGREE_RES:
            m = rx.search(ln)
            if m:
                hit = (m, name)
                break
        if not hit:
            i += 1
            continue
        m, name = hit
        window = ln + (" " + block[i + 1] if i + 1 < len(block) and not any(rx.search(block[i + 1]) for rx, _ in DEGREE_RES) else "")
        after = ln[m.end():]
        after = re.sub(r"^\s*(?:\(hons\.?\)|honou?rs)?\s*(?:in|of|-|–|—|:|,|\()?\s*", "", after, flags=re.I)
        fld = re.split(r"[,|–—(]|\s-\s|\bfrom\b|\bat\b|\buniversity\b|\bcollege\b|\binstitute\b|\bschool\b|\b(?:19|20)\d{2}\b|\bcgpa\b|\bgpa\b",
                       after, maxsplit=1, flags=re.I)[0].strip(" .:)")
        inst = None
        for seg in re.split(r"[|,–—]| - ", window):
            if INSTITUTION.search(seg):
                inst = re.sub(r"\(?\b(?:19|20)\d{2}\b.*$", "", seg)
                if m.group(0) in inst:           # degree and institution on one (joined) line: keep only the institution
                    inst = inst.split(m.group(0), 1)[1]
                    if fld and inst.strip(" .,:()").lower().startswith(fld.lower()):
                        inst = inst.strip(" .,:()")[len(fld):]
                inst = re.sub(r"^\s*(?:in|of|from|at)\s+", "", inst.strip(" .,:()-"), flags=re.I).strip(" .,()") or None
                if inst:
                    break
        years = re.findall(r"\b((?:19|20)\d{2})\b", window)
        if not years and i + 2 < len(block) and re.fullmatch(r"\(?(?:19|20)\d{2}\)?\.?", block[i + 2].strip()):
            years = [block[i + 2].strip(" ().")]          # sidebar layout: degree / institution / year on separate lines
        gm = re.search(r"(?:cgpa|gpa|grade|percentage|score)\s*[:\-]?\s*([\d.]+\s*(?:/\s*\d+(?:\.\d+)?)?\s*%?)", window, re.I) or \
            re.search(r"\b(\d{2}(?:\.\d+)?\s*%)", window)
        out.append({"degree": name, "field": (fld[:120] or None), "institution": (inst or "Unknown institution")[:160],
                    "graduation_year": int(years[-1]) if years else None, "grade": (gm.group(1).strip()[:40] if gm else None)})
        i += 1
    seen, uniq = set(), []
    for e in out:
        k = (e["degree"], e["institution"], e["graduation_year"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq[:10]


def parse_projects(lines):
    projs, cur = [], None
    for ln in lines:
        if not ln:
            cur = cur if cur and not cur.get("_open") else cur
            continue
        if BULLET.match(ln):
            b = BULLET.sub("", ln)
            if cur is None:
                cur = {"name": b[:100], "description": "", "url": None}
                projs.append(cur)
            else:
                cur["description"] = (cur["description"] + " " + b).strip()
            continue
        split = re.split(r"\s+[–—-]\s+|:\s+|\s\|\s", ln, maxsplit=1)
        if len(split) == 2 and 2 <= len(split[0]) <= 80 and len(split[0].split()) <= 9:
            cur = {"name": split[0].strip(" .:")[:120], "description": split[1].strip(), "url": None}
            projs.append(cur)
        elif len(ln) <= 80 and not ln.endswith("."):
            cur = {"name": ln[:120], "description": "", "url": None}
            projs.append(cur)
        elif cur is not None:
            cur["description"] = (cur["description"] + " " + ln).strip()
        else:
            cur = {"name": " ".join(ln.split()[:10]).strip(" .,")[:120], "description": ln, "url": None}
            projs.append(cur)
    out = []
    for p in projs[:15]:
        text = p["name"] + " " + p["description"]
        keys = list(sd.find_skills(text))
        out.append({"name": p["name"], "description": re.sub(r"\s+", " ", p["description"])[:600],
                    "skills": [sd.display(k) for k in keys][:15], "url": p["url"]})
    return out


def parse_certs(lines):
    out = []
    for ln in lines:
        l = BULLET.sub("", ln).strip()
        if len(l) < 4:
            continue
        year = re.search(r"\b((?:19|20)\d{2})\b", l)
        base = re.sub(r"[(\[]?\b(?:19|20)\d{2}\b[)\]]?", "", l).strip(" ,-–—|()")
        parts = re.split(r"\s+[–—-]\s+|\s\|\s|\s+by\s+|\s+from\s+|,\s+", base, maxsplit=1)
        out.append({"name": parts[0][:160], "issuer": (parts[1][:120] if len(parts) > 1 else None), "year": int(year.group(1)) if year else None})
    return out[:20]


def parse_languages(lines):
    out = []
    for tok in _skill_tokens(lines):
        m = re.match(r"^([A-Za-z]{3,20})\s*[(\-–:]?\s*([A-Za-z ]{3,25})?\)?$", tok)
        if m:
            out.append({"language": m.group(1).title(), "proficiency": (m.group(2) or "").strip() or None})
    return out[:12]


def writing_issues(text):
    issues = []
    for m in re.finditer(r"\b(\w+)\s+\1\b", text, re.I):
        if m.group(1).isalpha() and len(m.group(1)) > 2 and m.group(1).lower() not in ("had", "that"):
            issues.append({"text": m.group(0)[:160], "fix": m.group(1)})
    for w, fix in SPELLING.items():
        m = re.search(rf"\b{w}\b", text, re.I)
        if m:
            issues.append({"text": m.group(0), "fix": fix})
    for m in re.finditer(r"\bi\s+(?:am|have|was|built|led|worked|managed|developed)\b", text):
        issues.append({"text": m.group(0)[:160], "fix": "I" + m.group(0)[1:]})
    for m in re.finditer(r"[a-z]{3,},[A-Za-z]{2,}", text):
        if "@" not in m.group(0) and "." not in m.group(0):
            issues.append({"text": m.group(0), "fix": m.group(0).replace(",", ", ")})
    seen, out = set(), []
    for i in issues:
        if i["text"].lower() not in seen:
            seen.add(i["text"].lower())
            out.append(i)
    return out[:10]


# ------------------------------------------------------------------ main entry
def parse_cv(text, fallback_name=None):
    lines = _lines(text)
    head, secs = split_sections(lines)
    head_text = "\n".join(head)
    c = find_contacts(text, head_text)
    found_name = find_name(head)
    name = found_name or (fallback_name or "Name not found - please add")
    summary = " ".join(secs.get("summary", []))[:900]

    work = parse_experience(secs.get("experience", []))
    edu = parse_education(secs.get("education", []), text)
    skills = parse_skills(secs, text)
    projects = parse_projects(secs.get("projects", []))
    certs = parse_certs(secs.get("certifications", []))
    langs = parse_languages(secs.get("languages", []))
    ach = [BULLET.sub("", l)[:300] for l in secs.get("achievements", []) if len(l) > 4][:15]

    strengths, gaps = [], []
    demo = [s["name"] for s in skills if s["level"] == "demonstrated"]
    if demo:
        strengths.append("Shown in use: " + ", ".join(demo[:6]))
    if work:
        strengths.append(f"{len(work)} role(s) found in the work history")
    if edu:
        strengths.append("Education: " + edu[0]["degree"] + (f" ({edu[0]['field']})" if edu[0]["field"] else ""))
    if not found_name:
        gaps.append("No name was found at the top of the CV")
    if not secs.get("experience") and not work:
        gaps.append("No experience/work-history section was recognised")
    elif secs.get("experience") and not work:
        gaps.append("An experience section was found but no roles could be read from it; please add them")
    undated = sum(1 for w in work if w["start"] == "unknown")
    if undated:
        gaps.append(f"{undated} role(s) have no readable dates, so their length is not counted (this is not the same as having no experience)")
    if any(len(x["name"].split()) > 8 for x in certs):
        gaps.append("Some certifications may have run together in the PDF layout; please check them")
    if not c["email"]:
        gaps.append("No email address found in the CV")
    if not c["phone"]:
        gaps.append("No phone number found in the CV")
    if not edu:
        gaps.append("No education entry recognised")
    if not skills:
        gaps.append("No skills recognised")
    if any(e["institution"] == "Unknown institution" for e in edu):
        gaps.append("An education entry has no recognisable institution")

    # confidence reflects how much of a normal CV structure was actually found (0-0.85; never claims certainty)
    found = sum(bool(x) for x in (found_name, c["email"], work, edu, skills, secs.get("experience")))
    conf = round(min(0.85, 0.25 + 0.1 * found), 2)

    profile = {
        "full_name": name[:120], "email": c["email"], "phone": c["phone"], "location": c["location"],
        "education": edu, "work_history": work, "skills": skills, "projects": projects, "certifications": certs,
        "achievements": ach, "portfolio_links": c["links"][:10], "linkedin": c["linkedin"], "github": c["github"],
        "languages": langs, "strengths": strengths[:8], "gaps": gaps[:8], "writing_issues": writing_issues(text),
        "confidence": conf,
    }
    if summary:
        profile["summary"] = summary
    return profile
