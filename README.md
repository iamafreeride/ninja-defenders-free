# ninja-defenders-free

<p align="center">
  <img src="assets/icon.webp" alt="Ninja Defenders icon" width="128" height="128">
</p>

領取《Ninja Defenders : Cat Shinobi》網頁商店（Unity Web Shop）每天一次的免費
**1 Daily Free Ruby Cat Stone**（畫面顯示「每天免費紅貓石1個」），全自動、無人值守、跑完就結束。

結構與容器化方式參考 [simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer)（MIT）：
同樣是「用無頭瀏覽器做一件每天要做一次的小事，做完就讓程式／容器結束」。

| | noip-renewer | 本專案 |
|---|---|---|
| 目標 | No-IP 免費網域續期 | Ninja Defenders 每日免費紅貓石 |
| 登入方式 | 帳號 + 密碼（+ TOTP） | **只有 26 碼遊戲內帳號 ID** |
| 登入欄位 | `#username` / `#password` | `input[name="playerId"]` |
| 動作 | 逐一點 `Confirm` | 點免費卡片的領取鈕 |
| 結束 | 登出後結束 | 領取成功／今日已領後結束 |

```
docker run --rm --shm-size=1g -e NINJA_USER_ID=<你的26碼ID> ninja-defenders-free
```

---

## 它是怎麼運作的

1. 啟動無頭瀏覽器（映像內建 Firefox；Windows 本機預設 Edge），開啟 <https://shop.unity.com/crescento/game/webshop-cc08e9e8>。
2. 關掉 cookie 同意列。
3. 點右上角 **Log in / 登入**，在 `input[name="playerId"]` 填入 26 碼帳號 ID，按下方登入鈕。
   - 送出策略會依序嘗試：**按鈕文字比對 → `type=submit` → 在輸入框按 Enter**（最多 3 輪）。
   - 若已有登入狀態（例如使用固定 profile），會自動跳過登入。
4. 找到免費卡片上的按鈕：
   - `a[data-slot="product-card"][href*="unity_web_free"] button[data-slot="buy-cta"]`
   - 舊版 `button[data-testid="free-button"]` / `button[data-button-type="free"]` 仍保留為備援。
   - 這是**語言無關**的定位方式，所以商店顯示中文、英文、日文、韓文都不影響。
5. 判斷狀態：
   - 按鈕 `disabled`、文字含「已擁有／已領取」，或含 `[data-testid="owned"]` → 今天已領，直接 exit 0。
   - 否則點下去，處理可能出現的確認彈窗，然後等按鈕變成 owned／出現成功提示。
6. 印出結果並結束行程；用 `docker run --rm` 時容器也一併消失。

---

## 快速開始

### A. Docker（任何有 Docker 的機器，含 NAS）

```bash
git clone https://github.com/iamafreeride/ninja-defenders-free.git
cd ninja-defenders-free
docker build -t ninja-defenders-free .

docker run --rm --shm-size=1g \
  -e NINJA_USER_ID=<你的26碼ID> \
  ninja-defenders-free
```

或用 compose（設定寫在 `.env`）：

```bash
cp .env.example .env      # 填入 NINJA_USER_ID
docker compose up --build
```

### B. Windows 本機（不用裝 Docker）

1. 安裝 Python 3.9+（安裝時勾 **Add python.exe to PATH**）。
2. **雙擊 `run.bat`**。
   - 第一次會自動建立 `.venv` 並安裝 selenium（約 30 秒）。
   - 沒有設定 ID 時會問你：`Account ID (26 letters/digits):`，貼上後按 Enter。
   - 之後把 ID 寫進 `.env` 的 `NINJA_USER_ID=`，就不必每次輸入。
3. 預設用 **Edge**（Windows 10/11 內建），不需要另外裝驅動。

命令列等價作法：

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python claim.py <26碼ID>
```

> 也可以不改 `.env`，直接把 ID 當第一個參數：`python claim.py 01JB2XX...`

### 你的 26 碼 ID 在哪

遊戲內 → 左上角頭像 → 個人檔案頁面**最下方**的 26 碼英數（旁邊有 `Copy`）。
商店 FAQ 也這樣寫：*"The 26-character account ID ... is located at the bottom of the profile page."*

成功時的輸出長這樣（實際測試）：

```
[21:43:30] Ninja Defenders daily reward -- target https://shop.unity.com/crescento/game/webshop-cc08e9e8
[21:43:30] Starting Edge (headless)
[21:43:44] Page loaded
[21:43:53] Opening login dialog
[21:43:59] Login button not found, trying the input directly
[21:44:10] No login form, but the store is loaded -- reusing the existing session
[21:44:10] Logged in
[21:44:10] Free item already shows as owned
[21:44:10] Already claimed today (40s), nothing to do
```

---

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `NINJA_USER_ID` | （必填） | 26 碼遊戲帳號 ID；也可用第一個命令列參數 |
| `BROWSER` | `firefox` | `firefox` / `edge` / `chrome`（`run.bat` 會自動設成 `edge`） |
| `HEADLESS` | `true` | `false` 會開可見的瀏覽器，方便看它到底在點什麼 |
| `DEBUG` | `false` | 失敗時保存截圖 + DOM 到 `artifacts/` |
| `SITE_URL` | `https://shop.unity.com/crescento/game/webshop-cc08e9e8` | 商店網址 |
| `LOGIN_TIMEOUT` | `60` | 等登入完成的秒數 |
| `CLAIM_TIMEOUT` | `90` | 等免費按鈕出現的秒數 |
| `RESULT_TIMEOUT` | `60` | 等「已擁有」或成功提示的秒數 |
| `USER_ID_SELECTOR` | `#user-id-input, input[name='playerId']` | 帳號輸入框 selector（新舊商店皆可） |
| `WEBDRIVER_PATH` | 自動 | 指定 geckodriver / msedgedriver 路徑（自動下載失敗時用） |
| `BROWSER_PROFILE_DIR` | 無 | 指定瀏覽器 profile 目錄，可保留登入狀態 |
| `ARTIFACTS_DIR` | `/app/artifacts` | 除錯產物目錄 |

---

## 退出碼

| 代碼 | 意義 |
|---|---|
| `0` | 已領取，或今天已經領過（可安全重跑） |
| `1` | 自動化失敗：找不到元素、逾時、登入被拒 |
| `2` | 設定錯誤：ID 缺少或格式不符（非 26 碼英數） |

---

## 排程（每天一次）

Linux / NAS：

```cron
5 9 * * * cd /opt/ninja-defenders-free && /usr/bin/docker compose run --rm claim >> claim.log 2>&1
```

Windows 工作排程器：動作設成「啟動程式」，程式填 `C:\path\to\run.bat`，不要勾「只在使用者登入時執行」，
並把 `run.bat` 最後的 `pause` 拿掉（或改用 `pythonw`）。最簡單是直接呼叫：

```powershell
docker run --rm --shm-size=1g -e NINJA_USER_ID=<ID> ninja-defenders-free
```

> 每日獎勵一天只能領一次，重跑是安全的：會回報 `Already claimed today` 並 exit 0。

---

## 疑難排解

**按鈕顯示「已擁有」**
代表**這個帳號今天已經領過了**（可能你手動領過）。程式會印 `Already claimed today` 並 exit 0，
隔天再跑就會真的領。畫面下方的「開放購買時間還剩下 …」是活動剩餘時間，不是冷卻時間。

**卡在「Opening login dialog」／登入沒完成**
先用 `DEBUG=true` 跑一次，看 `artifacts/` 裡的截圖。常見原因：

- 登入鈕文字不同 → 覆蓋 `LOGIN_SUBMIT_WORDS="log in,login,登入,..."`
- 出現 captcha → 無頭瀏覽器過不了，改用 `HEADLESS=false` 在有螢幕的機器跑
- Firefox 在 Windows 上報 `Unable to write to temporary directory` → 把 `TEMP`/`TMP` 指到可寫目錄，或改用 `BROWSER=edge`

**找不到免費按鈕**
商店改版了。看 `artifacts/*.html`，找免費卡片上的 `data-slot="buy-cta"` 或舊版
`data-testid="free-button"` 是否還在；若改成別的屬性，覆蓋 `FREE_BUTTON_SELECTOR`
（見 `claim.py` 的 `find_free_button`）。

**Firefox 隨機崩潰（Docker）**
`/dev/shm` 太小，加 `--shm-size=1g`（compose 檔已設定）。

---

## 專案結構

```
.
├── claim.py                 # 登入 → 找免費按鈕 → 領取 → 判定結果
├── run.bat                  # Windows 一鍵執行（自動建 venv、問 ID、pause）
├── Dockerfile               # Debian slim + Firefox ESR + geckodriver
├── docker-compose.yml
├── requirements.txt         # selenium
├── .env.example
├── publish.ps1              # 一鍵把這個資料夾發佈到 GitHub
└── .github/workflows/docker.yml   # 建置並推送 GHCR（amd64 + arm64）
```

## 免責聲明

- 僅供**你自己的帳號**、每天一次使用；請勿用來代領他人帳號或大量註冊。
- 這是瀏覽器自動化，不是官方 API。Unity 或 CookApps 隨時可能改版、加上驗證或限制，
  也可能與其服務條款相牴觸 —— 風險自負。
- 本專案與 CookApps、Unity 均無任何關係。

## License

MIT，見 [LICENSE](LICENSE)。靈感來自 [simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer)。
