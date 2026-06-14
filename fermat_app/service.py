import re
import secrets
import threading
from datetime import timedelta

from .config import load_config
from .sources import MatchSource
from .store import parse_iso, read_db, to_iso, utc_now, verify_password, write_db
from .store import negative_user, normal_user


USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,24}$")
CHOICE_LABELS = {"home": "主胜", "draw": "平局", "away": "客胜"}
BALANCE_OPERATIONS = {"set": "设为", "add": "增加", "subtract": "扣减"}
LOAN_WEEKLY_RATE = 0.10
LOAN_DUE_DAYS = 14
COIN_NAME = "Fermat Coin"
_UPDATE_LOCK = threading.Lock()


class AppError(Exception):
    pass


def public_user(user):
    result = dict(user)
    result.pop("password_hash", None)
    return result


def register_user(username, password):
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise AppError("用户名只能包含字母、数字、下划线或短横线，长度 3-24。")
    if username.startswith("negative-"):
        raise AppError("用户名不能使用 negative- 前缀。")
    if len(password) < 6:
        raise AppError("密码至少 6 位。")

    def mutate(data):
        if username in data["users"]:
            raise AppError("用户名已经存在。")
        negative_name = f"negative-{username}"
        if negative_name in data["users"]:
            raise AppError("对应反向账户已经存在，请换一个用户名。")
        data["users"][username] = normal_user(username, password, approved=False)
        data["users"][negative_name] = negative_user(username)
        return True

    write_db(mutate)


def login_user(username, password):
    data = read_db()
    user = data["users"].get(username.strip())
    if not user or user.get("is_negative") or not verify_password(password, user.get("password_hash", "")):
        raise AppError("用户名或密码不正确。")
    if not user.get("approved"):
        raise AppError("账号正在等待管理员审核。")
    return public_user(user)


def get_user(username):
    data = read_db()
    user = data["users"].get(username)
    return public_user(user) if user else None


def get_dashboard(username):
    run_housekeeping()
    data = read_db()
    user = data["users"][username]
    negative = data["users"].get(user.get("negative_username"))
    user_bets = [bet for bet in data["bets"].values() if bet["username"] == username]
    negative_bets = []
    if negative:
        negative_bets = [bet for bet in data["bets"].values() if bet["username"] == negative["username"]]
    active_loans = [
        enrich_loan(loan)
        for loan in data["loans"].values()
        if loan["username"] == username and loan["status"] == "active"
    ]
    standings = sorted(
        [public_user(item) for item in data["users"].values()],
        key=lambda item: item.get("balance", 0),
        reverse=True,
    )
    return {
        "user": public_user(user),
        "negative": public_user(negative) if negative else None,
        "recent_bets": sorted(user_bets, key=lambda item: item["created_at"], reverse=True)[:8],
        "negative_recent_bets": sorted(negative_bets, key=lambda item: item["created_at"], reverse=True)[:8],
        "active_loans": active_loans,
        "standings": standings[:12],
        "meta": data["meta"],
        "matches": data["matches"],
    }


def list_matches():
    update_matches_if_due()
    data = read_db()
    return sorted(data["matches"].values(), key=lambda item: item.get("start_time") or "")


def list_user_bets(username):
    run_housekeeping()
    data = read_db()
    bets = [bet for bet in data["bets"].values() if bet.get("username") == username]
    return sorted(bets, key=lambda item: item["created_at"], reverse=True)


def place_bet(username, match_id, choice, stake):
    if choice not in CHOICE_LABELS:
        raise AppError("猜测选项无效。")
    try:
        stake = int(stake)
    except (TypeError, ValueError):
        raise AppError("猜测费马币必须是整数。")
    if stake <= 0:
        raise AppError("猜测费马币必须大于 0")

    def mutate(data):
        now = utc_now()
        user = data["users"].get(username)
        if not user or user.get("is_negative"):
            raise AppError("账号无效")
        if user.get("game_over"):
            raise AppError("账号已经费马,不能继续猜测")
        if user.get("balance", 0) < stake:
            raise AppError("费马币不足")
        match = data["matches"].get(match_id)
        if not match:
            raise AppError("比赛不存在")
        start = parse_iso(match["start_time"])
        if match.get("status") != "upcoming" or start <= now:
            raise AppError("比赛已经开始或结束，不能猜测")
        odds = float(match["odds"][choice])
        user["balance"] -= stake
        bet_id = _new_id("bet")
        data["bets"][bet_id] = {
            "id": bet_id,
            "username": username,
            "match_id": match_id,
            "choice": choice,
            "stake": stake,
            "odds": odds,
            "status": "open",
            "payout": 0,
            "created_at": to_iso(now),
            "settled_at": None,
            "mirrored_from": None,
        }
        mirrored = _place_negative_bets(data, user, match, choice, stake, bet_id, now)
        return bet_id, mirrored

    bet_id, mirrored = write_db(mutate)
    return f"猜测成功，id {bet_id}；反向账户同步 {mirrored} 笔。"


def cancel_bet(username, bet_id):
    def mutate(data):
        now = utc_now()
        user = data["users"].get(username)
        if not user or user.get("is_negative"):
            raise AppError("账号无效")
        bet = data["bets"].get(bet_id)
        if not bet or bet.get("username") != username or bet.get("mirrored_from"):
            raise AppError("猜测记录不存在或不能撤回")
        if bet.get("status") != "open":
            raise AppError("只能撤回待结算猜测")
        match = data["matches"].get(bet.get("match_id"))
        if not match:
            raise AppError("比赛不存在")
        start = parse_iso(match.get("start_time"))
        if match.get("status") != "upcoming" or not start or start <= now:
            raise AppError("比赛已经开始或结束，不能撤回")

        refunded = int(bet.get("stake", 0))
        user["balance"] += refunded
        _mark_bet_canceled(bet, now)

        mirrored = 0
        for mirror in data["bets"].values():
            if mirror.get("mirrored_from") != bet_id or mirror.get("status") != "open":
                continue
            mirror_user = data["users"].get(mirror.get("username"))
            if mirror_user:
                mirror_user["balance"] += int(mirror.get("stake", 0))
            _mark_bet_canceled(mirror, now)
            mirrored += 1
        return refunded, mirrored

    refunded, mirrored = write_db(mutate)
    return f"已撤回猜测，退回 {refunded:,} fermat coin；同步撤回反向账户 {mirrored} 笔。"


def _mark_bet_canceled(bet, now):
    bet["status"] = "canceled"
    bet["payout"] = 0
    bet["settled_at"] = to_iso(now)
    bet["canceled_at"] = to_iso(now)


def _place_negative_bets(data, user, match, choice, stake, source_bet_id, now):
    negative_name = user.get("negative_username")
    negative = data["users"].get(negative_name)
    if not negative:
        return 0
    mirror_stake = stake
    if mirror_stake <= 0:
        return 0
    if choice == "home":
        choices = [("away", mirror_stake)]
    elif choice == "away":
        choices = [("home", mirror_stake)]
    else:
        first = mirror_stake // 2
        second = mirror_stake - first
        choices = [("home", first), ("away", second)]
    count = 0
    for mirror_choice, mirror_amount in choices:
        if mirror_amount <= 0:
            continue
        negative["balance"] -= mirror_amount
        bet_id = _new_id("bet")
        data["bets"][bet_id] = {
            "id": bet_id,
            "username": negative["username"],
            "match_id": match["id"],
            "choice": mirror_choice,
            "stake": mirror_amount,
            "odds": float(match["odds"][mirror_choice]),
            "status": "open",
            "payout": 0,
            "created_at": to_iso(now),
            "settled_at": None,
            "mirrored_from": source_bet_id,
        }
        count += 1
    return count


def update_matches(force=False):
    if not force and not _update_due():
        return
    if not _UPDATE_LOCK.acquire(blocking=False):
        return
    try:
        if not force and not _update_due():
            return
        source = MatchSource()
        snapshot = read_db()
        fetched, source_label = source.fetch(snapshot["matches"], _score_sports_for_open_bets(snapshot))

        def mutate(data):
            now = utc_now()
            for match_id, match in fetched.items():
                old = data["matches"].get(match_id, {})
                merged = dict(old)
                merged.update(match)
                if not match.get("odds") and old.get("odds"):
                    merged["odds"] = old["odds"]
                data["matches"][match_id] = merged
            for match in data["matches"].values():
                if match.get("status") != "completed" and parse_iso(match.get("start_time")) <= now:
                    match["status"] = "in_progress"
            data["meta"]["last_match_update"] = to_iso(now)
            data["meta"]["match_source"] = source_label
            settle_open_bets(data)
            audit_loans(data)
            return True

        write_db(mutate)
        _record_all_nets()
    finally:
        _UPDATE_LOCK.release()


def update_matches_if_due():
    update_matches(force=False)


def _update_due():
    data = read_db()
    config = load_config()
    source = str(data["meta"].get("match_source", ""))
    configured_sources = []
    if config.get("odds_api_io_key"):
        configured_sources.append("Odds-API.io")
    if config.get("the_odds_api_key"):
        configured_sources.append("The Odds API")
    if configured_sources and not all(item in source for item in configured_sources):
        return True
    last = data["meta"].get("last_match_update")
    if not last:
        return True
    return utc_now() - parse_iso(last) >= timedelta(minutes=config["update_minutes"])


def _score_sports_for_open_bets(data):
    sports = set()
    now = utc_now()
    for bet in data["bets"].values():
        if bet.get("status") != "open":
            continue
        match = data["matches"].get(bet["match_id"])
        if not match or not match.get("start_time"):
            continue
        if parse_iso(match["start_time"]) <= now:
            sports.add(match.get("sport_key") or "soccer_epl")
    return sports


def settle_open_bets(data):
    now = utc_now()
    for bet in data["bets"].values():
        if bet.get("status") != "open":
            continue
        match = data["matches"].get(bet["match_id"])
        if not match or match.get("status") != "completed" or not match.get("result"):
            continue
        user = data["users"].get(bet["username"])
        if not user:
            bet["status"] = "void"
            bet["settled_at"] = to_iso(now)
            continue
        if bet["choice"] == match["result"]:
            payout = int(round(bet["stake"] * bet["odds"]))
            user["balance"] += payout
            bet["status"] = "won"
            bet["payout"] = payout
        else:
            bet["status"] = "lost"
            bet["payout"] = 0
        bet["settled_at"] = to_iso(now)


def run_housekeeping():
    def mutate(data):
        settle_open_bets(data)
        audit_loans(data)

    write_db(mutate)
    _record_all_nets()


def approve_user(admin_username, target_username):
    def mutate(data):
        admin = data["users"].get(admin_username)
        target = data["users"].get(target_username)
        if not admin or admin.get("role") != "admin":
            raise AppError("需要管理员权限。")
        if not target or target.get("is_negative"):
            raise AppError("账号不存在或不能审核反向账户。")
        target["approved"] = True
        target["approved_at"] = to_iso(utc_now())
        return True

    write_db(mutate)


def delete_user(admin_username, target_username):
    target_username = (target_username or "").strip()
    if not target_username:
        raise AppError("请选择要删除的账号。")

    def mutate(data):
        admin = data["users"].get(admin_username)
        target = data["users"].get(target_username)
        if not admin or admin.get("role") != "admin":
            raise AppError("需要管理员权限。")
        if not target:
            raise AppError("账号不存在。")
        if target.get("role") == "admin":
            raise AppError("不能删除管理员账号。")

        usernames = {target_username}
        if target.get("is_negative"):
            owner = data["users"].get(target.get("owner_username"))
            if owner and owner.get("negative_username") == target_username:
                owner["negative_username"] = None
        else:
            negative_username = target.get("negative_username") or f"negative-{target_username}"
            negative = data["users"].get(negative_username)
            if negative and negative.get("is_negative") and negative.get("owner_username") == target_username:
                usernames.add(negative_username)
            for username, user in data["users"].items():
                if user.get("is_negative") and user.get("owner_username") == target_username:
                    usernames.add(username)

        for username in usernames:
            data["users"].pop(username, None)

        data["bets"] = {
            bet_id: bet
            for bet_id, bet in data.get("bets", {}).items()
            if bet.get("username") not in usernames
        }
        data["loans"] = {
            loan_id: loan
            for loan_id, loan in data.get("loans", {}).items()
            if loan.get("username") not in usernames
        }
        return sorted(usernames)

    deleted = write_db(mutate)
    return f"已删除账号：{', '.join(deleted)}。"


def set_admin(admin_username, target_username):
    target_username = (target_username or "").strip()
    if not target_username:
        raise AppError("请选择目标账号。")

    def mutate(data):
        admin = data["users"].get(admin_username)
        target = data["users"].get(target_username)
        if not admin or admin.get("role") != "admin":
            raise AppError("需要管理员权限。")
        if not target or target.get("is_negative"):
            raise AppError("目标账号无效。")
        target["role"] = "admin"
        return True

    write_db(mutate)
    return f"已设置 {target_username} 为管理员。"


def manual_settle_match(admin_username, match_id, home_score, away_score):
    try:
        home_score = int(home_score)
        away_score = int(away_score)
    except (TypeError, ValueError):
        raise AppError("比分必须是整数。")
        
    def mutate(data):
        admin = data["users"].get(admin_username)
        if not admin or admin.get("role") != "admin":
            raise AppError("需要管理员权限。")
        match = data["matches"].get(match_id)
        if not match:
            raise AppError("比赛不存在。")
        
        match["home_score"] = home_score
        match["away_score"] = away_score
        if home_score > away_score:
            match["result"] = "home"
        elif home_score < away_score:
            match["result"] = "away"
        else:
            match["result"] = "draw"
        
        match["status"] = "completed"
        
        settle_open_bets(data)
        return True

    write_db(mutate)
    _record_all_nets()
    return "比赛已手动结算。"


def manual_add_match(admin_username, home_team, away_team, start_time, home_odds, draw_odds, away_odds):
    home_team = (home_team or "").strip()
    away_team = (away_team or "").strip()
    if not home_team or not away_team:
        raise AppError("队名不能为空。")
    try:
        home_odds = float(home_odds)
        draw_odds = float(draw_odds)
        away_odds = float(away_odds)
    except (TypeError, ValueError):
        raise AppError("赔率必须是数字。")

    try:
        # validate iso format
        dt = parse_iso(start_time)
        iso_time = to_iso(dt)
    except Exception:
        raise AppError("比赛时间不正确。")

    def mutate(data):
        admin = data["users"].get(admin_username)
        if not admin or admin.get("role") != "admin":
            raise AppError("需要管理员权限。")
        
        match_id = _new_id("match")
        data["matches"][match_id] = {
            "id": match_id,
            "home_team": home_team,
            "away_team": away_team,
            "start_time": iso_time,
            "status": "upcoming",
            "odds": {
                "home": str(home_odds),
                "draw": str(draw_odds),
                "away": str(away_odds)
            },
            "sport_key": "manual",
            "league": "手动添加",
            "source": "手动添加"
        }
        return True
    
    write_db(mutate)
    return "已成功手动添加比赛。"


def delete_match(admin_username, match_id):
    def mutate(data):
        admin = data["users"].get(admin_username)
        if not admin or admin.get("role") != "admin":
            raise AppError("需要管理员权限。")
        match = data["matches"].get(match_id)
        if not match:
            raise AppError("比赛不存在。")
        
        now = utc_now()
        voided = 0
        for bet in data.get("bets", {}).values():
            if bet.get("match_id") == match_id and bet.get("status") == "open":
                user = data["users"].get(bet["username"])
                if user:
                    user["balance"] += int(bet.get("stake", 0))
                bet["status"] = "void"
                bet["settled_at"] = to_iso(now)
                voided += 1

        del data["matches"][match_id]
        return voided

    voided = write_db(mutate)
    return f"已删除比赛，并作废退款了 {voided} 笔关联且未结算的猜测记录。"


def delete_demo_matches():
    def mutate(data):
        demo_match_ids = {
            match_id
            for match_id, match in data.get("matches", {}).items()
            if match_id.startswith("demo-") or match.get("source") == "内置演示源"
        }
        if not demo_match_ids:
            return 0, 0

        old_bet_count = len(data.get("bets", {}))
        data["matches"] = {
            match_id: match
            for match_id, match in data.get("matches", {}).items()
            if match_id not in demo_match_ids
        }
        data["bets"] = {
            bet_id: bet
            for bet_id, bet in data.get("bets", {}).items()
            if bet.get("match_id") not in demo_match_ids
        }
        return len(demo_match_ids), old_bet_count - len(data.get("bets", {}))

    return write_db(mutate)


def adjust_balance(admin_username, target_username, operation, amount, note=""):
    operation = (operation or "").strip()
    target_username = (target_username or "").strip()
    note = (note or "").strip()[:120]
    if operation not in BALANCE_OPERATIONS:
        raise AppError("余额调整方式无效。")
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise AppError("调整费马币必须是整数。")
    if amount < 0 and operation != "set":
        raise AppError("增加或扣减的费马币不能为负数。")
    if operation != "set" and amount == 0:
        raise AppError("增加或扣减费马币必须大于 0。")

    def mutate(data):
        admin = data["users"].get(admin_username)
        target = data["users"].get(target_username)
        if not admin or admin.get("role") != "admin":
            raise AppError("需要管理员权限。")
        if not target:
            raise AppError("目标账户不存在。")
        old_balance = int(target.get("balance", 0))
        if operation == "set":
            new_balance = amount
        elif operation == "add":
            new_balance = old_balance + amount
        else:
            new_balance = old_balance - amount
            if new_balance < 0 and not target.get("is_negative"):
                raise AppError("扣减后余额不能低于 0。")
        target["balance"] = new_balance
        adjustment_id = _new_id("adjust")
        data["balance_adjustments"][adjustment_id] = {
            "id": adjustment_id,
            "admin_username": admin_username,
            "target_username": target_username,
            "operation": operation,
            "amount": amount,
            "old_balance": old_balance,
            "new_balance": new_balance,
            "note": note,
            "created_at": to_iso(utc_now()),
        }
        return adjustment_id

    adjustment_id = write_db(mutate)
    _record_net_for(target_username)
    return f"余额已调整，记录编号 {adjustment_id}。"


def loan_limit(user):
    if user.get("game_over") or user.get("credit", 0) <= 0:
        return 0
    base = max(20_000, int(user.get("balance", 0)) * 10)
    return int(base * (int(user.get("credit", 0)) / 100))


def borrow(username, amount):
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise AppError("借款费马币必须是整数。")
    if amount <= 0:
        raise AppError("借款费马币必须大于 0。")

    def mutate(data):
        now = utc_now()
        user = data["users"].get(username)
        if not user or user.get("is_negative"):
            raise AppError("账号无效。")
        if any(loan["username"] == username and loan["status"] == "active" for loan in data["loans"].values()):
            raise AppError("还有未还清贷款，不能再次借款。")
        limit = loan_limit(user)
        if amount > limit:
            raise AppError(f"超过当前可贷额度 {limit:,} fermat coin。")
        user["balance"] += amount
        loan_id = _new_id("loan")
        data["loans"][loan_id] = {
            "id": loan_id,
            "username": username,
            "principal": amount,
            "paid_amount": 0,
            "weekly_rate": LOAN_WEEKLY_RATE,
            "borrowed_at": to_iso(now),
            "due_at": to_iso(now + timedelta(days=LOAN_DUE_DAYS)),
            "status": "active",
            "closed_at": None,
        }
        return loan_id

    loan_id = write_db(mutate)
    _record_net_for(username)
    return f"借款成功，贷款编号 {loan_id}。"


def repay(username, amount):
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise AppError("还款费马币必须是整数。")
    if amount <= 0:
        raise AppError("还款费马币必须大于 0。")

    def mutate(data):
        user = data["users"].get(username)
        if not user or user.get("is_negative"):
            raise AppError("账号无效。")
        active = [
            loan
            for loan in data["loans"].values()
            if loan["username"] == username and loan["status"] == "active"
        ]
        if not active:
            raise AppError("没有需要偿还的贷款。")
        loan = sorted(active, key=lambda item: item["borrowed_at"])[0]
        due = current_loan_due(loan)
        pay_amount = min(amount, due)
        if user.get("balance", 0) < pay_amount:
            raise AppError("余额不足。")
        user["balance"] -= pay_amount
        loan["paid_amount"] += pay_amount
        if current_loan_due(loan) <= 0:
            loan["status"] = "paid"
            loan["closed_at"] = to_iso(utc_now())
            user["credit"] = min(100, int(user.get("credit", 100)) + 10)
        return pay_amount

    paid = write_db(mutate)
    _record_net_for(username)
    return f"还款成功，已还 {paid:,} fermat coin。"


def current_loan_due(loan):
    borrowed_at = parse_iso(loan["borrowed_at"])
    days = max(0, (utc_now() - borrowed_at).days)
    weeks = min(2, days // 7)
    total = int(round(loan["principal"] * (1 + LOAN_WEEKLY_RATE * weeks)))
    return max(0, total - int(loan.get("paid_amount", 0)))


def enrich_loan(loan):
    item = dict(loan)
    item["current_due"] = current_loan_due(loan)
    item["due_days_left"] = max(0, (parse_iso(loan["due_at"]) - utc_now()).days)
    return item


def audit_loans(data):
    now = utc_now()
    for loan in data["loans"].values():
        if loan.get("status") != "active":
            continue
        if parse_iso(loan["due_at"]) <= now and current_loan_due(loan) > 0:
            loan["status"] = "defaulted"
            loan["closed_at"] = to_iso(now)
            user = data["users"].get(loan["username"])
            if user:
                user["credit"] = 0
                user["game_over"] = True


def admin_snapshot():
    update_matches_if_due()
    data = read_db()
    pending = [
        public_user(user)
        for user in data["users"].values()
        if not user.get("is_negative") and not user.get("approved")
    ]
    users = [public_user(user) for user in data["users"].values()]
    loans = [enrich_loan(loan) for loan in data["loans"].values()]
    adjustments = list(data.get("balance_adjustments", {}).values())
    bets = list(data.get("bets", {}).values())
    return {
        "pending": sorted(pending, key=lambda item: item["created_at"]),
        "users": sorted(users, key=lambda item: item["username"]),
        "loans": sorted(loans, key=lambda item: item["borrowed_at"], reverse=True),
        "adjustments": sorted(adjustments, key=lambda item: item["created_at"], reverse=True)[:20],
        "bets": sorted(bets, key=lambda item: item["created_at"], reverse=True),
        "meta": data["meta"],
        "matches": data["matches"],
    }


def all_bets_snapshot():
    update_matches_if_due()
    data = read_db()
    bets = list(data.get("bets", {}).values())
    return {
        "bets": sorted(bets, key=lambda item: item["created_at"], reverse=True),
        "matches": data["matches"],
    }


def leaderboard_snapshot():
    run_housekeeping()
    data = read_db()

    # 统计每个用户活跃贷款应还总额
    user_loan_due = {}
    for loan in data.get("loans", {}).values():
        if loan.get("status") == "active":
            username = loan["username"]
            user_loan_due[username] = user_loan_due.get(username, 0) + current_loan_due(loan)

    # 统计每个用户未结算下注总额（open 状态的 bet）
    user_open_bets = {}
    for bet in data.get("bets", {}).values():
        if bet.get("status") == "open":
            username = bet["username"]
            user_open_bets[username] = user_open_bets.get(username, 0) + int(bet.get("stake", 0))

    users = []
    for u in data["users"].values():
        item = public_user(u)
        username = item["username"]
        loan_due = user_loan_due.get(username, 0)
        open_stakes = user_open_bets.get(username, 0)
        item["loan_due"] = loan_due
        item["open_stakes"] = open_stakes
        # 净资产 = 当前余额 - 贷款应还 + 未结算下注
        item["net_asset"] = item["balance"] - loan_due + open_stakes
        users.append(item)

    by_balance = sorted(users, key=lambda it: it.get("balance", 0), reverse=True)
    by_net = sorted(users, key=lambda it: it.get("net_asset", 0), reverse=True)
    return by_balance, by_net


def compute_net_asset(username, data):
    """计算用户当前净资产 = 余额 - 贷款应还 + 未结算下注"""
    balance = data["users"].get(username, {}).get("balance", 0)
    loan_due = 0
    for loan in data.get("loans", {}).values():
        if loan.get("username") == username and loan.get("status") == "active":
            loan_due += current_loan_due(loan)
    open_stakes = 0
    for bet in data.get("bets", {}).values():
        if bet.get("username") == username and bet.get("status") == "open":
            open_stakes += int(bet.get("stake", 0))
    return balance - loan_due + open_stakes


def record_net_asset_snapshot(username, current_net):
    """记录净资产快照（值变化时才记录），最多保留 200 条"""
    def mutate(data):
        history = data.setdefault("net_asset_history", {}).setdefault(username, [])
        if not history or history[-1]["v"] != current_net:
            history.append({"t": to_iso(utc_now()), "v": current_net})
            if len(history) > 200:
                history[:] = history[-200:]
            return True
        return False
    return write_db(mutate)


def build_poster_data(username, data, current_amount=None):
    """构建海报数据，排名只统计非反向用户。"""
    user = data["users"].get(username)
    if not user:
        raise AppError("用户不存在")

    current = compute_net_asset(username, data) if current_amount is None else int(current_amount)
    ranked_players = []
    for player_name, player in data["users"].items():
        if player.get("is_negative"):
            continue
        ranked_players.append((player_name, compute_net_asset(player_name, data)))
    ranked_players.sort(key=lambda item: (item[1], item[0]), reverse=True)

    rank = next(
        (index + 1 for index, item in enumerate(ranked_players) if item[0] == username),
        len(ranked_players) + 1,
    )
    history = _poster_history(data.get("net_asset_history", {}).get(username, []))

    return {
        "nickname": username,
        "currentAmount": current,
        "coinName": COIN_NAME,
        "history": history,
        "rank": rank,
        "totalPlayers": len(ranked_players),
        # Legacy fields kept for current callers and older templates.
        "username": username,
        "current_net_asset": current,
        "balance": user["balance"],
    }


def _poster_history(raw_history):
    history = []
    for item in raw_history:
        date = item.get("date") or item.get("t")
        amount = item.get("amount")
        if amount is None:
            amount = item.get("v")
        if not date or amount is None:
            continue
        history.append({"date": date, "amount": int(amount)})
    return sorted(history, key=lambda item: item["date"])


def get_poster_data(username):
    """获取用户海报所需数据"""
    run_housekeeping()
    data = read_db()
    if username not in data["users"]:
        raise AppError("用户不存在")
    current_net = compute_net_asset(username, data)
    record_net_asset_snapshot(username, current_net)
    # 重新读取获取最新 history
    data = read_db()
    return build_poster_data(username, data, current_net)


def _record_net_for(username):
    """记录单个用户的净资产快照（值变化时才写入）"""
    data = read_db()
    current_net = compute_net_asset(username, data)
    record_net_asset_snapshot(username, current_net)


def _record_all_nets():
    """记录所有非负向用户的净资产快照（值变化时才写入）"""
    data = read_db()
    for username, user in data["users"].items():
        if user.get("is_negative"):
            continue
        current_net = compute_net_asset(username, data)
        record_net_asset_snapshot(username, current_net)


def _new_id(prefix):
    return f"{prefix}_{secrets.token_hex(6)}"
