# ninja-defenders-free

<p align="center">
  <img src="assets/icon.webp" alt="Ninja Defenders icon" width="128" height="128">
</p>

**English** | [繁體中文](README.md)

Automatically claims the once-a-day free **1 Daily Free Ruby Cat Stone** from the *Ninja Defenders : Cat Shinobi* Unity Web Shop. Fully unattended: it runs once and exits.

Login needs only your **26-character in-game account ID**. Structure and containerisation are modelled on [simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer) (MIT).

```bash
docker run --rm --shm-size=1g -e NINJA_USER_ID=<your 26-char ID> ninja-defenders-free
```

## How it works

1. Starts a headless browser (Firefox in the image; Edge by default on Windows) and opens <https://shop.unity.com/crescento/game/webshop-cc08e9e8>.
2. Dismisses the cookie banner and logs in with the ID (`input[name="playerId"]`). The submit step tries button text → `type=submit` → Enter, up to 3 rounds. An existing session skips login.
3. Finds the free card's button by a language-independent selector (`a[data-slot="product-card"][href*="unity_web_free"] button[data-slot="buy-cta"]`, with older `data-testid="free-button"` selectors as fallback).
4. If the button is disabled or shows "owned", it was already claimed today → exit 0. Otherwise it clicks, handles any confirmation dialog, and waits for the owned state or a success message.

## Quick start

### Docker (any machine, including NAS)

```bash
git clone https://github.com/iamafreeride/ninja-defenders-free.git
cd ninja-defenders-free
docker build -t ninja-defenders-free .
docker run --rm --shm-size=1g -e NINJA_USER_ID=<your 26-char ID> ninja-defenders-free
```

Or with compose:

```bash
cp .env.example .env      # set NINJA_USER_ID
docker compose up --build
```

### Windows (no Docker)

1. Install Python 3.9+ (tick **Add python.exe to PATH**).
2. Double-click **`run.bat`**. The first run creates `.venv` and installs selenium (~30 s), then asks for the ID if none is set. Put it in `.env` as `NINJA_USER_ID=` to skip the prompt.
3. Edge (built into Windows 10/11) is used by default; no driver install needed.

Manual equivalent:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python claim.py <26-char ID>
```

### Finding your ID

In the game: top-left avatar → profile page → the 26-character string at the **bottom** (next to `Copy`).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NINJA_USER_ID` | required | 26-char account ID (or pass as first CLI argument) |
| `BROWSER` | `firefox` | `firefox` / `edge` / `chrome` (`run.bat` sets `edge`) |
| `HEADLESS` | `true` | `false` opens a visible browser |
| `DEBUG` | `false` | Save screenshot + DOM to `artifacts/` on failure |
| `SITE_URL` | `https://shop.unity.com/crescento/game/webshop-cc08e9e8` | Shop URL |
| `LOGIN_TIMEOUT` | `60` | Seconds to wait for login |
| `CLAIM_TIMEOUT` | `90` | Seconds to wait for the free button |
| `RESULT_TIMEOUT` | `60` | Seconds to wait for owned state / success message |
| `USER_ID_SELECTOR` | `#user-id-input, input[name='playerId']` | ID input selector |
| `WEBDRIVER_PATH` | auto | geckodriver / msedgedriver path if auto-download fails |
| `BROWSER_PROFILE_DIR` | none | Browser profile dir to keep the login session |
| `ARTIFACTS_DIR` | `/app/artifacts` | Debug output directory |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Claimed, or already claimed today (safe to re-run) |
| `1` | Automation failure: element not found, timeout, login rejected |
| `2` | Config error: ID missing or not 26 alphanumerics |

## Scheduling (once a day)

Linux / NAS:

```cron
5 9 * * * cd /opt/ninja-defenders-free && /usr/bin/docker compose run --rm claim >> claim.log 2>&1
```

Windows Task Scheduler: run `C:\path\to\run.bat` (uncheck "only when user is logged on" and remove the trailing `pause` from `run.bat`), or call Docker directly as above.

## Troubleshooting

- **"Already claimed today"**: the account already claimed today (maybe manually). It exits 0 and will claim the next day. The "purchase time remaining" on the page is the event countdown, not a cooldown.
- **Stuck at "Opening login dialog"**: run with `DEBUG=true` and check `artifacts/`.
  - Different button text → set `LOGIN_SUBMIT_WORDS="log in,login,登入,..."`.
  - Captcha → headless can't pass it; run with `HEADLESS=false` on a machine with a display.
  - Firefox on Windows: `Unable to write to temporary directory` → point `TEMP`/`TMP` to a writable folder, or use `BROWSER=edge`.
- **Free button not found**: the shop layout changed. Check `artifacts/*.html` for `data-slot="buy-cta"` or `data-testid="free-button"`; override with `FREE_BUTTON_SELECTOR` (see `find_free_button` in `claim.py`).
- **Firefox crashes randomly (Docker)**: `/dev/shm` too small; use `--shm-size=1g` (already set in compose).

## Project layout

```
claim.py            login → find free button → claim → report
run.bat             Windows one-click runner
Dockerfile          Debian slim + Firefox ESR + geckodriver
docker-compose.yml
requirements.txt    selenium
.env.example
.github/workflows/docker.yml   build & push to GHCR (amd64 + arm64)
```

## Disclaimer

- For **your own account**, once a day. Do not use it to claim for others or mass-register.
- This is browser automation, not an official API. The shop may change, add verification, or consider this against its terms at any time. Use at your own risk.
- Not affiliated with CookApps or Unity.

## License

MIT, see [LICENSE](LICENSE). Inspired by [simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer).
