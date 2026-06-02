import hashlib
import random
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .config import load_config
from .store import parse_iso, to_iso, utc_now


SPORT_KEYS = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_fifa_world_cup",
]

DEMO_TEAMS = [
    ("阿森纳", "利物浦", "英超"),
    ("皇家马德里", "巴塞罗那", "西甲"),
    ("拜仁慕尼黑", "多特蒙德", "德甲"),
    ("国际米兰", "AC米兰", "意甲"),
    ("巴黎圣日耳曼", "马赛", "法甲"),
    ("曼城", "切尔西", "英超"),
    ("尤文图斯", "那不勒斯", "意甲"),
    ("马德里竞技", "塞维利亚", "西甲"),
]


class MatchSource:
    def __init__(self):
        config = load_config()
        self.api_key = config["the_odds_api_key"]
        self.odds_api_io_key = config["odds_api_io_key"]
        self.odds_api_io_bookmakers = config["odds_api_io_bookmakers"]
        self.odds_api_io_past_days = config["odds_api_io_past_days"]
        self.odds_api_io_future_days = config["odds_api_io_future_days"]
        self.odds_api_io_page_limit = config["odds_api_io_page_limit"]
        self.region = config["region"]
        self.sport_keys = config["sports"]

    def fetch(self, existing_matches, score_sports=None):
        score_sports = set(score_sports or [])
        if self.odds_api_io_key:
            try:
                return self._fetch_odds_api_io(existing_matches)
            except Exception as exc:
                return {}, (
                    f"Odds-API.io 拉取失败：{_format_fetch_error(exc)}；"
                    f"当前仍显示旧比赛：{_source_summary(existing_matches)}"
                )
        elif self.api_key:
            try:
                return self._fetch_odds_api(existing_matches, score_sports)
            except Exception as exc:
                return {}, (
                    f"The Odds API 拉取失败：{_format_fetch_error(exc)}；"
                    f"当前仍显示旧比赛：{_source_summary(existing_matches)}"
                )
        return self._demo_matches()

    def _request_json(self, path, params, base_url="https://api.the-odds-api.com/v4"):
        query = urllib.parse.urlencode(params)
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "fermat-coin-football/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            import json

            return json.loads(resp.read().decode("utf-8"))

    def _fetch_odds_api_io(self, existing_matches):
        now = utc_now()
        from_dt = now - timedelta(days=self.odds_api_io_past_days)
        to_dt = now + timedelta(days=self.odds_api_io_future_days)
        events = self._fetch_odds_api_io_events(from_dt, to_dt)
        odds_by_id = self._fetch_odds_api_io_odds(events)
        matches = {}
        skipped_without_odds = 0
        for event in events:
            match = self._match_from_odds_api_io_event(event, odds_by_id, existing_matches, now)
            if match:
                matches[match["id"]] = match
            else:
                skipped_without_odds += 1
        label = (
            f"Odds-API.io 拉取成功：football 近期 {len(matches)} 场"
            f"（{self.odds_api_io_past_days} 天前至 {self.odds_api_io_future_days} 天后"
        )
        if skipped_without_odds:
            label += f"，跳过 {skipped_without_odds} 场无可用赔率"
        return matches, label + "）"

    def _fetch_odds_api_io_events(self, from_dt, to_dt):
        events = []
        skip = 0
        for _ in range(20):
            rows = _as_rows(
                self._request_json(
                    "events",
                    {
                        "apiKey": self.odds_api_io_key,
                        "sport": "football",
                        "status": "pending,live,settled",
                        "from": to_iso(from_dt),
                        "to": to_iso(to_dt),
                        "limit": self.odds_api_io_page_limit,
                        "skip": skip,
                    },
                    "https://api.odds-api.io/v3",
                )
            )
            if not rows:
                break
            events.extend(rows)
            if len(rows) < self.odds_api_io_page_limit:
                break
            skip += len(rows)
        return events

    def _fetch_odds_api_io_odds(self, events):
        event_ids = [
            str(event.get("id"))
            for event in events
            if event.get("id") is not None and (_safe_int(event.get("bookmakerCount", 1)) or 0) > 0
        ]
        odds_by_id = {}
        for index in range(0, len(event_ids), 10):
            batch = event_ids[index : index + 10]
            rows = _as_rows(
                self._request_json(
                    "odds/multi",
                    {
                        "apiKey": self.odds_api_io_key,
                        "eventIds": ",".join(batch),
                        "bookmakers": ",".join(self.odds_api_io_bookmakers),
                    },
                    "https://api.odds-api.io/v3",
                )
            )
            for row in rows:
                raw_id = row.get("id")
                if raw_id is not None:
                    odds_by_id[str(raw_id)] = row
        return odds_by_id

    def _match_from_odds_api_io_event(self, event, odds_by_id, existing_matches, now):
        raw_id = event.get("id")
        if raw_id is None:
            return None
        raw_id = str(raw_id)
        odds_row = odds_by_id.get(raw_id) or {}
        match_id = f"odds-api-io-{raw_id}"
        old = existing_matches.get(match_id, {})
        home = odds_row.get("home") or event.get("home")
        away = odds_row.get("away") or event.get("away")
        start_time = odds_row.get("date") or event.get("date")
        if not home or not away or not start_time:
            return None
        odds = self._average_odds_api_io_ml(odds_row) or old.get("odds")
        status = _odds_api_io_status(odds_row.get("status") or event.get("status"))
        start = parse_iso(start_time)
        if status == "upcoming" and start <= now:
            status = "in_progress"
        if status == "upcoming" and not odds:
            return None
        if not odds:
            odds = old.get("odds") or {"home": 1.9, "draw": 3.2, "away": 3.8}
        league = _league_name(odds_row) or _league_name(event) or "Football"
        match = {
            "id": match_id,
            "provider_event_id": raw_id,
            "sport_key": "football",
            "league": league,
            "home_team": home,
            "away_team": away,
            "start_time": start_time,
            "odds": odds,
            "status": status,
            "result": None,
            "home_score": None,
            "away_score": None,
            "source": "Odds-API.io",
            "updated_at": to_iso(now),
        }
        self._apply_odds_api_io_score(match, odds_row or event)
        return match

    def _average_odds_api_io_ml(self, row):
        buckets = {"home": [], "draw": [], "away": []}
        for markets in (row.get("bookmakers") or {}).values():
            for market in markets or []:
                if str(market.get("name", "")).lower() not in ("ml", "moneyline"):
                    continue
                for outcome in market.get("odds") or []:
                    price = _safe_float(outcome.get("price"))
                    if price is None:
                        continue
                    name = str(outcome.get("name", "")).lower()
                    if name == "home":
                        buckets["home"].append(price)
                    elif name == "away":
                        buckets["away"].append(price)
                    elif name == "draw":
                        buckets["draw"].append(price)
        if not buckets["home"] or not buckets["away"]:
            return None
        if not buckets["draw"]:
            buckets["draw"].append(3.2)
        return {key: round(sum(values) / len(values), 2) for key, values in buckets.items()}

    def _apply_odds_api_io_score(self, match, row):
        scores = row.get("scores") or {}
        home_score = _safe_int(scores.get("home") if isinstance(scores, dict) else None)
        away_score = _safe_int(scores.get("away") if isinstance(scores, dict) else None)
        if home_score is not None:
            match["home_score"] = home_score
        if away_score is not None:
            match["away_score"] = away_score
        if match["status"] == "completed" and home_score is not None and away_score is not None:
            if home_score > away_score:
                match["result"] = "home"
            elif away_score > home_score:
                match["result"] = "away"
            else:
                match["result"] = "draw"

    def _fetch_odds_api(self, existing_matches, score_sports):
        now = utc_now()
        matches = {}
        source_parts = []
        for sport in self.sport_keys:
            odds_rows = self._request_json(
                f"sports/{sport}/odds/",
                {
                    "apiKey": self.api_key,
                    "regions": self.region,
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                    "dateFormat": "iso",
                },
            )
            scores_rows = []
            if sport in score_sports:
                scores_rows = self._request_json(
                    f"sports/{sport}/scores/",
                    {
                        "apiKey": self.api_key,
                        "daysFrom": 3,
                        "dateFormat": "iso",
                    },
                )
            scores_by_id = {row.get("id"): row for row in scores_rows}
            for row in odds_rows:
                match = self._match_from_odds(row)
                if match:
                    score_row = scores_by_id.get(match["id"])
                    if score_row:
                        self._apply_score(match, score_row)
                    elif parse_iso(match["start_time"]) <= now:
                        match["status"] = "in_progress"
                    matches[match["id"]] = match
            for row in scores_rows:
                match_id = row.get("id")
                if not match_id or match_id in matches:
                    continue
                old = existing_matches.get(match_id, {})
                match = {
                    "id": match_id,
                    "sport_key": row.get("sport_key") or sport,
                    "league": row.get("sport_title") or sport,
                    "home_team": row.get("home_team") or "",
                    "away_team": row.get("away_team") or "",
                    "start_time": row.get("commence_time"),
                    "odds": old.get("odds") or {"home": 1.9, "draw": 3.2, "away": 3.8},
                    "status": "upcoming",
                    "result": None,
                    "home_score": None,
                    "away_score": None,
                    "source": "The Odds API",
                    "updated_at": to_iso(now),
                }
                self._apply_score(match, row)
                matches[match_id] = match
            source_suffix = "赔率+赛果" if sport in score_sports else "赔率"
            source_parts.append(f"{sport}({source_suffix})")
        return matches, f"The Odds API：{', '.join(source_parts)}"

    def _match_from_odds(self, row):
        home = row.get("home_team")
        away = row.get("away_team")
        if not home or not away:
            return None
        odds = self._average_h2h(row, home, away)
        if not odds:
            return None
        return {
            "id": row.get("id"),
            "sport_key": row.get("sport_key"),
            "league": row.get("sport_title") or row.get("sport_key") or "足球",
            "home_team": home,
            "away_team": away,
            "start_time": row.get("commence_time"),
            "odds": odds,
            "status": "upcoming",
            "result": None,
            "home_score": None,
            "away_score": None,
            "source": "The Odds API",
            "updated_at": to_iso(utc_now()),
        }

    def _average_h2h(self, row, home, away):
        buckets = {"home": [], "draw": [], "away": []}
        for book in row.get("bookmakers", []):
            for market in book.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name")
                    price = outcome.get("price")
                    if not isinstance(price, (int, float)):
                        continue
                    if name == home:
                        buckets["home"].append(float(price))
                    elif name == away:
                        buckets["away"].append(float(price))
                    elif str(name).lower() == "draw":
                        buckets["draw"].append(float(price))
        if not buckets["home"] or not buckets["away"]:
            return None
        if not buckets["draw"]:
            buckets["draw"].append(3.2)
        return {key: round(sum(values) / len(values), 2) for key, values in buckets.items()}

    def _apply_score(self, match, score_row):
        completed = bool(score_row.get("completed"))
        scores = score_row.get("scores") or []
        score_map = {item.get("name"): item.get("score") for item in scores}
        home_score = _safe_int(score_map.get(match["home_team"]))
        away_score = _safe_int(score_map.get(match["away_team"]))
        if home_score is not None:
            match["home_score"] = home_score
        if away_score is not None:
            match["away_score"] = away_score
        if completed and home_score is not None and away_score is not None:
            match["status"] = "completed"
            if home_score > away_score:
                match["result"] = "home"
            elif away_score > home_score:
                match["result"] = "away"
            else:
                match["result"] = "draw"
        elif parse_iso(match["start_time"]) <= utc_now():
            match["status"] = "in_progress"

    def _demo_matches(self):
        now = utc_now()
        beijing = timezone(timedelta(hours=8))
        today = now.astimezone(beijing).date()
        matches = {}
        for day_offset in range(-2, 5):
            day = today + timedelta(days=day_offset)
            for slot, hour in enumerate((18, 21)):
                team_index = (day.toordinal() + slot) % len(DEMO_TEAMS)
                home, away, league = DEMO_TEAMS[team_index]
                start_local = datetime(day.year, day.month, day.day, hour, 30, tzinfo=beijing)
                start = start_local.astimezone(timezone.utc)
                match_id = f"demo-{day.strftime('%Y%m%d')}-{slot}"
                odds = _demo_odds(match_id)
                status = "upcoming"
                result = None
                home_score = None
                away_score = None
                if now >= start + timedelta(minutes=115):
                    status = "completed"
                    home_score, away_score = _demo_score(match_id)
                    if home_score > away_score:
                        result = "home"
                    elif away_score > home_score:
                        result = "away"
                    else:
                        result = "draw"
                elif now >= start:
                    status = "in_progress"
                matches[match_id] = {
                    "id": match_id,
                    "league": league,
                    "home_team": home,
                    "away_team": away,
                    "start_time": to_iso(start),
                    "odds": odds,
                    "status": status,
                    "result": result,
                    "home_score": home_score,
                    "away_score": away_score,
                    "source": "内置演示源",
                    "updated_at": to_iso(now),
                }
        return matches, "内置演示源（配置 ODDS_API_IO_KEY 后使用 Odds-API.io）"


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_fetch_error(exc):
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
        return "HTTP 429 请求过多，可能已触发接口频率限制或额度限制"
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} {exc.reason}"
    return str(exc)


def _source_summary(matches):
    if not matches:
        return "暂无旧比赛"
    counts = {}
    for match in matches.values():
        source = match.get("source") or "未知来源"
        counts[source] = counts.get(source, 0) + 1
    return "、".join(f"{source} {count} 场" for source, count in sorted(counts.items()))


def _as_rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "events", "results", "odds"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
        values = list(payload.values())
        if values and all(isinstance(item, dict) for item in values):
            return values
    return []


def _league_name(row):
    league = row.get("league")
    if isinstance(league, dict):
        return league.get("name") or league.get("slug")
    if league:
        return str(league)
    return None


def _odds_api_io_status(status):
    normalized = str(status or "").lower()
    if normalized in ("settled", "completed", "ended", "finished"):
        return "completed"
    if normalized in ("live", "inplay", "in_progress"):
        return "in_progress"
    return "upcoming"


def _seed_int(text):
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def _demo_odds(match_id):
    rng = random.Random(_seed_int(match_id))
    home = round(rng.uniform(1.55, 2.75), 2)
    draw = round(rng.uniform(2.85, 4.05), 2)
    away = round(rng.uniform(1.75, 3.4), 2)
    return {"home": home, "draw": draw, "away": away}


def _demo_score(match_id):
    rng = random.Random(_seed_int(match_id + "-score"))
    return rng.randint(0, 4), rng.randint(0, 4)
