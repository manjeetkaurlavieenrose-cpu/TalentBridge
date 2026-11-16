from .config import Config
from . import Ctx, bootstrap_admin
from .pipeline import worker_loop

if __name__ == "__main__":
    c = Ctx(Config())
    print("worker started")
    worker_loop(c)
