import tempfile
import unittest
from pathlib import Path

from fermat_app import service, store, web


class AdminRoleTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_sqlite_path = store.SQLITE_PATH
        store.SQLITE_PATH = Path(self.tmpdir.name) / "db.sqlite"
        store.ensure_db()

    def tearDown(self):
        store.SQLITE_PATH = self.original_sqlite_path
        self.tmpdir.cleanup()

    def make_admin(self, username):
        service.register_user(username, "secret1")
        service.approve_user("vexpaer", username)
        service.set_admin("vexpaer", username)

    def test_super_admin_can_demote_other_admin_to_user(self):
        self.make_admin("alice")

        message = service.demote_admin("vexpaer", "alice")

        data = store.read_db()
        self.assertEqual("user", data["users"]["alice"]["role"])
        self.assertEqual("admin", data["users"]["vexpaer"]["role"])
        self.assertEqual("已将 alice 降为普通用户。", message)

    def test_regular_admin_cannot_demote_admin(self):
        self.make_admin("alice")
        self.make_admin("bob")

        with self.assertRaisesRegex(service.AppError, "需要超级管理员权限"):
            service.demote_admin("alice", "bob")

        data = store.read_db()
        self.assertEqual("admin", data["users"]["bob"]["role"])

    def test_super_admin_can_delete_user(self):
        service.register_user("charlie", "secret1")
        service.approve_user("vexpaer", "charlie")

        message = service.delete_user("vexpaer", "charlie")

        data = store.read_db()
        self.assertNotIn("charlie", data["users"])
        self.assertNotIn("negative-charlie", data["users"])
        self.assertEqual("已删除账号：charlie, negative-charlie。", message)

    def test_regular_admin_cannot_delete_user(self):
        self.make_admin("alice")
        service.register_user("charlie", "secret1")
        service.approve_user("vexpaer", "charlie")

        with self.assertRaisesRegex(service.AppError, "需要超级管理员权限"):
            service.delete_user("alice", "charlie")

        data = store.read_db()
        self.assertIn("charlie", data["users"])
        self.assertIn("negative-charlie", data["users"])

    def test_super_admin_cannot_demote_self(self):
        with self.assertRaisesRegex(service.AppError, "不能降级超级管理员"):
            service.demote_admin("vexpaer", "vexpaer")

        data = store.read_db()
        self.assertEqual("admin", data["users"]["vexpaer"]["role"])

    def test_super_admin_table_shows_demote_action_for_other_admins(self):
        users = [
            {"username": "alice", "role": "admin", "balance": 0, "credit": 100, "approved": True},
            {"username": "vexpaer", "role": "admin", "balance": 0, "credit": 100, "approved": True},
        ]

        html = web.users_table(users, {"username": "vexpaer", "role": "admin"})

        self.assertIn('action="/admin/demote-admin"', html)
        self.assertIn('value="alice"', html)
        self.assertIn("降为普通用户", html)

    def test_super_admin_table_shows_delete_action_for_users(self):
        users = [
            {"username": "charlie", "role": "user", "balance": 0, "credit": 100, "approved": True},
        ]

        html = web.users_table(users, {"username": "vexpaer", "role": "admin"})

        self.assertIn('action="/admin/delete-user"', html)
        self.assertIn('value="charlie"', html)
        self.assertIn("删除", html)

    def test_regular_admin_table_hides_delete_action(self):
        users = [
            {"username": "charlie", "role": "user", "balance": 0, "credit": 100, "approved": True},
        ]

        html = web.users_table(users, {"username": "alice", "role": "admin"})

        self.assertNotIn('action="/admin/delete-user"', html)
        self.assertNotIn("删除", html)

    def test_regular_admin_table_hides_demote_action(self):
        users = [
            {"username": "alice", "role": "admin", "balance": 0, "credit": 100, "approved": True},
            {"username": "bob", "role": "admin", "balance": 0, "credit": 100, "approved": True},
        ]

        html = web.users_table(users, {"username": "alice", "role": "admin"})

        self.assertNotIn('action="/admin/demote-admin"', html)
        self.assertNotIn("降为普通用户", html)


if __name__ == "__main__":
    unittest.main()
