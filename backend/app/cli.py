import sys, getpass
from .config import Config
from . import Ctx
from .db import now, uid
from .security import hash_password, password_problem

if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "create-admin":
    email = sys.argv[2].lower()
    pw = getpass.getpass("Password: ")
    prob = password_problem(pw, email)
    if prob: sys.exit(prob)
    c = Ctx(Config())
    c.db.execute("INSERT INTO users (id,email,password_hash,role,status,created_at) VALUES (?,?,?,?,?,?)",
                 (uid(), email, hash_password(pw), "admin", "active", now()))
    print("admin created")
