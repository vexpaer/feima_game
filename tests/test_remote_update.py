import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fermat_app import service, store


class RemoteUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_sqlite_path = store.SQLITE_PATH
        store.SQLITE_PATH = Path(self.tmpdir.name) / "db.sqlite"
        store.ensure_db()

    def tearDown(self):
        store.SQLITE_PATH = self.original_sqlite_path
        self.tmpdir.cleanup()

    def test_remote_update_key_accepts_configured_api_key(self):
        with patch.dict(os.environ, {"ODDS_API_IO_KEY": "remote-secret"}):
            self.assertTrue(service.valid_match_update_key("remote-secret"))
            self.assertFalse(service.valid_match_update_key("wrong-secret"))

    def test_import_remote_matches_merges_match_and_sets_meta(self):
        start_time = store.to_iso(store.utc_now() + timedelta(days=1))
        match = {
            "id": "remote-match-1",
            "sport_key": "football",
            "league": "Football",
            "home_team": "Home",
            "away_team": "Away",
            "start_time": start_time,
            "odds": {"home": 1.9, "draw": 3.2, "away": 3.8},
            "status": "upcoming",
            "result": None,
            "home_score": None,
            "away_score": None,
            "source": "远程客户端",
            "updated_at": start_time,
        }

        count = service.import_remote_matches({"remote-match-1": match}, "远程客户端测试")

        data = store.read_db()
        self.assertEqual(1, count)
        self.assertEqual(match["home_team"], data["matches"]["remote-match-1"]["home_team"])
        self.assertEqual("远程客户端测试", data["meta"]["match_source"])
        self.assertIsNotNone(data["meta"]["last_match_update"])


if __name__ == "__main__":
    unittest.main()
