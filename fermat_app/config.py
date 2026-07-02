import json
import os

from .store import DATA_DIR


CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "the_odds_api_key": "",
    "odds_api_io_key": "",
    "odds_api_io_bookmakers": ["Bet365"],
    "odds_api_io_past_days": 7,
    "odds_api_io_future_days": 30,
    "odds_api_io_page_limit": 100,
    "region": "eu",
    "sports": ["soccer_epl", "soccer_fifa_world_cup"],
    "update_minutes": 120,
    "server_api_updates_enabled": True,
}


def _config_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, str):
        return value.lower() not in {"0", "false", "no", "off"}
    return bool(value)


def load_config():
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            file_config = json.load(f)
        config.update({key: value for key, value in file_config.items() if value not in (None, "")})

    env_key = os.environ.get("THE_ODDS_API_KEY") or os.environ.get("FOOTBALL_ODDS_API_KEY")
    if env_key:
        config["the_odds_api_key"] = env_key
    odds_api_io_key = os.environ.get("ODDS_API_IO_KEY") or os.environ.get("ODDS_API_KEY")
    if odds_api_io_key:
        config["odds_api_io_key"] = odds_api_io_key
    if os.environ.get("ODDS_API_IO_BOOKMAKERS"):
        config["odds_api_io_bookmakers"] = [
            item.strip() for item in os.environ["ODDS_API_IO_BOOKMAKERS"].split(",") if item.strip()
        ]
    if os.environ.get("ODDS_API_IO_PAST_DAYS"):
        config["odds_api_io_past_days"] = max(0, int(os.environ["ODDS_API_IO_PAST_DAYS"]))
    if os.environ.get("ODDS_API_IO_FUTURE_DAYS"):
        config["odds_api_io_future_days"] = max(1, int(os.environ["ODDS_API_IO_FUTURE_DAYS"]))
    if os.environ.get("ODDS_API_IO_PAGE_LIMIT"):
        config["odds_api_io_page_limit"] = max(1, int(os.environ["ODDS_API_IO_PAGE_LIMIT"]))
    if os.environ.get("THE_ODDS_API_REGION"):
        config["region"] = os.environ["THE_ODDS_API_REGION"]
    if os.environ.get("THE_ODDS_API_SPORTS"):
        config["sports"] = [item.strip() for item in os.environ["THE_ODDS_API_SPORTS"].split(",") if item.strip()]
    if os.environ.get("THE_ODDS_API_UPDATE_MINUTES"):
        config["update_minutes"] = max(10, int(os.environ["THE_ODDS_API_UPDATE_MINUTES"]))
    if os.environ.get("SERVER_API_UPDATES_ENABLED"):
        config["server_api_updates_enabled"] = _config_bool(os.environ["SERVER_API_UPDATES_ENABLED"])

    config["sports"] = [item for item in config.get("sports", []) if str(item).startswith("soccer_")]
    if not config["sports"]:
        config["sports"] = list(DEFAULT_CONFIG["sports"])
    if isinstance(config.get("odds_api_io_bookmakers"), str):
        config["odds_api_io_bookmakers"] = [
            item.strip() for item in config["odds_api_io_bookmakers"].split(",") if item.strip()
        ]
    if not config.get("odds_api_io_bookmakers"):
        config["odds_api_io_bookmakers"] = list(DEFAULT_CONFIG["odds_api_io_bookmakers"])
    config["odds_api_io_past_days"] = max(0, int(config.get("odds_api_io_past_days", 7)))
    config["odds_api_io_future_days"] = max(1, int(config.get("odds_api_io_future_days", 30)))
    config["odds_api_io_page_limit"] = max(1, min(100, int(config.get("odds_api_io_page_limit", 100))))
    config["update_minutes"] = max(10, int(config.get("update_minutes", DEFAULT_CONFIG["update_minutes"])))
    config["server_api_updates_enabled"] = _config_bool(config.get("server_api_updates_enabled"), True)
    return config
