import json
import os

from .store import DATA_DIR


CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "the_odds_api_key": "",
    "region": "eu",
    "sports": ["soccer_epl"],
    "update_minutes": 60,
}


def load_config():
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            file_config = json.load(f)
        config.update({key: value for key, value in file_config.items() if value not in (None, "")})

    env_key = os.environ.get("THE_ODDS_API_KEY") or os.environ.get("FOOTBALL_ODDS_API_KEY")
    if env_key:
        config["the_odds_api_key"] = env_key
    if os.environ.get("THE_ODDS_API_REGION"):
        config["region"] = os.environ["THE_ODDS_API_REGION"]
    if os.environ.get("THE_ODDS_API_SPORTS"):
        config["sports"] = [item.strip() for item in os.environ["THE_ODDS_API_SPORTS"].split(",") if item.strip()]
    if os.environ.get("THE_ODDS_API_UPDATE_MINUTES"):
        config["update_minutes"] = max(10, int(os.environ["THE_ODDS_API_UPDATE_MINUTES"]))

    config["sports"] = [item for item in config.get("sports", []) if str(item).startswith("soccer_")]
    if not config["sports"]:
        config["sports"] = list(DEFAULT_CONFIG["sports"])
    config["update_minutes"] = max(10, int(config.get("update_minutes", DEFAULT_CONFIG["update_minutes"])))
    return config
