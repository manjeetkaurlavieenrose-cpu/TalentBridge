"""Server-side normalisation of AI-extracted profiles. The model proposes; this code verifies."""
import re
from datetime import date
from .validation import EMAIL_RE

PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()\-]{6,18}[0-9]$")


def _ym(s, end=False):
    if not s: return None
    s = s.strip().lower()
    today = date.today()
    if s in ("present", "current", "now", "ongoing"):
        return today.year * 12 + today.month - 1
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?$", s)
    if not m: return None
    y, mo = int(m.group(1)), int(m.group(2) or (12 if end else 1))
    if not (1950 <= y <= today.year + 1) or not (1 <= mo <= 12): return None
    return y * 12 + mo - 1


def total_years(work):
    """Union of work intervals, so overlapping jobs are not double-counted."""
    spans = []
    for w in work:
        a, b = _ym(w.get("start")), _ym(w.get("end") or "present", end=True)
        if a is not None and b is not None and b >= a and (b - a) <= 12 * 50:
            spans.append((a, b + 1))
    spans.sort()
    total, cur = 0, None
    for a, b in spans:
        if cur is None: cur = [a, b]
        elif a <= cur[1]: cur[1] = max(cur[1], b)
        else: total += cur[1] - cur[0]; cur = [a, b]
    if cur: total += cur[1] - cur[0]
    return round(total / 12, 1)


def normalise(p):
    p = dict(p)
    if p.get("email") and not EMAIL_RE.match(p["email"]): p["email"] = None
    if p.get("phone") and not PHONE_RE.match(p["phone"]): p["phone"] = None
    for k in ("linkedin", "github"):
        v = p.get(k)
        if v and not re.match(r"^(https?://)?[\w.\-]+\.[a-z]{2,}(/.*)?$", v, re.I): p[k] = None
    p["portfolio_links"] = [l for l in p.get("portfolio_links", []) if re.match(r"^(https?://)?[\w.\-]+\.[a-z]{2,}", l, re.I)]
    seen, skills = set(), []
    for s in p.get("skills", []):
        k = s["name"].strip().lower()
        if k and k not in seen:
            seen.add(k); skills.append({**s, "name": s["name"].strip()})
        elif k in seen:  # keep the strongest evidence level
            for x in skills:
                if x["name"].lower() == k and s.get("level") == "demonstrated": x.update(s)
    p["skills"] = skills
    p["total_experience_years"] = total_years(p.get("work_history", []))
    return p


def summary_fields(p):
    """-> (years, top skills). Years is None when roles exist but none has readable dates: unknown, which is not the same as 0."""
    top = [s["name"] for s in sorted(p.get("skills", []), key=lambda s: s.get("level") != "demonstrated")][:8]
    work = p.get("work_history", []) or []
    if work and not any(_ym(w.get("start")) is not None for w in work):
        return None, top
    return p.get("total_experience_years"), top
