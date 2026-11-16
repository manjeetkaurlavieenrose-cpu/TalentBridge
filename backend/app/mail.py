"""Transactional e-mail. Providers (EMAIL_PROVIDER):

  file    (default) development fallback: each message is written to <DATA_DIR>/outbox/*.eml. Nothing leaves the computer.
  resend  Resend HTTP API (free tier). Needs RESEND_API_KEY and EMAIL_FROM (a verified domain, or onboarding@resend.dev,
          which Resend only delivers to the account owner's own address).
  brevo   Brevo HTTP API (free tier, 300/day). Needs BREVO_API_KEY and EMAIL_FROM set to a sender verified in Brevo.
  smtp    any SMTP server (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD).

Safety: real providers deliver ONLY to addresses listed in EMAIL_ALLOWED_RECIPIENTS (comma-separated; "@example.org"
allows a whole domain). Anything else is held: written to the file outbox and recorded as 'held'. Set EMAIL_ALLOW_ALL=1 only
when real candidates have agreed to receive e-mail. API keys are read from the environment and never logged or returned.
"""
import json, os, re, smtplib, urllib.request, urllib.error
from datetime import datetime, timezone
from email.message import EmailMessage


class MailError(Exception):
    def __init__(self, message, retryable=True):
        self.message, self.retryable = message, retryable
        super().__init__(message)


def _mask(addr):
    """jane.doe@example.org -> j***@example.org (for logs and status output)."""
    name, _, dom = (addr or "").partition("@")
    return (name[:1] + "***@" + dom) if dom else "***"


class FileMailer:
    real = False

    def __init__(self, folder):
        self.folder = folder

    def send(self, to, subject, body):
        os.makedirs(self.folder, exist_ok=True)
        m = EmailMessage()
        m["To"], m["Subject"], m["Date"] = to, subject, datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        m.set_content(body)
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".eml"
        with open(os.path.join(self.folder, name), "wb") as f:
            f.write(bytes(m))
        return "file:" + name

    def describe(self):
        return {"provider": "file", "real_delivery": False, "folder": "data/outbox",
                "note": getattr(self, "misconfigured", None) or "Development fallback: messages are saved to the outbox folder, not sent."}


class HttpMailer:
    real = True

    def __init__(self, cfg, guard):
        self.cfg, self.guard = cfg, guard

    def _post(self, url, headers, payload):
        req = urllib.request.Request(url, json.dumps(payload).encode(), {"content-type": "application/json", "accept": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read()).get("message", "")[:200]
            except Exception:
                pass
            # 4xx = configuration problem (bad key, unverified sender): retrying will not help
            raise MailError(f"{self.name} rejected the message (HTTP {e.code}). {detail}".strip(), retryable=e.code >= 500 or e.code == 429)
        except Exception as e:
            raise MailError(f"{self.name} could not be reached ({type(e).__name__}).")


class ResendMailer(HttpMailer):
    name = "Resend"

    def send(self, to, subject, body):
        r = self._post("https://api.resend.com/emails", {"authorization": "Bearer " + self.cfg.resend_api_key},
                       {"from": self.cfg.email_from, "to": [to], "subject": subject, "text": body})
        return "resend:" + str(r.get("id", ""))

    def describe(self):
        return {"provider": "resend", "real_delivery": True, "from": self.cfg.email_from, **self.guard.describe()}


class BrevoMailer(HttpMailer):
    name = "Brevo"

    def send(self, to, subject, body):
        r = self._post("https://api.brevo.com/v3/smtp/email", {"api-key": self.cfg.brevo_api_key},
                       {"sender": {"email": self.cfg.email_from, "name": "TalentBridge"}, "to": [{"email": to}], "subject": subject, "textContent": body})
        return "brevo:" + str(r.get("messageId", ""))

    def describe(self):
        return {"provider": "brevo", "real_delivery": True, "from": self.cfg.email_from, **self.guard.describe()}


class SMTPMailer:
    real = True
    name = "SMTP"

    def __init__(self, cfg, guard):
        self.cfg, self.guard = cfg, guard

    def send(self, to, subject, body):
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = self.cfg.email_from or self.cfg.mail_from, to, subject
        m.set_content(body)
        try:
            with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port, timeout=20) as s:
                s.starttls()
                if self.cfg.smtp_user: s.login(self.cfg.smtp_user, self.cfg.smtp_password)
                s.send_message(m)
        except (smtplib.SMTPException, OSError) as e:
            raise MailError(f"SMTP delivery failed ({type(e).__name__}).")
        return "smtp"

    def describe(self):
        return {"provider": "smtp", "real_delivery": True, **self.guard.describe()}


class Guard:
    """Only allow-listed recipients get real mail; everyone else is held in the file outbox."""
    def __init__(self, cfg, fallback):
        self.allow_all = cfg.email_allow_all
        self.allowed = [a.strip().lower() for a in (cfg.email_allowed_recipients or "").split(",") if a.strip()]
        self.fallback = fallback

    def permits(self, to):
        to = (to or "").lower()
        return self.allow_all or any(to == a or (a.startswith("@") and to.endswith(a)) for a in self.allowed)

    def describe(self):
        return {"restricted": not self.allow_all, "allowed_recipients": len(self.allowed)}


class GuardedMailer:
    def __init__(self, inner, guard):
        self.inner, self.guard, self.real = inner, guard, True

    def send(self, to, subject, body):
        if not self.guard.permits(to):
            return "held:" + self.guard.fallback.send(to, subject, body)
        return self.inner.send(to, subject, body)

    def describe(self):
        return self.inner.describe()


def get_mailer(cfg):
    folder = os.path.join(os.path.dirname(os.path.abspath(cfg.upload_dir)), "outbox")
    fallback = FileMailer(folder)
    kind = (cfg.email_provider or "").lower() or ("smtp" if cfg.smtp_host else "file")
    guard = Guard(cfg, fallback)
    if kind == "resend" and cfg.resend_api_key and cfg.email_from:
        return GuardedMailer(ResendMailer(cfg, guard), guard)
    if kind == "brevo" and cfg.brevo_api_key and cfg.email_from:
        return GuardedMailer(BrevoMailer(cfg, guard), guard)
    if kind == "smtp" and cfg.smtp_host:
        return GuardedMailer(SMTPMailer(cfg, guard), guard)
    if kind not in ("file", ""):
        fallback.misconfigured = f"EMAIL_PROVIDER={kind} is missing its API key or EMAIL_FROM; using the file outbox."
    return fallback


def queue_email(c, to, subject, body, kind):
    """Record the message and send it in the background (retried on temporary failures)."""
    from .db import uid, now
    from . import pipeline as pl
    mid = uid()
    c.db.execute("INSERT INTO email_outbox (id,to_email,subject,body,status,kind,created_at) VALUES (?,?,?,?,?,?,?)",
                 (mid, to, subject[:200], body, "queued", kind, now()))
    pl.enqueue(c, "send_email", {"outbox_id": mid})
    return mid


def render(kind, **v):
    url = v.get("url", "")
    if kind == "registered":
        return ("Your TalentBridge account is ready",
                f"Hello {v['name']},\n\nYour TalentBridge candidate account has been created. Sign in to upload your CV, check the profile "
                f"we read from it and apply to openings:\n{url}\n\nIf you did not create this account, ignore this message.\n\nTalentBridge")
    if kind == "assessment_ready":
        return (f"Your assessment for {v['job']}",
                f"Hello {v['name']},\n\nThanks for applying for {v['job']}. A short assessment is waiting for you (about {v['minutes']} minutes "
                f"once you start). Sign in to open it:\n{url}\nIt stays open for 7 days.\n\nTalentBridge")
    if kind == "assessment_submitted":
        return (f"We received your assessment for {v['job']}",
                f"Hello {v['name']},\n\nYour answers for the {v['job']} assessment were received on {v['when']} and are stored safely. "
                f"A member of the hiring team will review them; you can follow progress at:\n{url}\n\nTalentBridge")
    raise ValueError(kind)
