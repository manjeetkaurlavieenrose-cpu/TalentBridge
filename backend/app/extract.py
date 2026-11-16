"""Document -> plain text. Two-column PDF layouts are read column by column. PDFs without a text layer (scans) are read with
OCR when an OCR engine is installed (see ocr.py); otherwise they are reported, not guessed at."""
import io, re


class ExtractionError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def _clean(t):
    t = t.replace("\x00", " ")
    # Some PDF fonts have no unicode map; pdfplumber then yields "(cid:127)" for a bullet. Normalise them.
    t = re.sub(r"(?m)^[ \t]*\(cid:\d+\)[ \t]*", "• ", t)
    t = re.sub(r"\(cid:\d+\)", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def find_gutter(words, width, height):
    """-> (x, header_bottom) of the gap between two text columns, or None for a single-column page.
    A gutter is a vertical line no word crosses below an optional full-width header (name/contact block in the top 30%),
    with a real share of the words on each side. The widest such gap wins."""
    if len(words) < 40:
        return None
    n, runs, run = len(words), [], []
    for x in range(int(width * 0.22), int(width * 0.78), 3):
        crossing = [w for w in words if w["x0"] < x < w["x1"]]
        head = max((w["bottom"] for w in crossing), default=0)
        ok = head <= height * 0.3
        if ok:
            body = [w for w in words if w["top"] >= head]
            left = [w for w in body if w["x1"] <= x]
            right = [w for w in body if w["x0"] >= x]
            tall = 0.4 * _spread(body)       # both columns run down a good part of the page, not one short block beside text
            ok = len(left) >= 0.12 * n and len(right) >= 0.12 * n and _spread(left) >= tall and _spread(right) >= tall
        if ok:
            run.append((x, head))
        elif run:
            runs.append(run); run = []
    if run:
        runs.append(run)
    runs = [r for r in runs if len(r) >= 3]          # at least ~9 pt of clear space: not just the gap between two words
    if not runs:
        return None
    best = max(runs, key=len)
    x, _ = best[len(best) // 2]
    return x, max(h for _, h in best)


def _spread(ws):
    return (max(w["bottom"] for w in ws) - min(w["top"] for w in ws)) if ws else 0


def page_text(page):
    try:
        words = page.extract_words()
        g = find_gutter(words, page.width, page.height)
    except Exception:
        g = None
    if not g:
        return page.extract_text() or ""
    x, head = g
    x0, top, x1, bottom = page.bbox
    parts = []
    if head > top:
        parts.append(page.crop((x0, top, x1, head)).extract_text() or "")
    parts.append(page.crop((x0, head, x0 + x, bottom)).extract_text() or "")
    parts.append(page.crop((x0 + x, head, x1, bottom)).extract_text() or "")
    return "\n\n".join(p for p in parts if p.strip())


def pdf_text(data, max_pages):
    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > max_pages:
                raise ExtractionError("too_many_pages", f"CV has more than {max_pages} pages.")
            return _clean("\n\n".join(page_text(p) for p in pdf.pages))
    except ExtractionError:
        raise
    except Exception as e:
        if "password" in type(e).__name__.lower() or "encrypt" in type(e).__name__.lower() or b"/Encrypt" in data[-4096:]:
            raise ExtractionError("password_protected", "This PDF is password-protected. Save a copy without the password and upload that.") from e
        raise ExtractionError("unreadable_pdf", "The PDF could not be read (it may be damaged). Try exporting it again or upload a DOCX.") from e


def docx_text(data):
    import docx
    try:
        d = docx.Document(io.BytesIO(data))
    except Exception as e:
        raise ExtractionError("unreadable_docx", "The DOCX could not be read.") from e
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            seen = []
            for c in row.cells:                  # merged cells repeat; keep each once
                if c.text.strip() and c.text.strip() not in seen:
                    seen.append(c.text.strip())
            parts.append(" | ".join(seen))
    for s in d.sections:                         # contact details often sit in the page header
        for p in s.header.paragraphs:
            if p.text.strip() and p.text not in parts:
                parts.insert(0, p.text)
    return _clean("\n".join(parts))


def extract_document(data, kind, cfg):
    """-> (text, method). method: 'text' (text layer / DOCX) or 'ocr:<engine>' (scanned PDF read by OCR)."""
    text = pdf_text(data, cfg.max_cv_pages) if kind == "pdf" else docx_text(data)
    method = "text"
    if len(text) < cfg.min_cv_chars and kind == "pdf":
        from . import ocr
        o, eng = ocr.ocr_pdf(data, cfg.max_cv_pages, cfg)
        o = _clean(o)
        if eng and len(o) >= cfg.min_cv_chars:
            text, method = o, f"ocr:{eng}"
        elif not eng and not ocr.engine(cfg):
            raise ExtractionError(
                "no_text_layer",
                "This looks like a scanned or image-only document. Upload a text-based PDF or DOCX, or ask the administrator to "
                "install the free Tesseract OCR program so scanned CVs can be read.")
    if len(text) < cfg.min_cv_chars:
        raise ExtractionError(
            "no_text_layer",
            "Almost no text could be read, even with OCR. Upload a clearer scan, a text-based PDF or a DOCX.")
    return text[:60000], method


def extract_text(data, kind, cfg):
    return extract_document(data, kind, cfg)[0]
