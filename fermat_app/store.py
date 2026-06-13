import copy
import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "db.json"

INITIAL_BALANCE = 1_000_000
ADMIN_USERNAME = "vexpaer"
ADMIN_PASSWORD = "1qaz2wsX"

_LOCK = threading.RLock()


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


def _read_file():
    if not DB_PATH.exists():
        return default_db()
    with DB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_file(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = DB_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(DB_PATH)


def ensure_db():
    with _LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = _read_file()
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
            _write_file(data)
        return copy.deepcopy(data)


def read_db():
    with _LOCK:
        ensure_db()
        return copy.deepcopy(_read_file())


def write_db(mutator):
    with _LOCK:
        ensure_db()
        data = _read_file()
        result = mutator(data)
        _write_file(data)
        return result
