#!/usr/bin/env python3
"""Send ONE test e-mail with the configured provider, to check that delivery works.

    python3 scripts/send_test_email.py --to you@example.org

Reads the same settings as the app (.env or environment): EMAIL_PROVIDER, EMAIL_FROM, RESEND_API_KEY / BREVO_API_KEY,
EMAIL_ALLOWED_RECIPIENTS. The recipient must be on EMAIL_ALLOWED_RECIPIENTS (or EMAIL_ALLOW_ALL=1), so this can never
reach a candidate by accident. Prints the provider's message id or the exact error. Never prints the API key.
"""
import argparse, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend")); sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", required=True)
    a = ap.parse_args()
    from run import load_env
    load_env(os.path.join(ROOT, ".env"))
    os.environ.setdefault("UPLOAD_DIR", os.path.join(os.getenv("DATA_DIR", os.path.join(ROOT, "data")), "uploads"))
    from app.config import Config
    from app import mail
    cfg = Config()
    m = mail.get_mailer(cfg)
    info = m.describe()
    print("Provider:", info.get("provider"), "| real delivery:", info.get("real_delivery"), "|", info.get("note") or f"from {info.get('from')}")
    if not getattr(m, "real", False):
        print("No real provider is configured, so the message goes to the file outbox only (data/outbox). See README > E-mail.")
    elif not m.guard.permits(a.to):
        sys.exit(f"Refusing: {a.to} is not on EMAIL_ALLOWED_RECIPIENTS. Add it there first (only addresses you control or have approval for).")
    try:
        r = m.send(a.to, "TalentBridge test e-mail", "This is a test message from TalentBridge. If you can read it, e-mail delivery works.\n")
    except mail.MailError as e:
        sys.exit("FAILED: " + e.message)
    print("Result:", r)
    if r.startswith(("resend:", "brevo:", "smtp")):
        print("Accepted by the provider. Check the inbox (and spam folder) of", a.to)


if __name__ == "__main__":
    main()
