import unittest

from fermat_app import service


class PosterDataTests(unittest.TestCase):
    def test_build_poster_data_excludes_negative_users_from_rank(self):
        data = {
            "users": {
                "alice": {"username": "alice", "is_negative": False, "balance": 100},
                "negative-alice": {"username": "negative-alice", "is_negative": True, "balance": 999999},
                "bob": {"username": "bob", "is_negative": False, "balance": 250},
                "cara": {"username": "cara", "is_negative": False, "balance": 50},
            },
            "loans": {},
            "bets": {},
            "net_asset_history": {
                "alice": [
                    {"t": "2026-06-01T00:00:00Z", "v": 100},
                    {"t": "2026-06-02T00:00:00Z", "v": -50},
                    {"t": "2026-06-03T00:00:00Z", "v": 175},
                ]
            },
        }

        poster = service.build_poster_data("alice", data)

        self.assertEqual(poster["nickname"], "alice")
        self.assertEqual(poster["currentAmount"], 100)
        self.assertEqual(poster["coinName"], "Fermat Coin")
        self.assertEqual(poster["rank"], 2)
        self.assertEqual(poster["totalPlayers"], 3)
        self.assertEqual(
            poster["history"],
            [
                {"date": "2026-06-01T00:00:00Z", "amount": 100},
                {"date": "2026-06-02T00:00:00Z", "amount": -50},
                {"date": "2026-06-03T00:00:00Z", "amount": 175},
            ],
        )


if __name__ == "__main__":
    unittest.main()
