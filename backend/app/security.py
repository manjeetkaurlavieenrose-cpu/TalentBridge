import hashlib, hmac, os, secrets, threading, time
from collections import defaultdict, deque

_N, _R, _P = 2 ** 14, 8, 1
COMMON = {"password", "password1", "12345678", "123456789", "1234567890", "qwertyuiop", "letmein123", "iloveyou12"}


def hash_password(pw):
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${h.hex()}"


def verify_password(pw, stored):
    try:
        _, n, r, p, salt, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc.hex(), h)
    except Exception:
        return False


DUMMY_HASH = hash_password("dummy-password-for-timing")


def password_problem(pw, email=""):
    if len(pw) < 10: return "Password must be at least 10 characters."
    if len(pw) > 128: return "Password must be at most 128 characters."
    if pw.lower() in COMMON or pw.lower() == email.lower(): return "Choose a less guessable password."
    if pw.isdigit() or pw.isalpha(): return "Use a mix of letters and numbers or symbols."
    return None


def new_token():
    return secrets.token_urlsafe(32)


def token_hash(t):
    return hashlib.sha256(t.encode()).hexdigest()


class RateLimiter:
    """Sliding window, in-process. Use Redis (or the DB) when running more than one process."""
    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key, limit):
        mx, window = limit
        t = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= t - window:
                q.popleft()
            if len(q) >= mx:
                return False, int(window - (t - q[0])) + 1
            q.append(t)
            return True, 0

    def reset(self):
        with self.lock:
            self.hits.clear()


class DBRateLimiter:
    """Sliding window kept in the database so every gunicorn worker (and every server) shares one count."""
    def __init__(self, db):
        self.db = db

    def allow(self, key, limit):
        mx, window = limit
        t = time.time()
        with self.db.tx():
            if self.db.pg:
                self.db.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (key,))
            self.db.execute("DELETE FROM rate_hits WHERE key=? AND ts<=?", (key, t - window))
            rows = self.db.all("SELECT ts FROM rate_hits WHERE key=? ORDER BY ts LIMIT ?", (key, mx))
            if len(rows) >= mx:
                return False, int(window - (t - rows[0]["ts"])) + 1
            self.db.execute("INSERT INTO rate_hits (key, ts) VALUES (?,?)", (key, t))
            return True, 0

    def reset(self):
        self.db.execute("DELETE FROM rate_hits")

    def purge(self, older_than=7200):
        self.db.execute("DELETE FROM rate_hits WHERE ts<?", (time.time() - older_than,))
