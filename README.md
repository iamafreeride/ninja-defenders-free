# ninja-defenders-free

領取《Ninja Defenders : Cat Shinobi》網頁商店（Xsolla Web Shop）每日免費的
**1 Daily Free Ruby Cat Stone**，全自動、無人值守。

本專案的結構、容器化方式與錯誤處理，是照著
[simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer)（MIT）的精神改寫：
同樣是「用無頭瀏覽器做一件每天要做一次的小事，做完就讓容器結束」。

| | noip-renewer | 本專案 |
|---|---|---|
| 目標 | No-IP 免費網域續期 | Ninja Defenders 每日免費紅寶石 |
| 登入方式 | 帳號 + 密碼（+ TOTP） | **只有 26 碼遊戲內帳號 ID** |
| 登入欄位 | `#username` / `#password` | `#user-id-input` |
| 動作 | 逐一點 `Confirm` | 點免費商品的領取鈕 + 確認視窗 |
| 結束 | 登出後結束 | 領取成功後直接結束 |

> **一句話**：`docker run --rm -e NINJA_USER_ID=<你的26碼ID> ninja-defenders-free`
> 跑完（領到或今天已領）就自動退出，容器消失。

---

## 它是怎麼運作的

1. 啟動無頭 Firefox（geckodriver + Selenium），開啟 <https://catshinobi.xsolla.site/>。
2. 關掉 cookie 同意列 / 促銷彈窗。
3. 點右上角 **Log in**，在 `#user-id-input` 填入你的 26 碼帳號 ID，按下方登入鈕。
4. 等待登入完成（登入框關閉，或偵測到 token）。
5. 找出「免費」商品卡（預設以 `Ruby Cat Stone` / `Daily Free` 等字樣辨識），按下領取鈕。
6. 若有確認彈窗，一併按掉。
7. 等到成功提示（toast）或按鈕變成不可按，印出結果並以 exit code 0 結束。

**不需要** 帳號、密碼、TOTP —— Xsolla 這個商店是用「遊戲內帳號 ID」直接登入的。

---

## 快速開始

### 1. 取得你的帳號 ID

遊戲內 → 左上角頭像 → 個人檔案頁面最下方的 **26 碼英數 ID**（旁邊有 `Copy` 鈕）。
商店 FAQ 也是這樣寫的：*"The 26-character account ID, consisting of English letters and numbers,
is located at the bottom of the profile page."*

### 2. 建置映像

```bash
git clone https://github.com/<你的帳號>/ninja-defenders-free.git
cd ninja-defenders-free
docker build -t ninja-defenders-free .
```

### 3. 執行

```bash
docker run --rm --shm-size=1g \
  -e NINJA_USER_ID=AbCdEfGhIjKlMnOpQrStUvWxYz \
  ninja-defenders-free
```

或用 compose（推薦，設定寫在 `.env` 裡）：

```bash
cp .env.example .env      # 填入 NINJA_USER_ID
docker compose up --build
```

成功時終端機大概長這樣：

```
[20:31:02] Ninja Defenders daily reward -- target https://catshinobi.xsolla.site/
[20:31:09] Page loaded
[20:31:09] Opening login dialog
[20:31:10] Entered user id AbCdEfGhIjKlMnOpQrStUvWxYz
[20:31:10] Clicked login button ("Log in")
[20:31:14] Session token detected
[20:31:14] Logged in
[20:31:15] Claiming: "1 Daily Free Ruby Cat Stone ..."
[20:31:17] Confirmed dialog ("Claim")
[20:31:19] Toast: reward claimed successfully
[20:31:19] Daily free Ruby Cat Stone claimed (17s)
```

---

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `NINJA_USER_ID` | （必填） | 26 碼遊戲帳號 ID，也可用第一個命令列參數傳入 |
| `SITE_URL` | `https://catshinobi.xsolla.site/` | 商店網址 |
| `HEADLESS` | `true` | `false` 會開可見的瀏覽器（除錯用，需要 X server） |
| `DEBUG` | `false` | 失敗時額外保存截圖與 DOM 到 `artifacts/` |
| `LOGIN_TIMEOUT` | `60` | 等登入完成的秒數 |
| `CLAIM_TIMEOUT` | `90` | 等免費商品出現的秒數 |
| `RESULT_TIMEOUT` | `60` | 等成功提示的秒數 |
| `USER_ID_SELECTOR` | `#user-id-input` | 帳號輸入框的 CSS selector |
| `CLAIM_WORDS` | `free,get,claim,receive,領取,무료,...` | 領取鈕上可能出現的字 |
| `TARGET_WORDS` | `ruby cat stone,daily free,紅寶石,...` | 用來在多張卡片中挑對目標 |
| `SUCCESS_WORDS` / `ALREADY_WORDS` | 見 `claim.py` | 成功 / 今日已領的判定字串 |
| `ARTIFACTS_DIR` | `/app/artifacts` | 除錯產物輸出目錄 |

站方改版時，通常**不必改程式**，先試著用環境變數覆蓋文字比對即可。

---

## 退出碼

| 代碼 | 意義 |
|---|---|
| `0` | 已領取，或今天已經領過（可安全重跑） |
| `1` | 自動化失敗：找不到元素、逾時、登入被拒 |
| `2` | 設定錯誤：ID 缺少或格式不符（非 26 碼英數） |

搭配 cron / 排程器時，`1` 就該通知你。

---

## 排程（每天一次）

Linux crontab：

```cron
# 每天 09:05 領取
5 9 * * * cd /opt/ninja-defenders-free && /usr/bin/docker compose run --rm claim >> claim.log 2>&1
```

Windows 工作排程器：

```powershell
docker run --rm --shm-size=1g -e NINJA_USER_ID=<ID> ninja-defenders-free
```

> 每日獎勵一天只能領一次；重複執行是安全的（會回報 `Already claimed today` 並 exit 0）。

---

## 疑難排解

**卡在「Opening login dialog」**
登入鈕的文字可能是別的語言。覆蓋它：

```bash
-e LOGIN_OPEN_WORDS="log in,login,登入"
```

**登入了但找不到免費商品**
商店可能把免費項目放在別的區塊或改了標題。先看除錯產物：

```bash
docker run --rm --shm-size=1g -e DEBUG=true \
  -v "$PWD/artifacts:/app/artifacts" \
  -e NINJA_USER_ID=<ID> ninja-defenders-free
```

打開 `artifacts/*.png` 與 `*.html`，找出商品卡上的實際文字，然後：

```bash
-e TARGET_WORDS="ruby cat stone"  -e CLAIM_WORDS="free,claim,get"
```

**Firefox 隨機崩潰**
`/dev/shm` 太小。加上 `--shm-size=1g`（compose 檔已設定）。

**「Invalid user id」/ 登入被拒**
ID 必須是 26 碼英數，且要從**遊戲內**複製（不是商店網址、不是暱稱）。

---

## 專案結構

```
.
├── claim.py                 # 全部邏輯：登入 → 領取 → 判定結果
├── Dockerfile               # Debian slim + Firefox ESR + geckodriver
├── docker-compose.yml
├── requirements.txt         # selenium
├── .env.example
└── .github/workflows/docker.yml   # 建置並推送到 GHCR（amd64 + arm64）
```

## 免責聲明

- 僅供**你自己的帳號**、每天一次使用；請勿用來大量註冊或代領他人帳號。
- 這是瀏覽器自動化，不是官方 API。Xsolla 或 CookApps 隨時可能改版、加上驗證或限制，
  也可能與其服務條款相牴觸 —— 風險自負。
- 本專案與 CookApps、Xsolla 均無任何關係。

## License

MIT，見 [LICENSE](LICENSE)。靈感來自 [simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer)。
