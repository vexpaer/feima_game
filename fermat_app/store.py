import copy
import hashlib
import hmac
import json
import secrets
import sqlite3
import tempfile
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SQLITE_PATH = DATA_DIR / "db.sqlite"

INITIAL_BALANCE = 1_000_000
ADMIN_USERNAME = "vexpaer"
ADMIN_PASSWORD = "1qaz2wsX"

_LOCK = threading.RLock()
_DICT_COLLECTIONS = (
    "users",
    "matches",
    "bets",
    "loans",
    "balance_adjustments",
    "net_asset_history",
    "custom_leaderboards",
)


def utc_now():
    return datetime.now(timezone.utc)


def to_iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 260_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password, stored_hash):
    try:
        scheme, salt, digest = stored_hash.split("$", 2)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 260_000).hex()
    return hmac.compare_digest(test, digest)


def default_db():
    now = to_iso(utc_now())
    return {
        "meta": {
            "created_at": now,
            "last_match_update": None,
            "match_source": "未更新",
            "session_secret": secrets.token_hex(32),
        },
        "users": {},
        "matches": {},
        "bets": {},
        "loans": {},
        "balance_adjustments": {},
        "net_asset_history": {},
        "custom_leaderboards": {},
    }


def normal_user(username, password, role="user", approved=False):
    now = to_iso(utc_now())
    return {
        "username": username,
        "password_hash": password_hash(password),
        "role": role,
        "approved": approved,
        "is_negative": False,
        "owner_username": None,
        "negative_username": f"negative-{username}",
        "balance": INITIAL_BALANCE,
        "credit": 100,
        "game_over": False,
        "created_at": now,
        "approved_at": now if approved else None,
    }


def negative_user(owner_username):
    now = to_iso(utc_now())
    return {
        "username": f"negative-{owner_username}",
        "password_hash": "",
        "role": "negative",
        "approved": True,
        "is_negative": True,
        "owner_username": owner_username,
        "negative_username": None,
        "balance": INITIAL_BALANCE,
        "credit": 100,
        "game_over": False,
        "created_at": now,
        "approved_at": now,
    }


def _dump_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _ensure_schema(conn):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS records (
            collection TEXT NOT NULL,
            id TEXT NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (collection, id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_collection ON records(collection)")


def _connect():
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _sqlite_has_data(conn):
    meta_count = conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
    record_count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    return bool(meta_count or record_count)


def _read_sqlite():
    with closing(_connect()) as conn:
        if not _sqlite_has_data(conn):
            return default_db()

        data = default_db()
        data["meta"] = {
            row["key"]: json.loads(row["value"])
            for row in conn.execute("SELECT key, value FROM meta")
        }
        for collection in _DICT_COLLECTIONS:
            data[collection] = {}
        for row in conn.execute("SELECT collection, id, data FROM records"):
            if row["collection"] in data:
                data[row["collection"]][row["id"]] = json.loads(row["data"])
        return data


def _write_sqlite(conn, data, old_data=None):
    old_data = old_data or {}
    with conn:
        old_meta = old_data.get("meta", {})
        new_meta = data.get("meta", {})
        for key in set(old_meta) - set(new_meta):
            conn.execute("DELETE FROM meta WHERE key = ?", (key,))
        for key, value in new_meta.items():
            serialized = _dump_json(value)
            if old_meta.get(key) != value:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, serialized),
                )

        for collection in _DICT_COLLECTIONS:
            old_items = old_data.get(collection, {})
            new_items = data.get(collection, {})
            for item_id in set(old_items) - set(new_items):
                conn.execute(
                    "DELETE FROM records WHERE collection = ? AND id = ?",
                    (collection, item_id),
                )
            for item_id, value in new_items.items():
                if old_items.get(item_id) == value:
                    continue
                conn.execute(
                    "INSERT INTO records(collection, id, data) VALUES(?, ?, ?) "
                    "ON CONFLICT(collection, id) DO UPDATE SET data = excluded.data",
                    (collection, item_id, _dump_json(value)),
                )


def _write_storage(data, old_data=None):
    with closing(_connect()) as conn:
        _write_sqlite(conn, data, old_data)


def export_sqlite_bytes():
    ensure_db()
    with tempfile.TemporaryDirectory() as tmpdir:
        snapshot_path = Path(tmpdir) / SQLITE_PATH.name
        with closing(_connect()) as source, closing(sqlite3.connect(snapshot_path)) as target:
            source.backup(target)
        return snapshot_path.read_bytes()


def ensure_db():
    with _LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = _read_sqlite()
        old_data = copy.deepcopy(data)
        changed = False
        for key, value in default_db().items():
            if key not in data:
                data[key] = value
                changed = True
        for key in ("created_at", "last_match_update", "match_source", "session_secret"):
            if key not in data["meta"]:
                data["meta"][key] = default_db()["meta"][key]
                changed = True
        users = data["users"]
        if ADMIN_USERNAME not in users:
            users[ADMIN_USERNAME] = normal_user(ADMIN_USERNAME, ADMIN_PASSWORD, role="admin", approved=True)
            changed = True
        else:
            admin = users[ADMIN_USERNAME]
            if admin.get("role") != "admin":
                admin["role"] = "admin"
                changed = True
            if not admin.get("approved"):
                admin["approved"] = True
                admin["approved_at"] = to_iso(utc_now())
                changed = True
        negative_name = f"negative-{ADMIN_USERNAME}"
        if negative_name not in users:
            users[negative_name] = negative_user(ADMIN_USERNAME)
            users[ADMIN_USERNAME]["negative_username"] = negative_name
            changed = True
        if changed:
            _write_storage(data, old_data)
        return copy.deepcopy(data)


def read_db():
    with _LOCK:
        ensure_db()
        return copy.deepcopy(_read_sqlite())


def write_db(mutator):
    with _LOCK:
        ensure_db()
        data = _read_sqlite()
        old_data = copy.deepcopy(data)
        result = mutator(data)
        _write_storage(data, old_data)
        return result
