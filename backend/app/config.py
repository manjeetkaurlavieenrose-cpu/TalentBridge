import os
from dataclasses import dataclass, field


def _list(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


@dataclass
class Config:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///talentbridge.db")
    upload_dir: str = os.getenv("UPLOAD_DIR", "./var/uploads")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", 5 * 1024 * 1024))
    max_cv_pages: int = 15
    min_cv_chars: int = 200
    allowed_origins: list = field(default_factory=lambda: _list(os.getenv("ALLOWED_ORIGINS", "http://localhost:5000")))
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "1") == "1"
    # Number of reverse proxies in front of the app (nginx, load balancer...). 0 = none: X-Forwarded-For is ignored.
    trusted_proxies: int = int(os.getenv("TRUSTED_PROXIES", 0))
    # "db" shares counters between all gunicorn workers; "memory" is per-process (tests/dev only).
    rate_limit_backend: str = os.getenv("RATE_LIMIT_BACKEND", "db")
    # "local" = files under UPLOAD_DIR; "s3" = any S3-compatible bucket (AWS, Supabase, R2, MinIO).
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    s3_bucket: str = os.getenv("S3_BUCKET", "")
    s3_prefix: str = os.getenv("S3_PREFIX", "cv/")
    s3_endpoint: str = os.getenv("S3_ENDPOINT", "")
    session_hours: int = int(os.getenv("SESSION_HOURS", 12))
    # AI provider: "local" (default: rule-based, no network, no cost) | "ollama" (local model) |
    # "openai" (any OpenAI-compatible server: LM Studio, Jan, llama.cpp, vLLM, Groq, OpenRouter, Gemini) | "anthropic" (Claude API).
    ai_provider: str = os.getenv("AI_PROVIDER", "local")
    # which jobs the model handles (the rest stay rule-based): profile, summary, assessment, evaluation
    ai_tasks: str = os.getenv("AI_TASKS", os.getenv("OLLAMA_TASKS", "profile,summary,assessment,evaluation"))
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    ai_model: str = os.getenv("AI_MODEL", "claude-opus-5-5")
    ai_timeout: int = int(os.getenv("AI_TIMEOUT", 60))
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    ollama_timeout: int = int(os.getenv("OLLAMA_TIMEOUT", 180))
    ollama_tasks: str = os.getenv("OLLAMA_TASKS", "")          # older name for AI_TASKS; used when set
    ollama_num_ctx: int = int(os.getenv("OLLAMA_NUM_CTX", 8192))   # Ollama's own default (2048) silently truncates a CV
    # optional semantic CV<->job similarity (needs sentence-transformers + a one-time ~90 MB model download)
    semantic_match: bool = os.getenv("SEMANTIC_MATCH", "0") == "1"
    semantic_model: str = os.getenv("SEMANTIC_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    # where embeddings come from: ollama (e.g. nomic-embed-text) | openai | sentence-transformers. Default follows AI_PROVIDER.
    semantic_backend: str = os.getenv("SEMANTIC_BACKEND", "")
    embed_model: str = os.getenv("EMBED_MODEL", "")
    # OCR for scanned PDFs: auto (use Tesseract or RapidOCR if installed) | off
    ocr: str = os.getenv("OCR", "auto")
    ocr_lang: str = os.getenv("OCR_LANG", "eng")
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "")
    # candidates may see their own match breakdown and assessment feedback (never recruiter notes or decisions)
    candidate_sees_results: bool = os.getenv("CANDIDATE_SEES_RESULTS", "1") == "1"
    # start the background worker inside the web process (what you want for a laptop demo; use `python -m app.worker` in production)
    demo_mode: bool = os.getenv("DEMO_SEED", "0") == "1"      # shows the public demo logins on the sign-in page; never use in production
    embedded_worker: bool = os.getenv("EMBEDDED_WORKER", "0") == "1"
    # rate limits: (max requests, window seconds)
    rl_login: tuple = (10, 900)
    rl_register: tuple = (10, 3600)
    rl_upload: tuple = (20, 3600)
    rl_global: tuple = (600, 60)
    lockout_after: int = 5
    lockout_minutes: int = 15
    task_max_attempts: int = 3
    # e-mail: file (default, nothing sent) | resend | brevo | smtp. Real delivery only to EMAIL_ALLOWED_RECIPIENTS unless EMAIL_ALLOW_ALL=1
    email_provider: str = os.getenv("EMAIL_PROVIDER", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    resend_api_key: str = os.getenv("RESEND_API_KEY", "")
    brevo_api_key: str = os.getenv("BREVO_API_KEY", "")
    email_allowed_recipients: str = os.getenv("EMAIL_ALLOWED_RECIPIENTS", "")
    email_allow_all: bool = os.getenv("EMAIL_ALLOW_ALL", "0") == "1"
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", 587))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    mail_from: str = os.getenv("MAIL_FROM", "no-reply@talentbridge.local")
    public_url: str = os.getenv("PUBLIC_URL", "http://localhost:5000")
    admin_email: str = os.getenv("ADMIN_EMAIL", "")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
