"""Does an uploaded CV belong to the person whose record it was uploaded to?

The check is deliberately conservative. It never merges people and never moves data by itself; it only decides whether a
freshly parsed CV may be applied to the record automatically.

  match       the CV's email equals the record's email, or the names clearly agree
  unverified  the CV has no readable name and no email, so ownership cannot be checked (applied, with a warning)
  mismatch    the CV names someone else and its email (if any) differs: the CV is held and NOT applied to the profile
  confirmed   a mismatch the owner explicitly confirmed ("this is my CV", e.g. after a name change); audit-logged
  reassigned  a recruiter/admin moved the CV to the record of the person it belongs to
"""
import re
import unicodedata

NOT_FOUND_PREFIX = "Name not found"


def name_tokens(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return [t for t in re.findall(r"[a-z]+", s) if len(t) > 1 and t not in ("mr", "mrs", "ms", "dr", "miss")]


def names_agree(a, b):
    """True when two names plausibly refer to the same person. Similar is not enough: 'Priya Nair' vs 'Priya Sharma' disagree."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    sa, sb = set(ta), set(tb)
    if sa == sb:
        return True
    if len(sa & sb) >= 2:                          # 'Priya S. Nair' vs 'Priya Nair'
        return True
    if (len(sa) == 1 or len(sb) == 1) and (sa & sb):   # a one-word name on either side
        return True
    return ta[0] == tb[0] and ta[-1] == tb[-1]


def check(cv_profile, record_name, record_email):
    """-> (status, detail) where detail explains the decision in plain words (shown to the candidate/recruiter)."""
    cv_name = (cv_profile or {}).get("full_name") or ""
    if cv_name.startswith(NOT_FOUND_PREFIX):
        cv_name = ""
    cv_email = ((cv_profile or {}).get("email") or "").strip().lower()
    rec_email = (record_email or "").strip().lower()
    detail = {"cv_name": cv_name or None, "cv_email": cv_email or None, "record_name": record_name, "record_email": rec_email or None}
    if cv_email and rec_email and cv_email == rec_email:
        return "match", {**detail, "reason": "The email address on the CV matches this record."}
    if cv_name and names_agree(cv_name, record_name):
        return "match", {**detail, "reason": "The name on the CV matches this record."}
    if not cv_name and not cv_email:
        return "unverified", {**detail, "reason": "No name or email could be read from the CV, so ownership could not be checked."}
    if not cv_name:
        # an email that differs is not proof on its own (people use several addresses)
        return "unverified", {**detail, "reason": "The CV shows a different email address and no readable name. Please check it is yours."}
    return "mismatch", {**detail, "reason": f"This CV appears to belong to {cv_name}, not {record_name}. It was not applied to the profile."}


APPLIED = ("match", "unverified", "confirmed", "reassigned", None)


def usable(status):
    """May a CV with this identity status feed the candidate's profile and applications?"""
    return status in APPLIED
