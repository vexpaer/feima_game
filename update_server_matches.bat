@echo off
chcp 65001 >nul
setlocal

rem API keys used by this one-shot remote updater.
set "ODDS_API_IO_KEY=5def36f911f728971ea26b9a3d581352566f8e555ce5fab1b68e5b607c480bd1"
set "THE_ODDS_API_KEY=f56e40433a77881bd1d9337617fce05b"
set "FERMAT_UPDATE_KEY=%ODDS_API_IO_KEY%"

set "THE_ODDS_API_REGION=eu"
set "THE_ODDS_API_SPORTS=soccer_epl,soccer_fifa_world_cup"
set "ODDS_API_IO_BOOKMAKERS=Bet365"
set "ODDS_API_IO_PAST_DAYS=7"
set "ODDS_API_IO_FUTURE_DAYS=30"
set "ODDS_API_IO_PAGE_LIMIT=100"

set /p "SERVER_IP=服务器 IP/域名（可带端口，默认 3008）："
if "%SERVER_IP%"=="" (
  echo 未输入服务器地址。
  pause
  exit /b 1
)

set "PYTHON=python"
python --version >nul 2>nul
if errorlevel 1 (
  py -3 --version >nul 2>nul
  if errorlevel 1 (
    echo 未找到可用的 Python，请先安装 Python 3。
    pause
    exit /b 1
  )
  set "PYTHON=py -3"
)

%PYTHON% "%~dp0remote_update_matches.py" "%SERVER_IP%"
set "EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %EXIT_CODE%
