"""Minimal JSON-schema-style validator used for request bodies AND for AI output."""
import re


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")


def _check(v, s, path, errs, strip):
    t = s.get("type")
    if v is None and s.get("nullable"):
        return None
    if t == "string":
        if not isinstance(v, str):
            errs[path] = "must be a string"; return v
        v = v.strip()
        if "minLength" in s and len(v) < s["minLength"]:
            errs[path] = f"must be at least {s['minLength']} characters"
        if "maxLength" in s and len(v) > s["maxLength"]:
            if strip: v = v[: s["maxLength"]]
            else: errs[path] = f"must be at most {s['maxLength']} characters"
        if "enum" in s and v not in s["enum"]:
            errs[path] = f"must be one of {s['enum']}"
        if s.get("format") == "email" and not EMAIL_RE.match(v):
            errs[path] = "must be a valid email address"
        if "pattern" in s and not re.match(s["pattern"], v):
            errs[path] = "has an invalid format"
        return v
    if t in ("number", "integer"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errs[path] = "must be a number"; return v
        if t == "integer" and int(v) != v:
            errs[path] = "must be an integer"
        if "minimum" in s and v < s["minimum"]:
            if strip: v = s["minimum"]
            else: errs[path] = f"must be >= {s['minimum']}"
        if "maximum" in s and v > s["maximum"]:
            if strip: v = s["maximum"]
            else: errs[path] = f"must be <= {s['maximum']}"
        return v
    if t == "boolean":
        if not isinstance(v, bool): errs[path] = "must be true or false"
        return v
    if t == "array":
        if not isinstance(v, list):
            errs[path] = "must be a list"; return v
        mx = s.get("maxItems")
        if mx and len(v) > mx:
            if strip: v = v[:mx]
            else: errs[path] = f"must have at most {mx} items"
        if "minItems" in s and len(v) < s["minItems"]:
            errs[path] = f"must have at least {s['minItems']} items"
        return [_check(x, s.get("items", {}), f"{path}[{i}]", errs, strip) for i, x in enumerate(v)]
    if t == "object":
        if not isinstance(v, dict):
            errs[path] = "must be an object"; return v
        props = s.get("properties", {})
        out = {}
        for k in s.get("required", []):
            if k not in v or v[k] is None and not props.get(k, {}).get("nullable"):
                errs[f"{path}.{k}" if path else k] = "is required"
        for k, sub in props.items():
            if k in v:
                out[k] = _check(v[k], sub, f"{path}.{k}" if path else k, errs, strip)
        if not strip and not s.get("additionalProperties", False):
            for k in v:
                if k not in props:
                    errs[f"{path}.{k}" if path else k] = "is not allowed"
        elif s.get("additionalProperties") and not props:
            out = v
        return out
    return v


def validate(data, schema, strip=False):
    """strip=False (API input): unknown keys / over-long values are errors.
    strip=True (AI output): clamp & drop unknowns, still reject missing/wrong types."""
    errs = {}
    out = _check(data, schema, "", errs, strip)
    if errs:
        raise ValidationError(errs)
    return out


def S(**kw): return {"type": "string", **kw}
def N(**kw): return {"type": "number", **kw}
def I(**kw): return {"type": "integer", **kw}
def A(items, **kw): return {"type": "array", "items": items, **kw}
def O(props, required=None, **kw): return {"type": "object", "properties": props, "required": required or [], **kw}
