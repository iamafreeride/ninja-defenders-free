# ninja-defenders-free

<p align="center">
  <img src="assets/icon.webp" alt="Ninja Defenders icon" width="128" height="128">
</p>

[English](README_EN.md) | **繁體中文**

自動領取《Ninja Defenders : Cat Shinobi》網頁商店（Unity Web Shop）每天一次的免費 **1 Daily Free Ruby Cat Stone**（畫面顯示「每天免費紅貓石1個」）。全自動、無人值守，跑完就結束。

登入只需要 **26 碼遊戲內帳號 ID**。結構與容器化方式參考 [simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer)（MIT）。

```bash
docker run --rm --shm-size=1g -e NINJA_USER_ID=<你的26碼ID> ninja-defenders-free
```

## 運作方式

1. 啟動無頭瀏覽器（映像內建 Firefox；Windows 本機預設 Edge），開啟 <https://shop.unity.com/crescento/game/webshop-cc08e9e8>。
2. 關掉 cookie 同意列，用 ID（`input[name="playerId"]`）登入。送出策略依序嘗試：按鈕文字 → `type=submit` → Enter，最多 3 輪。已有登入狀態則跳過。
3. 用語言無關的 selector 找免費卡片按鈕（`a[data-slot="product-card"][href*="unity_web_free"] button[data-slot="buy-cta"]`，舊版 `data-testid="free-button"` 等作為備援），所以商店顯示任何語言都不影響。
4. 按鈕 `disabled` 或顯示「已擁有」代表今天已領，直接 exit 0；否則點擊、處理確認彈窗，並等待變成已擁有或出現成功提示。

## 快速開始

### Docker（任何有 Docker 的機器，含 NAS）

```bash
git clone https://github.com/iamafreeride/ninja-defenders-free.git
cd ninja-defenders-free
docker build -t ninja-defenders-free .
docker run --rm --shm-size=1g -e NINJA_USER_ID=<你的26碼ID> ninja-defenders-free
```

或用 compose：

```bash
cp .env.example .env      # 填入 NINJA_USER_ID
docker compose up --build
```

### Windows 本機（不用裝 Docker）

1. 安裝 Python 3.9+（勾選 **Add python.exe to PATH**）。
2. 雙擊 **`run.bat`**。第一次會建立 `.venv` 並安裝 selenium（約 30 秒），沒設定 ID 時會詢問；把 ID 寫進 `.env` 的 `NINJA_USER_ID=` 就不必每次輸入。
3. 預設使用 Edge（Windows 10/11 內建），不需另外裝驅動。

命令列等價作法：

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python claim.py <26碼ID>
```

### 你的 26 碼 ID 在哪

遊戲內 → 左上角頭像 → 個人檔案頁面**最下方**的 26 碼英數（旁邊有 `Copy`）。

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `NINJA_USER_ID` | 必填 | 26 碼帳號 ID；也可用第一個命令列參數 |
| `BROWSER` | `firefox` | `firefox` / `edge` / `chrome`（`run.bat` 設為 `edge`） |
| `HEADLESS` | `true` | `false` 會開可見瀏覽器 |
| `DEBUG` | `false` | 失敗時保存截圖與 DOM 到 `artifacts/` |
| `SITE_URL` | `https://shop.unity.com/crescento/game/webshop-cc08e9e8` | 商店網址 |
| `LOGIN_TIMEOUT` | `60` | 等登入完成的秒數 |
| `CLAIM_TIMEOUT` | `90` | 等免費按鈕出現的秒數 |
| `RESULT_TIMEOUT` | `60` | 等「已擁有」或成功提示的秒數 |
| `USER_ID_SELECTOR` | `#user-id-input, input[name='playerId']` | 帳號輸入框 selector |
| `WEBDRIVER_PATH` | 自動 | 自動下載驅動失敗時，指定 geckodriver / msedgedriver 路徑 |
| `BROWSER_PROFILE_DIR` | 無 | 瀏覽器 profile 目錄，可保留登入狀態 |
| `ARTIFACTS_DIR` | `/app/artifacts` | 除錯產物目錄 |

## 退出碼

| 代碼 | 意義 |
|---|---|
| `0` | 已領取，或今天已領過（可安全重跑） |
| `1` | 自動化失敗：找不到元素、逾時、登入被拒 |
| `2` | 設定錯誤：ID 缺少或不是 26 碼英數 |

## 排程（每天一次）

Linux / NAS：

```cron
5 9 * * * cd /opt/ninja-defenders-free && /usr/bin/docker compose run --rm claim >> claim.log 2>&1
```

Windows 工作排程器：執行 `C:\path\to\run.bat`（不要勾「只在使用者登入時執行」，並移除 `run.bat` 最後的 `pause`），或直接呼叫上面的 Docker 指令。

## 疑難排解

- **顯示「Already claimed today」**：這個帳號今天已領過（可能是手動領的），程式 exit 0，隔天再跑就會領。頁面的「開放購買時間還剩下…」是活動倒數，不是冷卻時間。
- **卡在「Opening login dialog」**：先用 `DEBUG=true` 跑一次，查看 `artifacts/`。
  - 登入鈕文字不同 → 設定 `LOGIN_SUBMIT_WORDS="log in,login,登入,..."`。
  - 出現 captcha → 無頭模式過不了，改用 `HEADLESS=false` 在有螢幕的機器執行。
  - Windows 上 Firefox 報 `Unable to write to temporary directory` → 把 `TEMP`/`TMP` 指到可寫目錄，或改用 `BROWSER=edge`。
- **找不到免費按鈕**：商店改版了。查看 `artifacts/*.html` 中 `data-slot="buy-cta"` 或 `data-testid="free-button"` 是否還在，必要時以 `FREE_BUTTON_SELECTOR` 覆蓋（見 `claim.py` 的 `find_free_button`）。
- **Firefox 隨機崩潰（Docker）**：`/dev/shm` 太小，加 `--shm-size=1g`（compose 已設定）。

## 專案結構

```
claim.py            登入 → 找免費按鈕 → 領取 → 判定結果
run.bat             Windows 一鍵執行
Dockerfile          Debian slim + Firefox ESR + geckodriver
docker-compose.yml
requirements.txt    selenium
.env.example
.github/workflows/docker.yml   建置並推送 GHCR（amd64 + arm64）
```

## 免責聲明

- 僅供**你自己的帳號**每天一次使用，請勿代領他人帳號或大量註冊。
- 這是瀏覽器自動化，不是官方 API。商店隨時可能改版、加上驗證或限制，也可能與其服務條款相牴觸，風險自負。
- 本專案與 CookApps、Unity 均無任何關係。

## 授權

MIT，見 [LICENSE](LICENSE)。靈感來自 [simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer)。
