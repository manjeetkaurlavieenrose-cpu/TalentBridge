"""CV <-> job text similarity. Informational only: it is shown next to the match but is NOT part of the score.

Two methods, always labelled honestly:
  lexical   (default, no downloads) Share of the job description's distinctive terms that also appear in the CV.
            This is word overlap. It does not understand meaning and cannot tell "used SQL" from "never used SQL".
  semantic  (SEMANTIC_MATCH=1) Cosine similarity of text embeddings. Embeddings come from the configured AI server
            (Ollama, e.g. `ollama pull nomic-embed-text`, or an OpenAI-compatible /embeddings endpoint) or from a local
            sentence-transformers model (`pip install -r requirements-semantic.txt`). SEMANTIC_BACKEND picks one.
            If the embedding source is unavailable the app stays on the lexical method for that comparison.
Neither number is evidence that someone can do the job.
"""
import logging, re
from .answer_scorer import STOP, stem

log = logging.getLogger("talentbridge.similarity")
JOB_FILLER = set("""role work team will able ability experience skills skill including include strong good excellent required preferred responsible
responsibilities looking candidate candidates join company opportunity must need needs years year plus knowledge understanding working
ideal seeking position job day days business well new using use used help support within across""".split())

NOTE_LEXICAL = ("Word overlap between the CV and the job text. It does not understand meaning, so treat it as a rough pointer, not as evidence "
                "of ability.")
NOTE_SEMANTIC = ("Similarity of meaning between the CV and the job text, from an embedding model. It is a rough pointer, not evidence of "
                 "ability.")


def terms(text):
    out = {}
    for w in re.findall(r"[a-z][a-z0-9+#.\-]{2,}", (text or "").lower()):
        w = w.strip(".-")
        if len(w) < 3 or w in STOP or w in JOB_FILLER:
            continue
        out.setdefault(stem(w), w)
    return out


def lexical(cv_text, job_text):
    jt, ct = terms(job_text), terms(cv_text)
    if not jt or not ct:
        return {"method": "lexical", "score": None, "shared_terms": [], "note": "Not enough text to compare."}
    shared = [jt[k] for k in jt if k in ct]
    score = round(100 * len(shared) / len(jt), 1)
    return {"method": "lexical", "score": score, "shared_terms": sorted(shared)[:25], "note": NOTE_LEXICAL}


def _chunks(text, size=60):
    ws = (text or "").split()
    return [" ".join(ws[i:i + size]) for i in range(0, len(ws), size)] or [""]


class SentenceEncoder:
    """Lazy wrapper around sentence-transformers. `encode(list[str]) -> list[list[float]]`."""
    label = "sentence-transformers"

    def __init__(self, model_name):
        self.model_name, self._m = model_name, None

    def encode(self, texts):
        if self._m is None:
            from sentence_transformers import SentenceTransformer   # imported only when SEMANTIC_MATCH=1
            self._m = SentenceTransformer(self.model_name)
        return self._m.encode(texts, normalize_embeddings=True).tolist()


class HTTPEncoder:
    """Embeddings from the AI server that is already configured: Ollama (/api/embed, e.g. nomic-embed-text) or any
    OpenAI-compatible server (/embeddings). No PyTorch download needed."""
    def __init__(self, kind, url, model, key="", timeout=15):
        self.kind, self.url, self.model, self.key, self.timeout = kind, url.rstrip("/"), model, key, timeout
        self.label = f"{kind}:{model}"

    def encode(self, texts):
        import json, urllib.request
        if self.kind == "ollama":
            path, body, h = "/api/embed", {"model": self.model, "input": texts}, {}
        else:
            path, body, h = "/embeddings", {"model": self.model, "input": texts}, ({"authorization": "Bearer " + self.key} if self.key else {})
        req = urllib.request.Request(self.url + path, json.dumps(body).encode(), {"content-type": "application/json", **h})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read())
        vecs = data["embeddings"] if self.kind == "ollama" else [d["embedding"] for d in data["data"]]
        out = []
        for v in vecs:
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out


def make_encoder(cfg):
    if not getattr(cfg, "semantic_match", False):
        return None
    provider = (getattr(cfg, "ai_provider", "") or "").lower()
    backend = (getattr(cfg, "semantic_backend", "") or ("ollama" if provider == "ollama" else "openai" if provider == "openai" else
                                                        "sentence-transformers")).lower()
    if backend == "ollama":
        return HTTPEncoder("ollama", cfg.ollama_url, getattr(cfg, "embed_model", "") or "nomic-embed-text")
    if backend == "openai":
        return HTTPEncoder("openai", cfg.openai_base_url, getattr(cfg, "embed_model", "") or "text-embedding-3-small", cfg.openai_api_key)
    try:
        import sentence_transformers  # noqa: F401
    except Exception:
        log.warning("SEMANTIC_MATCH=1 but sentence-transformers is not installed; using the lexical method instead.")
        return None
    return SentenceEncoder(cfg.semantic_model)


def semantic(cv_text, job_text, encoder):
    import math
    vecs = encoder.encode(_chunks(cv_text) + _chunks(job_text, 120))
    nc = len(_chunks(cv_text))
    cv_v, job_v = vecs[:nc], vecs[nc:]

    def mean(vs):
        m = [sum(x) / len(vs) for x in zip(*vs)]
        n = math.sqrt(sum(x * x for x in m)) or 1.0
        return [x / n for x in m]
    a, b = mean(cv_v), mean(job_v)
    cos = sum(x * y for x, y in zip(a, b))
    return {"method": "semantic", "score": round(max(0.0, min(1.0, cos)) * 100, 1), "shared_terms": [], "note": NOTE_SEMANTIC}


def compare(cv_text, job_text, encoder=None):
    if encoder is not None and cv_text:
        try:
            return semantic(cv_text, job_text, encoder)
        except Exception as e:   # model missing/offline: fall back, never fail the application
            log.warning("semantic similarity failed (%s); using lexical", type(e).__name__)
    r = lexical(cv_text, job_text)
    return r


def job_text(job):
    parts = [job.get("title", ""), job.get("description", ""), " ".join(job.get("required_skills") or []),
             " ".join(job.get("preferred_skills") or []), " ".join(job.get("custom_requirements") or []), job.get("task_brief") or ""]
    return "\n".join(p for p in parts if p)
