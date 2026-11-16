"""Reading scanned (image-only) PDFs with OCR. Used only when a PDF has no usable text layer.

Engines, tried in this order (OCR=auto, the default):
  tesseract   the free Tesseract OCR program (best quality). Found on PATH, at TESSERACT_CMD, or in the standard Windows install
              folders. Install: Windows - the UB Mannheim installer; macOS - `brew install tesseract`; Linux - `apt install tesseract-ocr`.
  rapidocr    pure-pip fallback (`pip install -r requirements-ocr.txt`), no admin rights needed. Lower quality on long lines.
Pages are rendered with pypdfium2, which pdfplumber already installs, so OCR needs no other Python package.
OCR=off disables it. Text read by OCR is labelled as such on the candidate's profile so it is checked before confirming.
"""
import logging, os, shutil, subprocess, tempfile

log = logging.getLogger("talentbridge.ocr")
WINDOWS_PATHS = [r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe")]
MAC_PATHS = ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]


def tesseract_path(cfg=None):
    cmd = getattr(cfg, "tesseract_cmd", "") or os.getenv("TESSERACT_CMD", "")
    if cmd and os.path.isfile(cmd):
        return cmd
    found = shutil.which("tesseract")
    if found:
        return found
    for p in (WINDOWS_PATHS if os.name == "nt" else MAC_PATHS):
        if p and os.path.isfile(p):
            return p
    return None


def _rapidocr():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return None
    return RapidOCR


def engine(cfg=None):
    """-> 'tesseract' | 'rapidocr' | None (OCR switched off or nothing installed)."""
    if (getattr(cfg, "ocr", "auto") or "auto").lower() in ("off", "0", "no", "false"):
        return None
    if tesseract_path(cfg):
        return "tesseract"
    if _rapidocr():
        return "rapidocr"
    return None


def describe(cfg=None):
    e = engine(cfg)
    return {"enabled": e is not None, "engine": e}


def _pages(data, max_pages, dpi=300):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    try:
        for i in range(min(len(pdf), max_pages)):
            yield pdf[i].render(scale=dpi / 72).to_pil().convert("L")
    finally:
        pdf.close()


def _tesseract(img, exe, lang):
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)                         # Windows cannot hand an open file to another program
    try:
        img.save(path)
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}      # CREATE_NO_WINDOW: no console flashing on Windows
        r = subprocess.run([exe, path, "stdout", "-l", lang, "--psm", "3"], capture_output=True, timeout=120, **kw)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "replace")[:200])
        return r.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def ocr_pdf(data, max_pages=15, cfg=None):
    """-> (text, engine). Returns ('', None) when OCR is unavailable or fails; never raises for a missing engine."""
    e = engine(cfg)
    if not e:
        return "", None
    try:
        out = []
        if e == "tesseract":
            exe, lang = tesseract_path(cfg), getattr(cfg, "ocr_lang", "eng") or "eng"
            for img in _pages(data, max_pages):
                out.append(_tesseract(img, exe, lang))
        else:
            import numpy as np
            reader = _rapidocr()()
            for img in _pages(data, max_pages, dpi=200):
                res, _ = reader(np.array(img.convert("RGB")))
                out.append("\n".join(r[1] for r in (res or [])))
        return "\n\n".join(out), e
    except Exception as ex:          # a broken OCR install must not break CV upload: the 'no text' message is shown instead
        log.warning("OCR with %s failed: %s", e, ex)
        return "", None
