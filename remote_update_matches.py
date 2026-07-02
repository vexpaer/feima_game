import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from fermat_app.sources import MatchSource


DEFAULT_PORT = 3008
TIMEOUT_SECONDS = 90


def normalize_server(value):
    server = str(value or "").strip().rstrip("/")
    if not server:
        raise SystemExit("请输入服务器 IP 或域名。")
    if not server.startswith(("http://", "https://")):
        server = "http://" + server
    parsed = urllib.parse.urlparse(server)
    if not parsed.netloc:
        raise SystemExit("服务器地址格式不正确。")
    netloc = parsed.netloc
    if ":" not in netloc:
        netloc = f"{netloc}:{DEFAULT_PORT}"
    return urllib.parse.urlunparse((parsed.scheme, netloc, "", "", "", ""))


def update_key():
    for name in ("FERMAT_UPDATE_KEY", "ODDS_API_IO_KEY", "THE_ODDS_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value
    raise SystemExit("缺少更新密钥：请在 bat 开头设置 FERMAT_UPDATE_KEY 或 API key。")


def request_json(method, url, key, payload=None):
    body = None
    headers = {"X-Fermat-Update-Key": key}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{url} 返回 HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 {url}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{url} 返回的不是 JSON: {raw[:200]}") from exc


def main():
    server = normalize_server(sys.argv[1] if len(sys.argv) > 1 else input("服务器 IP 或域名："))
    key = update_key()

    state_url = server + "/api/matches/update-state"
    import_url = server + "/api/matches/import"
    print(f"连接服务器：{server}")

    state = request_json("GET", state_url, key)
    if not state.get("ok"):
        raise RuntimeError(state.get("error") or "服务器拒绝读取更新状态。")
    existing_matches = state.get("matches") or {}
    score_sports = state.get("score_sports") or []
    print(f"服务器现有比赛：{len(existing_matches)} 场")

    fetched, source_label = MatchSource().fetch(existing_matches, score_sports)
    print(f"本机 API 拉取完成：{len(fetched)} 场")
    print(source_label)

    result = request_json(
        "POST",
        import_url,
        key,
        {
            "matches": fetched,
            "source_label": "远程客户端：" + source_label,
        },
    )
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "服务器导入失败。")
    print(result.get("message") or f"已导入 {result.get('count', 0)} 场比赛。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"更新失败：{exc}")
        raise SystemExit(1)
