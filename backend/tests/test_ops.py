"""Deployment-facing behaviour: proxies, shared rate limits, migrations, object storage."""
import os, shutil, tempfile, unittest
from app import create_app, Ctx
from app.config import Config
from app.files import S3Storage, make_storage, LocalStorage
from app.security import DBRateLimiter
from .support import test_db_url, FakeAI, Mailer


def cfg_for(tmp, **kw):
    base = dict(database_url=test_db_url(tmp), upload_dir=f"{tmp}/up", cookie_secure=False,
                admin_email="admin@tb.test", admin_password="correct-horse-9", rl_global=(100000, 60),
                allowed_origins=["http://localhost:5000"])
    base.update(kw)
    return Config(**base)


class OpsBase(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)


class ProxyTests(OpsBase):
    def _ips(self, trusted):
        app = create_app(cfg_for(self.tmp, trusted_proxies=trusted, rl_register=(1000, 60)), ai=FakeAI(), mailer=Mailer())
        r = app.test_client().post("/api/v1/auth/register/candidate", json={"email": "a@x.com", "password": "correct-horse-9", "full_name": "A B"},
                                   headers={"X-Forwarded-For": "203.0.113.7"}, environ_base={"REMOTE_ADDR": "10.0.0.1"})
        self.assertIn(r.status_code, (200, 201), r.get_data(as_text=True))
        ip = app.ctx.db.scalar("SELECT ip FROM activity_logs WHERE ip IS NOT NULL ORDER BY created_at DESC LIMIT 1")
        app.ctx.db.close()
        return ip

    def test_forwarded_ip_ignored_when_no_proxy_is_trusted(self):
        self.assertEqual(self._ips(0), "10.0.0.1")

    def test_forwarded_ip_used_behind_a_trusted_proxy(self):
        self.assertEqual(self._ips(1), "203.0.113.7")


class SharedLimiterTests(OpsBase):
    def test_two_processes_share_one_count(self):
        cfg = cfg_for(self.tmp)
        a, b = Ctx(cfg, FakeAI(), Mailer()), Ctx(cfg, FakeAI(), Mailer())   # two gunicorn workers
        self.assertIsInstance(a.limiter, DBRateLimiter)
        limit = (3, 60)
        self.assertTrue(a.limiter.allow("k", limit)[0])
        self.assertTrue(b.limiter.allow("k", limit)[0])
        self.assertTrue(a.limiter.allow("k", limit)[0])
        ok, wait = b.limiter.allow("k", limit)
        self.assertFalse(ok); self.assertGreater(wait, 0)
        self.assertTrue(a.limiter.allow("other", limit)[0])
        a.db.close(); b.db.close()

    def test_window_expires(self):
        c = Ctx(cfg_for(self.tmp), FakeAI(), Mailer())
        self.assertTrue(c.limiter.allow("k", (1, 1))[0])
        self.assertFalse(c.limiter.allow("k", (1, 1))[0])
        c.db.execute("UPDATE rate_hits SET ts = ts - 5")
        self.assertTrue(c.limiter.allow("k", (1, 1))[0])
        c.db.close()


class MigrationTests(OpsBase):
    def test_applied_once_and_recorded(self):
        cfg = cfg_for(self.tmp)
        c = Ctx(cfg, FakeAI(), Mailer()); c.db.close()
        c = Ctx(cfg, FakeAI(), Mailer())   # second start must not re-apply
        self.assertEqual([r["version"] for r in c.db.all("SELECT version FROM schema_migrations")], [1, 2, 3, 4, 5, 6, 7])
        c.db.close()

    def test_failed_migration_rolls_back_and_is_retried(self):
        c = Ctx(cfg_for(self.tmp), FakeAI(), Mailer())
        bad = [(99, "broken", "CREATE TABLE half_done (x TEXT); THIS IS NOT SQL")]
        with self.assertRaises(Exception):
            c.db.migrate(bad, lambda sql, pg: [x.strip() for x in sql.split(";") if x.strip()])
        with self.assertRaises(Exception):          # the half-created table was rolled back with the failed migration
            c.db.one("SELECT 1 AS x FROM half_done")
        self.assertIsNone(c.db.one("SELECT 1 AS x FROM schema_migrations WHERE version=99"))
        c.db.close()


class FakeS3:
    def __init__(self): self.objs = {}
    def put_object(self, Bucket, Key, Body, **kw): self.objs[(Bucket, Key)] = Body
    def get_object(self, Bucket, Key):
        import io; return {"Body": io.BytesIO(self.objs[(Bucket, Key)])}
    def delete_object(self, Bucket, Key): self.objs.pop((Bucket, Key), None)


class StorageTests(OpsBase):
    def test_s3_round_trip_and_key_safety(self):
        fake = FakeS3(); st = S3Storage("b", "cv/", client=fake)
        key, sha = st.put(b"%PDF-data", "pdf")
        self.assertIn(("b", "cv/" + key), fake.objs)
        self.assertEqual(st.get(key), b"%PDF-data")
        st.delete(key); self.assertEqual(fake.objs, {})
        for bad in ("../x", "a/b"):
            with self.assertRaises(ValueError): st.get(bad)

    def test_factory(self):
        self.assertIsInstance(make_storage(cfg_for(self.tmp)), LocalStorage)
        with self.assertRaises(RuntimeError): make_storage(cfg_for(self.tmp, storage_backend="s3"))


if __name__ == "__main__":
    unittest.main()
