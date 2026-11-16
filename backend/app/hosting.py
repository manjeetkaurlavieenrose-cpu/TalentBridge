"""Make the same code run correctly on a laptop and on a hosting service, without anyone editing settings.

Hosting services put a proxy in front of the app and give it a port in $PORT. Without these defaults the app would listen only on
127.0.0.1 (unreachable), mark sign-in cookies as insecure over https, and reject the browser's own requests as "cross-origin".
Called by run.py before the settings are read. Every value is only a default: anything set by the person wins.
"""
import os


def detect(env):
    if env.get("RENDER"):
        return "Render"
    if env.get("FLY_APP_NAME"):
        return "Fly.io"
    if env.get("RAILWAY_ENVIRONMENT") or env.get("RAILWAY_PUBLIC_DOMAIN"):
        return "Railway"
    if env.get("CODESPACES") == "true":
        return "GitHub Codespaces"
    if env.get("K_SERVICE"):
        return "Google Cloud Run"
    if env.get("DYNO"):
        return "Heroku"
    return None


def public_url(env, platform):
    if platform == "Render" and env.get("RENDER_EXTERNAL_URL"):
        return env["RENDER_EXTERNAL_URL"].rstrip("/")
    if platform == "Fly.io":
        return f"https://{env['FLY_APP_NAME']}.fly.dev"
    if platform == "Railway" and env.get("RAILWAY_PUBLIC_DOMAIN"):
        return "https://" + env["RAILWAY_PUBLIC_DOMAIN"]
    if platform == "GitHub Codespaces" and env.get("CODESPACE_NAME") and env.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN"):
        return f"https://{env['CODESPACE_NAME']}-{env.get('PORT', '5050')}.{env['GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN']}"
    return None


def apply_host_defaults(env=os.environ):
    """-> the hosting platform's name, or None on a plain computer. Sets defaults in `env`."""
    platform = detect(env)
    if env.get("PORT") and "HOST" not in env:
        env["HOST"] = "0.0.0.0"                       # a service must listen on all interfaces on the port it was given
    if platform or env.get("TB_BEHIND_HTTPS") == "1":
        env.setdefault("TRUSTED_PROXIES", "1")        # one proxy in front: real client address, https and host come from it
        env.setdefault("COOKIE_SECURE", "1")
    url = public_url(env, platform)
    if url:
        env.setdefault("PUBLIC_URL", url)
        env.setdefault("ALLOWED_ORIGINS", url)
    return platform
