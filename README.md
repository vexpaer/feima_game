# Fermat Coin 足球模拟投注平台

运行：

```powershell
python run.py
```

访问：

```text
http://127.0.0.1:0308/
```

初始管理员：

```text
用户名：vexpaer
密码：1qaz2wsX
```

数据保存在 `data/db.json`。首次启动会自动创建管理员和 `negative-vexpaer` 反向账户。

## 比赛数据源

默认使用内置演示源，保证没有 API key 时也能体验注册、审核、下注、反向账户、结算和借贷。

当前已在 `data/config.json` 接入 The Odds API，本地配置不会被 `.gitignore` 纳入版本管理。默认只请求一个足球 sport key：

```json
{
  "region": "eu",
  "sports": ["soccer_epl"],
  "update_minutes": 60
}
```

也可以用环境变量覆盖配置：

```powershell
$env:THE_ODDS_API_KEY="你的 key"
python run.py
```

可选环境变量：

```text
THE_ODDS_API_REGION=eu
THE_ODDS_API_SPORTS=soccer_epl
THE_ODDS_API_UPDATE_MINUTES=60
HOST=0.0.0.0
PORT=0308
```

The Odds API 的 `/odds` 接口用于未开赛赔率。为节省额度，只有存在已开赛的未结算注单时才请求 `/scores` 获取赛果。系统不做后台空跑；有人访问页面时才检查是否需要自动更新，默认每 60 分钟最多触发一次 API 请求轮次。管理员后台的“立即刷新比赛”会手动强制拉取一次 API。所有页面顶部都会显示上次 API 拉取时间和数据源。

## 规则

- 每个普通账户初始 1,000,000 fermat coin。
- 注册后生成 `negative-用户名`，不能登录，只随主账户下注自动反向下注。
- 主胜和客胜下注会在反向账户押相反一方；平局下注会在反向账户拆成主胜和客胜两笔。
- 比赛开始后停止下注，比赛完成后自动按赔率结算。
- 登录后可在“富豪榜”查看所有账户的 fermat coin 余额排行。
- 管理员后台可以手动将任意账户余额设为指定值、增加余额或扣减余额，并保留最近调整记录。
- 银行借贷额度为 `max(20,000, 当前余额 x 10) x 信用/100`。
- 只能有一笔未结清贷款；每周 10% 利息，两周未还清则信用清零并 game over。
