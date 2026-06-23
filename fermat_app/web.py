import html
import hmac
import json
import mimetypes
import os
import urllib.parse
from datetime import timedelta
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from . import service
from .store import ADMIN_USERNAME, ROOT_DIR, export_sqlite_bytes, parse_iso, read_db, utc_now


PORT = int(os.environ.get("PORT", "3008"))
HOST = os.environ.get("HOST", "0.0.0.0")
SESSION_DAYS = 7
STATIC_DIR = ROOT_DIR / "static"


def run_server():
    server = ThreadingHTTPServer((HOST, PORT), FermatHandler)
    print(f"Fermat Coin 足球站已启动：http://127.0.0.1:{PORT}/")
    server.serve_forever()


class FermatHandler(BaseHTTPRequestHandler):
    server_version = "FermatCoinFootball/1.0"

    def do_GET(self):
        try:
            self.route_get()
        except service.AppError as exc:
            self.redirect("/", error=str(exc))
        except Exception as exc:
            self.render_error(exc)

    def do_POST(self):
        try:
            self.route_post()
        except service.AppError as exc:
            self.redirect(self.headers.get("Referer") or "/", error=str(exc))
        except Exception as exc:
            self.render_error(exc)

    def route_get(self):
        path, query = split_url(self.path)
        user = self.current_user()
        if path.startswith("/static/"):
            return self.serve_static(path)
        if path == "/admin/download-db":
            self.require_admin(user)
            return self.download_db()
        service.update_matches_if_due()
        if path == "/":
            if user:
                return self.redirect("/dashboard")
            return self.render_login(query)
        if path == "/login":
            return self.render_login(query)
        if path == "/register":
            return self.render_register(query)
        if path == "/dashboard":
            self.require_user(user)
            return self.render_dashboard(user, query)
        if path == "/matches":
            self.require_user(user)
            return self.render_matches(user, query)
        if path == "/loans":
            self.require_user(user)
            return self.render_loans(user, query)
        if path == "/leaderboard":
            self.require_user(user)
            return self.render_leaderboard(user, query)
        if path == "/all-bets":
            self.require_user(user)
            return self.render_all_bets(user, query)
        if path == "/poster":
            self.require_user(user)
            return self.render_poster(user, query)
        if path == "/admin":
            self.require_admin(user)
            return self.render_admin(user, query)
        self.send_error(HTTPStatus.NOT_FOUND)

    def route_post(self):
        path, _ = split_url(self.path)
        form = self.read_form()
        user = self.current_user()
        if path == "/login":
            logged_in = service.login_user(form.get("username", ""), form.get("password", ""))
            self.set_session(logged_in["username"])
            return self.redirect("/dashboard", message="登录成功。")
        if path == "/register":
            service.register_user(form.get("username", ""), form.get("password", ""))
            return self.redirect("/login", message="注册成功，请等待管理员审核。")
        if path == "/logout":
            self.clear_session()
            return self.redirect("/login", message="已退出登录。")
        self.require_user(user)
        if path == "/bet":
            msg = service.place_bet(user["username"], form.get("match_id", ""), form.get("choice", ""), form.get("stake", ""))
            return self.redirect("/matches", message=msg)
        if path == "/bet/cancel":
            msg = service.cancel_bet(user["username"], form.get("bet_id", ""))
            return self.redirect(self.headers.get("Referer") or "/matches", message=msg)
        if path == "/loan/borrow":
            msg = service.borrow(user["username"], form.get("amount", ""))
            return self.redirect("/loans", message=msg)
        if path == "/loan/repay":
            msg = service.repay(user["username"], form.get("amount", ""))
            return self.redirect("/loans", message=msg)
        if path == "/admin/approve":
            self.require_admin(user)
            service.approve_user(user["username"], form.get("username", ""))
            return self.redirect("/admin", message="账号已通过。")
        if path == "/admin/delete-user":
            self.require_admin(user)
            msg = service.delete_user(user["username"], form.get("username", ""))
            return self.redirect("/admin", message=msg)
        if path == "/admin/balance":
            self.require_admin(user)
            msg = service.adjust_balance(
                user["username"],
                form.get("username", ""),
                form.get("operation", ""),
                form.get("amount", ""),
                form.get("note", ""),
            )
            return self.redirect("/admin", message=msg)
        if path == "/admin/refresh":
            self.require_admin(user)
            service.update_matches(force=True)
            return self.redirect("/admin", message="已手动刷新 API 数据。")
        if path == "/admin/set-admin":
            self.require_admin(user)
            msg = service.set_admin(user["username"], form.get("username", ""))
            return self.redirect("/admin", message=msg)
        if path == "/admin/demote-admin":
            self.require_admin(user)
            msg = service.demote_admin(user["username"], form.get("username", ""))
            return self.redirect("/admin", message=msg)
        if path == "/admin/settle-match":
            self.require_admin(user)
            msg = service.manual_settle_match(
                user["username"],
                form.get("match_id", ""),
                form.get("home_score", ""),
                form.get("away_score", "")
            )
            return self.redirect("/admin", message=msg)
        if path == "/admin/add-match":
            self.require_admin(user)
            msg = service.manual_add_match(
                user["username"],
                form.get("home_team", ""),
                form.get("away_team", ""),
                form.get("start_time", ""),
                form.get("home_odds", ""),
                form.get("draw_odds", ""),
                form.get("away_odds", "")
            )
            return self.redirect("/admin", message=msg)
        if path == "/admin/delete-match":
            self.require_admin(user)
            msg = service.delete_match(user["username"], form.get("match_id", ""))
            return self.redirect("/admin", message=msg)
        if path == "/admin/leaderboards/create":
            self.require_admin(user)
            msg = service.create_custom_leaderboard(
                user["username"],
                form.get("name", ""),
                form.get("metric", ""),
            )
            return self.redirect("/admin", message=msg)
        if path == "/admin/leaderboards/delete":
            self.require_admin(user)
            msg = service.delete_custom_leaderboard(user["username"], form.get("leaderboard_id", ""))
            return self.redirect("/admin", message=msg)
        if path == "/admin/leaderboards/add-user":
            self.require_admin(user)
            msg = service.add_custom_leaderboard_user(
                user["username"],
                form.get("leaderboard_id", ""),
                form.get("username", ""),
            )
            return self.redirect("/admin", message=msg)
        if path == "/admin/leaderboards/remove-user":
            self.require_admin(user)
            msg = service.remove_custom_leaderboard_user(
                user["username"],
                form.get("leaderboard_id", ""),
                form.get("username", ""),
            )
            return self.redirect("/admin", message=msg)
        self.send_error(HTTPStatus.NOT_FOUND)

    def render_login(self, query):
        body = f"""
        <section class="auth-panel">
          <div>
            <p class="eyebrow">Fermat Coin</p>
            <h1>费马的游戏</h1>
            <p class="muted"></p>
          </div>
          <form method="post" action="/login" class="form-card">
            <label>用户名<input name="username" autocomplete="username" required></label>
            <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
            <button type="submit">登录</button>
            <a class="secondary-link" href="/register">注册新账号</a>
          </form>
        </section>
        """
        self.send_html(layout("登录", body, None, query))

    def render_register(self, query):
        body = """
        <section class="auth-panel">
          <div>
            <p class="eyebrow">注册</p>
            <h1>创建账户</h1>
            <p class="muted">注册后系统会自动创建同名反向账户，管理员通过后才能登录。</p>
          </div>
          <form method="post" action="/register" class="form-card">
            <label>用户名<input name="username" minlength="3" maxlength="24" required></label>
            <label>密码<input name="password" type="password" minlength="6" required></label>
            <button type="submit">提交注册</button>
            <a class="secondary-link" href="/login">返回登录</a>
          </form>
        </section>
        """
        self.send_html(layout("注册", body, None, query))

    def render_dashboard(self, user, query):
        snapshot = service.get_dashboard(user["username"])
        real = snapshot["user"]
        negative = snapshot["negative"]
        active_loans = snapshot["active_loans"]
        body = f"""
        <section class="page-head">
          <div>
            <p class="eyebrow">账户总览</p>
            <h1>{e(real['username'])}</h1>
          </div>
          <div class="head-actions">
            <span class="pill">拉取状态：{e(snapshot['meta'].get('match_source', '未更新'))}</span>
          </div>
        </section>
        <section class="metric-grid">
          {metric_card('主账户余额', money(real['balance']), 'fermat coin')}
          {metric_card('信用', str(real.get('credit', 0)), '100 为满分')}
          {metric_card('反向账户', money(negative['balance']) if negative else '-', negative['username'] if negative else '未创建')}
          {metric_card('状态', 'Game Over' if real.get('game_over') else '正常', '逾期两周未还会出局')}
        </section>
        <section class="two-col">
          <div class="panel">
            <div class="panel-title"><h2>最近猜测</h2><a href="/matches">去猜测</a></div>
            {bets_table(snapshot['recent_bets'], snapshot['matches'], allow_cancel=True)}
          </div>
          <div class="panel">
            <div class="panel-title"><h2>反向账户最近猜测</h2></div>
            {bets_table(snapshot['negative_recent_bets'], snapshot['matches'])}
          </div>
        </section>
        <section class="two-col">
          <div class="panel">
            <div class="panel-title"><h2>贷款</h2><a href="/loans">管理贷款</a></div>
            {loan_summary(active_loans)}
          </div>
          <div class="panel">
            <div class="panel-title"><h2>排行榜</h2></div>
            {standings_table(snapshot['standings'])}
          </div>
        </section>
        """
        self.send_html(layout("账户总览", body, user, query))

    def render_matches(self, user, query):
        matches = service.list_matches()
        fresh_user = service.get_user(user["username"]) or user
        user_balance = int(fresh_user.get("balance", 0))
        user_bets = service.list_user_bets(user["username"])
        matches_by_id = {match["id"]: match for match in matches}
        upcoming = [m for m in matches if m["status"] == "upcoming"]
        running = [m for m in matches if m["status"] == "in_progress"]
        completed = [m for m in matches if m["status"] == "completed"]
        body = f"""
        <section class="page-head">
          <div>
            <p class="eyebrow">比赛</p>
            <h1>选择未开赛比赛猜测</h1>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title"><h2>我的猜测</h2></div>
          {bets_table(user_bets, matches_by_id, allow_cancel=True, show_time=True)}
        </section>
        <section class="match-list">
          <h2>可猜测</h2>
          {''.join(match_card(match, allow_bet=True, user_balance=user_balance) for match in upcoming) or empty_state('暂无可猜测比赛')}
        </section>
        <section class="match-list compact-list">
          <h2>进行中</h2>
          {''.join(match_card(match, allow_bet=False) for match in running) or empty_state('暂无进行中比赛')}
        </section>
        <section class="match-list compact-list">
          <h2>已结束</h2>
          {''.join(match_card(match, allow_bet=False) for match in completed[-12:]) or empty_state('暂无已结束比赛')}
        </section>
        """
        self.send_html(layout("比赛", body, user, query))

    def render_loans(self, user, query):
        service.run_housekeeping()
        data = read_db()
        real = data["users"][user["username"]]
        active = [
            service.enrich_loan(loan)
            for loan in data["loans"].values()
            if loan["username"] == user["username"] and loan["status"] == "active"
        ]
        limit = service.loan_limit(real)
        repay_due = sum(int(loan.get("current_due", 0)) for loan in active)
        repay_amount = min(repay_due, int(real.get("balance", 0)))
        body = f"""
        <section class="page-head">
          <div>
            <p class="eyebrow">银行借贷</p>
            <h1>信用与复活机会</h1>
          </div>
        </section>
        <section class="metric-grid">
          {metric_card('当前余额', money(real['balance']), 'fermat coin')}
          {metric_card('信用', str(real.get('credit', 0)), '影响可贷额度')}
          {metric_card('可贷额度', money(limit), 'max(2万, 当前本金 x 10)')}
        </section>
        <section class="two-col">
          <form class="panel form-card inline-form" method="post" action="/loan/borrow">
            <h2>借款</h2>
            <label>费马币<input name="amount" type="number" min="1" max="{limit}" value="{limit if limit else 0}" required></label>
            <button type="submit" {'disabled' if active or limit <= 0 else ''}>确认借款</button>
          </form>
          <form class="panel form-card inline-form" method="post" action="/loan/repay">
            <h2>还款</h2>
            <label>费马币<input name="amount" type="number" min="1" max="{repay_amount if repay_amount else 1}" value="{repay_amount}" required></label>
            <button type="submit" {'disabled' if not active else ''}>确认还款</button>
          </form>
        </section>
        <section class="panel">
          <div class="panel-title"><h2>当前贷款</h2></div>
          {loans_table(active)}
        </section>
        """
        self.send_html(layout("借贷", body, user, query))

    def render_leaderboard(self, user, query):
        by_balance, by_net, custom_leaderboards = service.leaderboard_snapshot()
        requested_tab = first_query(query, "tab") or "balance"
        show_negative = first_query(query, "show_negative") == "1"
        visible_by_balance = by_balance if show_negative else [item for item in by_balance if not item.get("is_negative")]
        visible_by_net = by_net if show_negative else [item for item in by_net if not item.get("is_negative")]
        custom_tabs = {f"custom-{item['id']}" for item in custom_leaderboards}
        tab = requested_tab if requested_tab in {"balance", "net"} | custom_tabs else "balance"
        negative_toggle_href = add_query("/leaderboard", {
            "tab": tab,
            "show_negative": "" if show_negative else "1",
        })
        negative_toggle_text = "隐藏反向账户" if show_negative else "显示反向账户"
        bal_active = "active" if tab == "balance" else ""
        net_active = "active" if tab == "net" else ""

        top_bal = visible_by_balance[:3]
        bal_cards = "".join(
            metric_card(f"第 {idx} 名", item["username"], f"{money(item['balance'])} fermat coin")
            for idx, item in enumerate(top_bal, 1)
        ) or metric_card("富豪榜", "暂无账户", "等待用户注册")

        top_net = visible_by_net[:3]
        net_cards = "".join(
            metric_card(f"第 {idx} 名", item["username"], f"净资产 {money(item['net_asset'])} fermat coin")
            for idx, item in enumerate(top_net, 1)
        ) or metric_card("净资产榜", "暂无账户", "等待用户注册")

        custom_tab_buttons = []
        custom_sections = []
        for leaderboard in custom_leaderboards:
            tab_key = f"custom-{leaderboard['id']}"
            active = "active" if tab == tab_key else ""
            metric = leaderboard["metric"]
            users = leaderboard["users"]
            top_users = users[:3]
            cards = "".join(
                metric_card(
                    f"第 {idx} 名",
                    item["username"],
                    f"{leaderboard['metric_label']} {money(item[metric])} fermat coin",
                )
                for idx, item in enumerate(top_users, 1)
            ) or metric_card(leaderboard["name"], "暂无账户", "等待管理员添加")
            table = (
                net_asset_standings_table(users)
                if metric == "net_asset"
                else standings_table(users)
            ) if users else empty_state("暂无参与用户")
            custom_tab_buttons.append(
                f'<button class="tab-item {active}" data-tab="{e(tab_key)}">{e(leaderboard["name"])}</button>'
            )
            custom_sections.append(f"""
        <section class="tab-content {active}" data-tab-content="{e(tab_key)}">
          <section class="metric-grid podium-grid">
            {cards}
          </section>
          <section class="panel">
            <div class="panel-title"><h2>完整榜单 · {e(leaderboard["metric_label"])}</h2></div>
            {table}
          </section>
        </section>
            """)

        body = f"""
        <section class="page-head">
          <div>
            <p class="eyebrow">排行榜</p>
            <h1>Fermat Coin 排行</h1>
          </div>
          <div class="head-actions">
            <a class="button-link" href="/all-bets">全站猜测记录</a>
            <a class="button-link secondary" href="{negative_toggle_href}">{negative_toggle_text}</a>
          </div>
        </section>
        <div class="tab-bar">
          <button class="tab-item {bal_active}" data-tab="balance">富豪榜（余额）</button>
          <button class="tab-item {net_active}" data-tab="net">净资产榜</button>
          {''.join(custom_tab_buttons)}
        </div>
        <section class="tab-content {bal_active}" data-tab-content="balance">
          <section class="metric-grid podium-grid">
            {bal_cards}
          </section>
          <section class="panel">
            <div class="panel-title"><h2>完整榜单</h2></div>
            {standings_table(visible_by_balance)}
          </section>
        </section>
        <section class="tab-content {net_active}" data-tab-content="net">
          <section class="metric-grid podium-grid">
            {net_cards}
          </section>
          <section class="panel">
            <div class="panel-title"><h2>完整榜单</h2></div>
            {net_asset_standings_table(visible_by_net)}
          </section>
        </section>
        {''.join(custom_sections)}
        <script>
        (function () {{
          var tabs = document.querySelectorAll('.tab-item');
          var contents = document.querySelectorAll('[data-tab-content]');
          function activate(name) {{
            tabs.forEach(function (t) {{ t.classList.remove('active'); }});
            contents.forEach(function (content) {{
              content.classList.remove('active');
            }});
            var btn = document.querySelector('.tab-item[data-tab="' + name + '"]');
            if (btn) btn.classList.add('active');
            contents.forEach(function (content) {{
              if (content.getAttribute('data-tab-content') === name) {{
                content.classList.add('active');
              }}
            }});
          }}
          tabs.forEach(function (tab) {{
            tab.addEventListener('click', function () {{
              activate(this.getAttribute('data-tab'));
            }});
          }});
        }})();
        </script>
        """
        self.send_html(layout("排行榜", body, user, query))

    def render_all_bets(self, user, query):
        snapshot = service.all_bets_snapshot()
        selected_username = first_query(query, "username").strip()
        usernames = sorted({bet.get("username", "") for bet in snapshot["bets"] if bet.get("username")})
        filtered_bets = [
            bet for bet in snapshot["bets"]
            if not selected_username or bet.get("username") == selected_username
        ]
        body = f"""
        <section class="page-head">
          <div>
            <p class="eyebrow">全站记录</p>
            <h1>全站猜测记录</h1>
          </div>
          <div class="head-actions">
            <a class="button-link" href="/leaderboard">返回排行榜</a>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">
            <h2>{'所有猜测' if not selected_username else e(selected_username) + ' 的猜测'}</h2>
          </div>
          {bets_filter_form(usernames, selected_username)}
          {admin_bets_table(filtered_bets, snapshot['matches'])}
        </section>
        """
        self.send_html(layout("全站猜测记录", body, user, query))

    def render_poster(self, user, query):
        db = read_db()
        poster_users = sorted(
            username
            for username, item in db.get("users", {}).items()
            if not item.get("is_negative")
        )
        requested_username = first_query(query, "username").strip()
        selected_username = requested_username if requested_username in poster_users else user["username"]
        data = service.get_poster_data(selected_username)
        poster_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        options = []
        for username in poster_users:
            selected = " selected" if username == selected_username else ""
            options.append(f'<option value="{e(username)}"{selected}>{e(username)}</option>')

        body = f"""
        <section class="page-head">
          <div>
            <p class="eyebrow">我的报告</p>
            <h1>资产海报</h1>
          </div>
          <div class="head-actions">
            <button class="button-link" onclick="downloadPoster()" id="dl-btn">下载图片</button>
            <a class="button-link" href="/dashboard">返回总览</a>
          </div>
        </section>
        <section class="panel poster-tools">
          <form class="filter-form" method="get" action="/poster">
            <label>查看玩家
              <select name="username">
                {''.join(options)}
              </select>
            </label>
            <button type="submit">查看海报</button>
          </form>
          <div class="poster-bg-tools">
            <label>上传背景<input id="poster-bg-file" type="file" accept="image/*"></label>
            <label>横向裁切<input id="poster-bg-x" type="range" min="-100" max="100" value="0"></label>
            <label>纵向裁切<input id="poster-bg-y" type="range" min="-100" max="100" value="0"></label>
            <label>缩放<input id="poster-bg-zoom" type="range" min="100" max="220" value="100"></label>
            <label>透明度<input id="poster-bg-opacity" type="range" min="0" max="100" value="100"></label>
            <button class="secondary" id="poster-bg-reset" type="button">重置背景</button>
          </div>
        </section>
        <div class="poster-wrap">
          <div class="poster" id="poster-container">
            <canvas id="poster-canvas" width="1200" height="675"></canvas>
          </div>
        </div>
        <script id="poster-data" type="application/json">{poster_json}</script>
        <script src="/static/poster.js"></script>
        """
        self.send_html(layout("资产海报", body, user, query))

    def render_admin(self, user, query):
        snapshot = service.admin_snapshot()
        body = f"""
        <section class="page-head">
          <div>
            <p class="eyebrow">管理后台</p>
            <h1>账号审核与数据维护</h1>
          </div>
          <div class="head-actions">
            <a class="button-link" href="/admin/download-db">下载 db.sqlite</a>
            <form method="post" action="/admin/refresh">
              <button type="submit">立即刷新比赛</button>
            </form>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title"><h2>待审核账号</h2></div>
          {pending_table(snapshot['pending'])}
        </section>
        <section class="panel">
          <div class="panel-title"><h2>全部账号</h2></div>
          {users_table(snapshot['users'], user)}
        </section>
        <section class="panel">
          <div class="panel-title"><h2>自定义排行榜</h2></div>
          <form class="inline-form filter-form" method="post" action="/admin/leaderboards/create">
            <label>排行榜名称<input name="name" maxlength="32" required></label>
            <label>类型
              <select name="metric" required>
                <option value="balance">余额</option>
                <option value="net_asset">净资产</option>
              </select>
            </label>
            <button type="submit">创建排行榜</button>
          </form>
          {custom_leaderboards_admin(snapshot['custom_leaderboards'], snapshot['users'])}
        </section>
        <section class="two-col">
          <form class="panel form-card inline-form" method="post" action="/admin/balance">
            <h2>手动调整余额</h2>
            <label>账户
              <select name="username" required>
                {account_options(snapshot['users'])}
              </select>
            </label>
            <label>调整方式
              <select name="operation" required>
                <option value="set">设为</option>
                <option value="add">增加</option>
                <option value="subtract">扣减</option>
              </select>
            </label>
            <label>费马币<input name="amount" type="number" required></label>
            <label>备注<input name="note" maxlength="120" placeholder="可选"></label>
            <button type="submit">提交调整</button>
          </form>
          <div class="panel">
            <div class="panel-title"><h2>最近余额调整</h2></div>
            {balance_adjustments_table(snapshot['adjustments'])}
          </div>
        </section>
        
        <section class="two-col">
          <form class="panel form-card inline-form" method="post" action="/admin/add-match">
            <h2>手动添加比赛</h2>
            <div style="display: flex; gap: 8px;">
              <label style="flex: 1;">主队名称<input name="home_team" required></label>
              <label style="flex: 1;">客队名称<input name="away_team" required></label>
            </div>
            <label>开赛时间<input name="start_time" type="datetime-local" required></label>
            <div style="display: flex; gap: 8px;">
              <label style="flex: 1;">主胜赔率<input name="home_odds" type="number" step="0.01" min="1" required></label>
              <label style="flex: 1;">平局赔率<input name="draw_odds" type="number" step="0.01" min="1" required></label>
              <label style="flex: 1;">客胜赔率<input name="away_odds" type="number" step="0.01" min="1" required></label>
            </div>
            <button type="submit">添加比赛</button>
          </form>

          <form class="panel form-card inline-form" method="post" action="/admin/settle-match" onsubmit="return confirm('确定手动结算这场比赛吗？结算后所有开放的该场比赛猜测都将完成发放，操作不可逆！');">
            <h2>手动结算比赛</h2>
            <label style="flex: 2;">未结束比赛
              <select name="match_id" required>
                {match_options(snapshot['matches'])}
              </select>
            </label>
            <div style="display: flex; gap: 8px;">
              <label style="flex: 1;">主队得分<input name="home_score" type="number" min="0" required></label>
              <label style="flex: 1;">客队得分<input name="away_score" type="number" min="0" required></label>
            </div>
            <button type="submit">强制结算并派彩</button>
          </form>
        </section>

        <section class="panel">
          <div class="panel-title"><h2>未结束比赛管理</h2></div>
          {admin_matches_table(snapshot['matches'])}
        </section>

        <section class="panel">
          <div class="panel-title"><h2>贷款记录</h2></div>
          {loans_table(snapshot['loans'])}
        </section>
        <section class="panel">
          <div class="panel-title"><h2>猜测记录</h2></div>
          {admin_bets_table(snapshot['bets'], snapshot['matches'])}
        </section>
        """
        self.send_html(layout("管理后台", body, user, query))

    def current_user(self):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        morsel = cookie.get("session")
        if not morsel:
            return None
        username = verify_session(morsel.value)
        if not username:
            return None
        return service.get_user(username)

    def require_user(self, user):
        if not user:
            raise service.AppError("请先登录。")
        return user

    def require_admin(self, user):
        self.require_user(user)
        if user.get("role") != "admin":
            raise service.AppError("需要管理员权限。")
        return user

    def set_session(self, username):
        value = sign_session(username)
        self.extra_cookie = f"session={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS * 86400}"

    def clear_session(self):
        self.extra_cookie = "session=deleted; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"

    def redirect(self, path, message=None, error=None):
        params = {}
        if message:
            params["message"] = message
        if error:
            params["error"] = error
        target = add_query(path, params)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", target)
        cookie = getattr(self, "extra_cookie", None)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def read_form(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8")
        parsed = urllib.parse.parse_qs(raw)
        return {key: values[0] for key, values in parsed.items()}

    def send_html(self, html_text, status=HTTPStatus.OK):
        payload = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_static(self, path):
        rel = path.removeprefix("/static/").replace("/", os.sep)
        file_path = (STATIC_DIR / rel).resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = file_path.read_bytes()
        mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def download_db(self):
        content = export_sqlite_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/vnd.sqlite3")
        self.send_header("Content-Disposition", 'attachment; filename="db.sqlite"')
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def render_error(self, exc):
        body = f"""
        <section class="panel error-page">
          <h1>服务器错误</h1>
          <p>{e(str(exc))}</p>
          <a href="/">返回首页</a>
        </section>
        """
        self.send_html(layout("错误", body, self.current_user(), {}), HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def layout(title, body, user, query):
    message = first_query(query, "message")
    error = first_query(query, "error")
    api_status = api_status_badge()
    nav = ""
    if user:
        admin = '<a href="/admin">管理</a>' if user.get("role") == "admin" else ""
        nav = f"""
        <nav>
          <a href="/dashboard">总览</a>
          <a href="/matches">比赛</a>
          <a href="/loans">借贷</a>
          <a href="/leaderboard">富豪榜</a>
          <a href="/poster">海报</a>
          {admin}
          <form method="post" action="/logout"><button class="ghost" type="submit">退出</button></form>
        </nav>
        """
    flash = ""
    if message:
        flash = f'<div class="flash ok">{e(message)}</div>'
    if error:
        flash = f'<div class="flash bad">{e(error)}</div>'
    return f"""<!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{e(title)} - Fermat Coin</title>
      <link rel="icon" href="https://www.svgrepo.com/show/522513/coin.svg" type="image/svg+xml">
      <link rel="stylesheet" href="/static/styles.css">
    </head>
    <body>
      <div class="site-bg" aria-hidden="true"></div>
      <header class="topbar">
        <a class="brand" href="/">Fermat Coin</a>
        {nav}
      </header>
      <div class="api-status">{api_status}</div>
      <main>
        {flash}
        {body}
      </main>
      <button class="bg-toggle" type="button" data-bg-toggle aria-pressed="true">关闭背景</button>
      <script>
        (function () {{
          var key = "fermat-bg-visible";
          var button = document.querySelector("[data-bg-toggle]");
          function readVisible() {{
            try {{
              return localStorage.getItem(key) !== "off";
            }} catch (err) {{
              return true;
            }}
          }}
          function writeVisible(visible) {{
            try {{
              localStorage.setItem(key, visible ? "on" : "off");
            }} catch (err) {{}}
          }}
          function applyVisible(visible) {{
            document.documentElement.classList.toggle("bg-hidden", !visible);
            button.textContent = visible ? "关闭背景" : "开启背景";
            button.setAttribute("aria-pressed", visible ? "true" : "false");
          }}
          applyVisible(readVisible());
          button.addEventListener("click", function () {{
            var visible = document.documentElement.classList.contains("bg-hidden");
            writeVisible(visible);
            applyVisible(visible);
          }});
        }})();
        document.addEventListener("click", function (event) {{
          var maxButton = event.target.closest("[data-fill-max]");
          if (!maxButton) return;
          var field = maxButton.closest("label");
          var input = field ? field.querySelector("input[type='number']") : null;
          if (!input) return;
          input.value = maxButton.getAttribute("data-fill-max") || "0";
          input.focus();
        }});
      </script>
    </body>
    </html>"""


def api_status_badge():
    meta = read_db()["meta"]
    last = meta.get("last_match_update")
    last_text = format_time(last) if last else "尚未拉取"
    source = meta.get("match_source") or "未更新"
    return f"<span>上次 API 检查：{e(last_text)}</span><span>拉取状态：{e(source)}</span>"


def metric_card(label, value, sub):
    return f"""
    <div class="metric">
      <span>{e(label)}</span>
      <strong>{e(value)}</strong>
      <small>{e(sub)}</small>
    </div>
    """


def match_card(match, allow_bet, user_balance=0):
    odds = match.get("odds") or {}
    status = status_label(match.get("status"))
    score = ""
    if match.get("status") == "completed":
        score = f"<span class=\"score\">{match.get('home_score')} - {match.get('away_score')}</span>"
    bet_form = ""
    if allow_bet:
        bet_form = f"""
        <form class="bet-form" method="post" action="/bet">
          <input type="hidden" name="match_id" value="{e(match['id'])}">
          <div class="choice-row">
            {choice_radio('home', match['home_team'], odds.get('home'))}
            {choice_radio('draw', '平局', odds.get('draw'))}
            {choice_radio('away', match['away_team'], odds.get('away'))}
          </div>
          <label class="stake-input">费马币
            <span class="input-with-button">
              <input name="stake" type="number" min="1" max="{max(1, int(user_balance))}" required>
              <button type="button" data-fill-max="{max(0, int(user_balance))}">max</button>
            </span>
          </label>
          <button type="submit">猜测</button>
        </form>
        """
    return f"""
    <article class="match-card">
      <div class="match-main">
        <div>
          <span class="league">{e(match.get('league', '足球'))}</span>
          <h3>{e(match.get('home_team', ''))} <span>vs</span> {e(match.get('away_team', ''))}</h3>
          <p>{format_time(match.get('start_time'))} · {status} {score}</p>
        </div>
        <div class="odds-line">
          <span>主胜 {odds.get('home', '-')}</span>
          <span>平局 {odds.get('draw', '-')}</span>
          <span>客胜 {odds.get('away', '-')}</span>
        </div>
      </div>
      {bet_form}
    </article>
    """


def choice_radio(value, label, odds):
    return f"""
    <label class="choice">
      <input type="radio" name="choice" value="{value}" required>
      <span>{e(label)}</span>
      <strong>{odds}</strong>
    </label>
    """


def bets_table(bets, matches, allow_cancel=False, show_time=False):
    if not bets:
        return empty_state("暂无记录")
    rows = []
    for bet in bets:
        match = matches.get(bet["match_id"], {})
        cells = []
        if show_time:
            cells.append(f"<td>{format_time(bet.get('created_at'))}</td>")
        cells.extend(
            [
                f"<td>{e(match.get('home_team', '?'))} vs {e(match.get('away_team', '?'))}</td>",
                f"<td>{service.CHOICE_LABELS.get(bet['choice'], bet['choice'])}</td>",
                f"<td>{money(bet['stake'])}</td>",
                f"<td>{bet['odds']}</td>",
                f"<td>{bet_status(bet)}</td>",
            ]
        )
        if allow_cancel:
            cells.append(f"<td>{cancel_bet_form(bet, match)}</td>")
        rows.append(
            f"""
            <tr>
              {''.join(cells)}
            </tr>
            """
        )
    headers = []
    if show_time:
        headers.append("<th>时间</th>")
    headers.extend(["<th>比赛</th>", "<th>选择</th>", "<th>费马币</th>", "<th>赔率</th>", "<th>状态</th>"])
    if allow_cancel:
        headers.append("<th>操作</th>")
    return f"""
    <div class="table-wrap"><table>
      <thead><tr>{''.join(headers)}</tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def cancel_bet_form(bet, match):
    if bet.get("status") != "open" or bet.get("mirrored_from"):
        return '<span class="muted">-</span>'
    start_time = match.get("start_time")
    if not start_time or match.get("status") != "upcoming" or parse_iso(start_time) <= utc_now():
        return '<span class="muted">-</span>'
    return f"""
    <form method="post" action="/bet/cancel" onsubmit="return confirm('确定撤回这条猜测？');">
      <input type="hidden" name="bet_id" value="{e(bet['id'])}">
      <button class="danger" type="submit">撤回</button>
    </form>
    """


def bets_filter_form(usernames, selected_username):
    options = ['<option value="">全部用户</option>']
    for username in usernames:
        selected = " selected" if username == selected_username else ""
        options.append(f'<option value="{e(username)}"{selected}>{e(username)}</option>')
    reset_link = '<a class="button-link secondary" href="/all-bets">重置</a>' if selected_username else ""
    return f"""
    <form class="filter-form" method="get" action="/all-bets">
      <label>按用户筛选
        <select name="username">
          {''.join(options)}
        </select>
      </label>
      <button type="submit">筛选</button>
      {reset_link}
    </form>
    """


def admin_bets_table(bets, matches):
    if not bets:
        return empty_state("暂无猜测记录")
    rows = []
    for bet in bets:
        match = matches.get(bet["match_id"], {})
        rows.append(
            f"""
            <tr>
              <td>{format_time(bet.get('created_at'))}</td>
              <td>{e(bet.get('username', ''))}</td>
              <td>{'反向' if bet.get('mirrored_from') else '主账户'}</td>
              <td>{e(match.get('home_team', '?'))} vs {e(match.get('away_team', '?'))}</td>
              <td>{service.CHOICE_LABELS.get(bet.get('choice'), bet.get('choice'))}</td>
              <td>{money(bet.get('stake', 0))}</td>
              <td>{bet.get('odds')}</td>
              <td>{bet_status(bet)}</td>
              <td>{e(bet.get('mirrored_from') or '-')}</td>
            </tr>
            """
        )
    return f"""
    <div class="table-wrap"><table>
      <thead><tr><th>时间</th><th>账户</th><th>类型</th><th>比赛</th><th>选择</th><th>费马币</th><th>赔率</th><th>状态</th><th>关联</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def standings_table(users):
    rows = []
    for idx, user in enumerate(users, 1):
        rows.append(
            f"""
            <tr>
              <td>{idx}</td>
              <td>{e(user['username'])}</td>
              <td>{money(user['balance'])}</td>
              <td>{'反向' if user.get('is_negative') else user.get('role', 'user')}</td>
            </tr>
            """
        )
    return f"""
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>账户</th><th>余额</th><th>类型</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def net_asset_standings_table(users):
    rows = []
    for idx, user in enumerate(users, 1):
        rows.append(
            f"""
            <tr>
              <td>{idx}</td>
              <td>{e(user['username'])}</td>
              <td>{money(user['balance'])}</td>
              <td>{money(-user.get('loan_due', 0))}</td>
              <td>+{money(user.get('open_stakes', 0))}</td>
              <td><strong>{money(user['net_asset'])}</strong></td>
              <td>{'反向' if user.get('is_negative') else user.get('role', 'user')}</td>
            </tr>
            """
        )
    return f"""
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>账户</th><th>余额</th><th>贷款</th><th>未结算下注</th><th>净资产</th><th>类型</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def loan_summary(loans):
    if not loans:
        return '<p class="muted">当前没有未结清贷款。</p>'
    return loans_table(loans)


def loans_table(loans):
    if not loans:
        return empty_state("暂无贷款记录")
    rows = []
    for loan in loans:
        rows.append(
            f"""
            <tr>
              <td>{e(loan['username'])}</td>
              <td>{money(loan['principal'])}</td>
              <td>{money(loan.get('current_due', 0))}</td>
              <td>{format_time(loan['due_at'])}</td>
              <td>{loan_status(loan['status'])}</td>
            </tr>
            """
        )
    return f"""
    <div class="table-wrap"><table>
      <thead><tr><th>账户</th><th>本金</th><th>当前应还</th><th>到期</th><th>状态</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def pending_table(users):
    if not users:
        return empty_state("暂无待审核账号")
    rows = []
    for user in users:
        rows.append(
            f"""
            <tr>
              <td>{e(user['username'])}</td>
              <td>{format_time(user['created_at'])}</td>
              <td>
                <form method="post" action="/admin/approve">
                  <input type="hidden" name="username" value="{e(user['username'])}">
                  <button type="submit">通过</button>
                </form>
              </td>
            </tr>
            """
        )
    return f"""
    <div class="table-wrap"><table>
      <thead><tr><th>用户名</th><th>注册时间</th><th>操作</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def account_options(users):
    options = []
    for user in users:
        label = f"{user['username']} · {money(user.get('balance', 0))}"
        options.append(f'<option value="{e(user["username"])}">{e(label)}</option>')
    return "".join(options)


def real_account_options(users):
    options = []
    for user in users:
        if user.get("is_negative"):
            continue
        label = f"{user['username']} · {money(user.get('balance', 0))}"
        options.append(f'<option value="{e(user["username"])}">{e(label)}</option>')
    if not options:
        options.append('<option value="" disabled selected>暂无真实账户</option>')
    return "".join(options)


def custom_leaderboards_admin(leaderboards, users):
    if not leaderboards:
        return empty_state("暂无自定义排行榜")
    account_select_options = real_account_options(users)
    rows = []
    for leaderboard in leaderboards:
        member_forms = []
        for member in leaderboard.get("users", []):
            member_forms.append(f"""
              <form method="post" action="/admin/leaderboards/remove-user" class="chip-form">
                <input type="hidden" name="leaderboard_id" value="{e(leaderboard['id'])}">
                <input type="hidden" name="username" value="{e(member['username'])}">
                <button type="submit" class="ghost" title="移出排行榜">{e(member['username'])} ×</button>
              </form>
            """)
        members = "".join(member_forms) or '<span class="muted">暂无参与用户</span>'
        rows.append(f"""
        <tr>
          <td>
            <strong>{e(leaderboard['name'])}</strong>
            <div class="muted">{e(leaderboard['id'])}</div>
          </td>
          <td>{e(leaderboard['metric_label'])}</td>
          <td><div class="chip-list">{members}</div></td>
          <td>
            <form method="post" action="/admin/leaderboards/add-user" class="compact-form">
              <input type="hidden" name="leaderboard_id" value="{e(leaderboard['id'])}">
              <select name="username" required>
                {account_select_options}
              </select>
              <button type="submit">添加</button>
            </form>
          </td>
          <td>
            <form method="post" action="/admin/leaderboards/delete" onsubmit="return confirm('确定删除这个排行榜？');">
              <input type="hidden" name="leaderboard_id" value="{e(leaderboard['id'])}">
              <button class="danger" type="submit">删除</button>
            </form>
          </td>
        </tr>
        """)
    return f"""
    <div class="table-wrap"><table>
      <thead><tr><th>排行榜</th><th>类型</th><th>参与用户</th><th>添加用户</th><th>操作</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def match_options(matches_dict):
    options = []
    # only list non-completed or maybe we want to allow re-settling? Usually just non-completed.
    active_matches = [m for m in matches_dict.values() if m.get("status") != "completed"]
    sorted_matches = sorted(active_matches, key=lambda m: m.get("start_time") or "")
    for m in sorted_matches:
        time_str = format_time(m.get("start_time"))
        label = f"{m.get('home_team')} vs {m.get('away_team')} ({time_str})"
        options.append(f'<option value="{e(m["id"])}">{e(label)}</option>')
    
    if not options:
        options.append(f'<option value="" disabled selected>暂无可结算比赛</option>')
    return "".join(options)


def user_actions(user, current_user=None):
    actions = []
    is_super_admin = (
        current_user
        and current_user.get("username") == ADMIN_USERNAME
        and current_user.get("role") == "admin"
    )
    if user.get("role") == "admin":
        if is_super_admin and user.get("username") != ADMIN_USERNAME:
            actions.append(f"""
            <form method="post" action="/admin/demote-admin" onsubmit="return confirm('确定将这个管理员降为普通用户？');" style="display:inline-block;">
              <input type="hidden" name="username" value="{e(user['username'])}">
              <button class="danger" type="submit">降为普通用户</button>
            </form>
            """)
        else:
            actions.append('<span class="muted">保留</span>')
    else:
        if is_super_admin:
            confirm = "确定删除这个反向账号及相关猜测记录？" if user.get("is_negative") else "确定删除这个账号、关联反向账号及相关猜测和借贷记录？"
            actions.append(f"""
            <form method="post" action="/admin/delete-user" onsubmit="return confirm('{e(confirm)}');" style="display:inline-block; margin-right:4px;">
              <input type="hidden" name="username" value="{e(user['username'])}">
              <button class="danger" type="submit">删除</button>
            </form>
            """)
        if not user.get("is_negative"):
            actions.append(f"""
            <form method="post" action="/admin/set-admin" onsubmit="return confirm('确定将这个账号设置为管理员？');" style="display:inline-block;">
              <input type="hidden" name="username" value="{e(user['username'])}">
              <button type="submit">设为管理</button>
            </form>
            """)
    return "".join(actions)


def admin_matches_table(matches_dict):
    active = [m for m in matches_dict.values() if m.get("status") != "completed"]
    active.sort(key=lambda m: m.get("start_time") or "")
    if not active:
        return empty_state("暂无未结束的比赛")
    rows = []
    for m in active:
        rows.append(f"""
        <tr>
          <td>{format_time(m.get('start_time'))}</td>
          <td>{e(m.get('home_team'))}</td>
          <td>{e(m.get('away_team'))}</td>
          <td>{e(m.get('odds', {}).get('home', '-'))} / {e(m.get('odds', {}).get('draw', '-'))} / {e(m.get('odds', {}).get('away', '-'))}</td>
          <td>{status_label(m.get('status'))}</td>
          <td>
            <form method="post" action="/admin/delete-match" onsubmit="return confirm('确定删除这场比赛吗？会作废相关猜测并退款。');">
              <input type="hidden" name="match_id" value="{e(m['id'])}">
              <button class="danger" type="submit">删除</button>
            </form>
          </td>
        </tr>
        """)
    return f"""
    <div class="table-wrap"><table>
      <thead><tr><th>时间</th><th>主队</th><th>客队</th><th>赔率(主/平/客)</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def users_table(users, current_user=None):
    rows = []
    for user in users:
        action = user_actions(user, current_user)
        rows.append(
            f"""
            <tr>
              <td>{e(user['username'])}</td>
              <td>{'反向账户' if user.get('is_negative') else user.get('role', 'user')}</td>
              <td>{money(user.get('balance', 0))}</td>
              <td>{user.get('credit', 0)}</td>
              <td>{'已通过' if user.get('approved') else '待审核'}</td>
              <td>{'Game Over' if user.get('game_over') else '正常'}</td>
              <td>{action}</td>
            </tr>
            """
        )
    return f"""
    <div class="table-wrap"><table>
      <thead><tr><th>账户</th><th>类型</th><th>余额</th><th>信用</th><th>审核</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def balance_adjustments_table(adjustments):
    if not adjustments:
        return empty_state("暂无余额调整记录")
    rows = []
    for item in adjustments:
        rows.append(
            f"""
            <tr>
              <td>{format_time(item['created_at'])}</td>
              <td>{e(item['target_username'])}</td>
              <td>{service.BALANCE_OPERATIONS.get(item['operation'], item['operation'])}</td>
              <td>{money(item['amount'])}</td>
              <td>{money(item['old_balance'])} → {money(item['new_balance'])}</td>
              <td>{e(item.get('note', ''))}</td>
            </tr>
            """
        )
    return f"""
    <div class="table-wrap"><table>
      <thead><tr><th>时间</th><th>账户</th><th>方式</th><th>费马币</th><th>变化</th><th>备注</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    """


def empty_state(text):
    return f'<div class="empty">{e(text)}</div>'


def bet_status(bet):
    if bet["status"] == "won":
        return f"赢，派彩 {money(bet.get('payout', 0))}"
    labels = {"open": "待结算", "lost": "输", "void": "作废", "canceled": "已撤回"}
    return labels.get(bet["status"], bet["status"])


def loan_status(status):
    return {"active": "未结清", "paid": "已还清", "defaulted": "逾期出局"}.get(status, status)


def status_label(status):
    return {"upcoming": "未开赛", "in_progress": "进行中", "completed": "已结束"}.get(status, status)


def format_time(value):
    if not value:
        return "-"
    dt = parse_iso(value).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


def money(value):
    return f"{int(value):,}"


def e(value):
    return html.escape(str(value), quote=True)


def split_url(path):
    parsed = urllib.parse.urlparse(path)
    return parsed.path, urllib.parse.parse_qs(parsed.query)


def first_query(query, key):
    values = query.get(key)
    return values[0] if values else ""


def add_query(path, params):
    if not params:
        return path
    parsed = urllib.parse.urlparse(path)
    current = urllib.parse.parse_qs(parsed.query)
    for key, value in params.items():
        current[key] = [value]
    query = urllib.parse.urlencode(current, doseq=True)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def sign_session(username):
    exp = int((utc_now() + timedelta(days=SESSION_DAYS)).timestamp())
    payload = f"{username}|{exp}"
    secret = read_db()["meta"]["session_secret"].encode("utf-8")
    sig = hmac.new(secret, payload.encode("utf-8"), "sha256").hexdigest()
    return urllib.parse.quote(f"{payload}|{sig}")


def verify_session(value):
    try:
        raw = urllib.parse.unquote(value)
        username, exp, sig = raw.rsplit("|", 2)
        if int(exp) < int(utc_now().timestamp()):
            return None
        payload = f"{username}|{exp}"
        secret = read_db()["meta"]["session_secret"].encode("utf-8")
        expected = hmac.new(secret, payload.encode("utf-8"), "sha256").hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return username
    except Exception:
        return None
