#!/usr/bin/env python3
"""
ninja-defenders-free
====================

Claim the daily free "Ruby Cat Stone" bundle from the Ninja Defenders web shop
(https://catshinobi.xsolla.site/) with zero human interaction.

The Xsolla web shop has no username/password: you type your 26 character
in-game account ID into a field (``#user-id-input``), press "Log in", and the
shop loads your account.  This script does that, claims the free daily item,
and exits -- so ``docker run --rm`` tears the container down by itself.

Structure and error-handling are deliberately modelled on
simao-silva/noip-renewer (MIT), which does the same kind of job for No-IP.

Exit codes
----------
0   reward claimed, or already claimed today (idempotent, safe for cron)
1   automation failure (selector drift, network problem, login rejected)
2   configuration error (bad / missing user id)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    JavascriptException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# --------------------------------------------------------------------------- #
# Configuration (everything can be overridden with environment variables)
# --------------------------------------------------------------------------- #

BASE_URL = os.getenv("SITE_URL", "https://catshinobi.xsolla.site/")

USER_ID_SELECTOR = os.getenv("USER_ID_SELECTOR", "#user-id-input")

#: The free/gift button on the store card.  These data attributes are stable
#: across languages, unlike the button label ("Free" / "免費" / "無料" ...).
FREE_BUTTON_SELECTOR = os.getenv(
    "FREE_BUTTON_SELECTOR",
    "button[data-testid='free-button'], "
    "button[data-button-type='free'], "
    "[data-testid='free-button']",
)

#: Words that may appear on the button that opens the login dialog.
LOGIN_OPEN_WORDS = [
    w.strip().lower()
    for w in os.getenv(
        "LOGIN_OPEN_WORDS",
        "log in,login,sign in,登入,登录,로그인,ログイン",
    ).split(",")
    if w.strip()
]

#: Words on the button that submits the user id.
LOGIN_SUBMIT_WORDS = [
    w.strip().lower()
    for w in os.getenv(
        "LOGIN_SUBMIT_WORDS",
        "log in,login,sign in,continue,enter,登入,登录,로그인,ログイン",
    ).split(",")
    if w.strip()
]

#: Words on the button that actually claims a free item.
CLAIM_WORDS = [
    w.strip().lower()
    for w in os.getenv(
        "CLAIM_WORDS",
        "free,get,claim,receive,obtain,grab,collect,"
        "領取,免費,免费领取,무료,받기,수령,受け取る,無料",
    ).split(",")
    if w.strip()
]

#: Extra hint used to pick the right card when several are clickable.
TARGET_WORDS = [
    w.strip().lower()
    for w in os.getenv(
        "TARGET_WORDS",
        "ruby cat stone,ruby,cat stone,daily free,daily reward,"
        "紅寶石,红宝石,루비,ルビー",
    ).split(",")
    if w.strip()
]

#: Words that mean "the claim worked".
SUCCESS_WORDS = [
    w.strip().lower()
    for w in os.getenv(
        "SUCCESS_WORDS",
        "success,successfully,claimed,received,purchased,added,"
        "領取成功,已領取,成功,獲得,성공,받았,受け取り",
    ).split(",")
    if w.strip()
]

#: Words that mean "already claimed today" -- treated as success.
ALREADY_WORDS = [
    w.strip().lower()
    for w in os.getenv(
        "ALREADY_WORDS",
        "already claimed,already received,already purchased,come back tomorrow,"
        "next claim,owned,已擁有,已拥有,已購買,已购买,已領取過,明天再來,내일,明日",
    ).split(",")
    if w.strip()
]

#: Cookie / consent buttons that would otherwise swallow our clicks.
CONSENT_WORDS = [
    w.strip().lower()
    for w in os.getenv(
        "CONSENT_WORDS",
        "accept,accept all,agree,i agree,got it,ok,"
        "接受,同意,我知道了,동의,확인,同意する",
    ).split(",")
    if w.strip()
]

LOGIN_TIMEOUT = float(os.getenv("LOGIN_TIMEOUT", "60"))
CLAIM_TIMEOUT = float(os.getenv("CLAIM_TIMEOUT", "90"))
RESULT_TIMEOUT = float(os.getenv("RESULT_TIMEOUT", "60"))

HEADLESS = os.getenv("HEADLESS", "true").strip().lower() not in {"0", "false", "no"}

#: firefox (the image), or edge / chrome when running natively on Windows/macOS.
BROWSER = os.getenv("BROWSER", "firefox").strip().lower()

DEBUG = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes"}

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
)

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "/app/artifacts"))

#: Account IDs are 26 alphanumeric characters (documented in the shop FAQ).
USER_ID_RE = re.compile(r"^[A-Za-z0-9]{26}$")

#: Buttons we must never press while hunting for the claim button.
DANGEROUS_WORDS = (
    "delete",
    "remove",
    "logout",
    "log out",
    "sign out",
    "取消訂閱",
    "登出",
    "삭제",
)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def norm(text: str | None) -> str:
    """Collapse whitespace and lower-case a string for loose comparisons."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def matches(text: str, words: list[str]) -> bool:
    """True when *text* equals or contains any of *words*."""
    if not text:
        return False
    return any(word == text or word in text for word in words)


def visible(element) -> bool:
    try:
        return bool(element.is_displayed())
    except (StaleElementReferenceException, WebDriverException):
        return False


def click(driver, element) -> bool:
    """Scroll to *element*, click it, fall back to a JS click if intercepted."""
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            element,
        )
    except (JavascriptException, StaleElementReferenceException):
        pass

    try:
        element.click()
        return True
    except (ElementClickInterceptedException, ElementNotInteractableException):
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except (JavascriptException, StaleElementReferenceException):
            return False
    except (StaleElementReferenceException, WebDriverException):
        return False


def save_artifacts(driver, tag: str) -> None:
    """Dump a screenshot and the DOM -- the fastest way to fix a selector."""
    try:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        png = ARTIFACTS_DIR / f"{stamp}-{tag}.png"
        html = ARTIFACTS_DIR / f"{stamp}-{tag}.html"
        driver.save_screenshot(str(png))
        html.write_text(driver.page_source, encoding="utf-8")
        log(f"Debug artifacts written to {ARTIFACTS_DIR}")
    except Exception as exc:  # never mask the original failure
        log(f"Could not write debug artifacts: {exc}")


def page_text(driver) -> str:
    try:
        return norm(driver.find_element(By.TAG_NAME, "body").text)
    except WebDriverException:
        return ""


def toast_text(driver) -> str:
    """Text of transient popups/toasts only, to avoid false positives."""
    selectors = (
        "[role='alert']",
        "[role='status']",
        "[class*='toast']",
        "[class*='snackbar']",
        "[class*='notification']",
        "[class*='Toast']",
        "[class*='Snackbar']",
    )
    chunks = []
    for selector in selectors:
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                if visible(element):
                    chunks.append(element.text)
        except WebDriverException:
            continue
    return norm(" ".join(chunks))


def alerts_text(driver) -> str:
    """Visible error messages, used to fail fast on a rejected login."""
    chunks = []
    for selector in ("[role='alert']", "[class*='error']", "[class*='Error']", "[class*='invalid']"):
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                if visible(element):
                    text = norm(element.text)
                    if text:
                        chunks.append(text)
        except WebDriverException:
            continue
    return " ".join(chunks)


def buttons(driver):
    try:
        return driver.find_elements(By.XPATH, "//button | //*[@role='button']")
    except WebDriverException:
        return []


def find_buttons_by_text(driver, words: list[str]):
    found = []
    for element in buttons(driver):
        if not visible(element):
            continue
        text = norm(element.text)
        if matches(text, words):
            found.append((element, text))
    return found


def session_state(driver) -> dict:
    """Inspect cookies / localStorage for something that looks like a token."""
    script = """
    const out = {cookies: document.cookie || '', keys: []};
    try {
        for (let i = 0; i < localStorage.length; i++) out.keys.push(localStorage.key(i));
    } catch (e) {}
    return out;
    """
    try:
        return driver.execute_script(script) or {"cookies": "", "keys": []}
    except (JavascriptException, WebDriverException):
        return {"cookies": "", "keys": []}


def has_session(driver) -> bool:
    state = session_state(driver)
    blob = norm(state.get("cookies", "") + " " + " ".join(state.get("keys", [])))
    return bool(re.search(r"token|jwt|auth|session|xsolla", blob))


# --------------------------------------------------------------------------- #
# Browser
# --------------------------------------------------------------------------- #


def build_driver():
    """Firefox by default (that is what the image ships), Edge/Chrome on request."""
    driver_path = os.getenv("WEBDRIVER_PATH")
    profile_dir = os.getenv("BROWSER_PROFILE_DIR")

    if BROWSER in {"edge", "msedge", "microsoft-edge"}:
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.edge.service import Service as EdgeService

        options = EdgeOptions()
        if HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        if profile_dir:
            options.add_argument(f"--user-data-dir={Path(profile_dir).absolute()}")
        service = EdgeService(executable_path=driver_path) if driver_path else EdgeService()
        log(f"Starting Edge ({'headless' if HEADLESS else 'visible'})")
        return webdriver.Edge(options=options, service=service)

    if BROWSER in {"chrome", "google-chrome"}:
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.chrome.service import Service as ChromeService

        options = ChromeOptions()
        if HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        if profile_dir:
            options.add_argument(f"--user-data-dir={Path(profile_dir).absolute()}")
        service = ChromeService(executable_path=driver_path) if driver_path else ChromeService()
        log(f"Starting Chrome ({'headless' if HEADLESS else 'visible'})")
        return webdriver.Chrome(options=options, service=service)

    options = Options()
    if HEADLESS:
        options.add_argument("-headless")
    options.add_argument("--width=1440")
    options.add_argument("--height=1000")

    # A plain Firefox UA: the default one advertises "Headless".
    options.set_preference("general.useragent.override", USER_AGENT)
    options.set_preference("intl.accept_languages", "en-US,en")
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    options.set_preference("dom.disable_beforeunload", True)

    geckodriver = os.getenv("GECKODRIVER_PATH", "/usr/local/bin/geckodriver")
    service = Service(executable_path=geckodriver) if Path(geckodriver).exists() else Service()

    log(f"Starting Firefox ({'headless' if HEADLESS else 'visible'})")
    return webdriver.Firefox(options=options, service=service)


# --------------------------------------------------------------------------- #
# Overlays (cookie banner, promo pop-ups)
# --------------------------------------------------------------------------- #


def dismiss_overlays(driver) -> None:
    """Close consent banners and promo pop-ups that would eat our clicks."""
    for _ in range(3):
        acted = False

        try:
            for element in driver.find_elements(
                By.XPATH,
                "//*[self::button or @role='button' or self::a]"
                "[@aria-label and contains(translate(@aria-label,'CLOSE','close'),'close')]",
            ):
                if visible(element) and click(driver, element):
                    acted = True
                    break
        except WebDriverException:
            pass

        if not acted:
            for element, text in find_buttons_by_text(driver, CONSENT_WORDS):
                if len(text) <= 20 and click(driver, element):
                    log(f'Dismissed overlay ("{text}")')
                    acted = True
                    break

        if not acted:
            return
        time.sleep(1.0)


# --------------------------------------------------------------------------- #
# Login by account id
# --------------------------------------------------------------------------- #


class LoginRejected(RuntimeError):
    pass


def wait_for_user_id_input(driver, timeout: float):
    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, USER_ID_SELECTOR))
        )
    except TimeoutException:
        return None


def open_login_form(driver):
    """Open the login dialog and return the user id input element."""
    field = wait_for_user_id_input(driver, 3)
    if field is not None:
        return field

    log("Opening login dialog")
    for element, text in find_buttons_by_text(driver, LOGIN_OPEN_WORDS):
        if len(text) > 24:  # "Log in" only -- skip whole sentences
            continue
        if click(driver, element):
            field = wait_for_user_id_input(driver, 15)
            if field is not None:
                return field

    log("Login button not found, trying the input directly")
    return wait_for_user_id_input(driver, 10)


def fill_user_id(driver, field, user_id: str) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", field)
    try:
        field.click()
    except WebDriverException:
        pass
    field.clear()
    field.send_keys(user_id)

    # React controlled inputs sometimes ignore send_keys-only updates.
    driver.execute_script(
        """
        const el = arguments[0];
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        """,
        field,
    )

    entered = norm(field.get_attribute("value"))
    if entered != norm(user_id):
        raise LoginRejected(f"User id was not accepted by the form (got {entered!r})")
    log(f"Entered user id {user_id}")


def dialog_scope(driver, field=None):
    """Return the element that looks like the open login dialog."""
    for selector in ("[role='dialog']", "[class*='modal']", "[class*='Modal']", "form"):
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                if visible(element) and element.find_elements(By.CSS_SELECTOR, USER_ID_SELECTOR):
                    return element
        except WebDriverException:
            continue

    if field is not None:
        node = field
        for _ in range(5):
            try:
                node = node.find_element(By.XPATH, "..")
            except (NoSuchElementException, StaleElementReferenceException):
                return None
            try:
                if node.find_elements(By.XPATH, ".//button"):
                    return node
            except WebDriverException:
                return None
    return None


def dialog_buttons(scope):
    try:
        return [
            b
            for b in scope.find_elements(By.XPATH, ".//button | .//*[@role='button']")
            if visible(b) and b.is_enabled()
        ]
    except WebDriverException:
        return []


def submit_login(driver, field, strategy: int = 1) -> None:
    """Submit the id: 1 = click by label, 2 = any submit button, 3 = press Enter."""
    if strategy == 3:
        try:
            field.send_keys(Keys.ENTER)
        except WebDriverException as exc:
            raise LoginRejected(f"Could not press Enter: {exc}") from exc
        log("Pressed Enter in the account id field")
        return

    scope = dialog_scope(driver, field)
    if scope is None:
        raise LoginRejected("Login dialog could not be located")

    candidates = dialog_buttons(scope)
    if not candidates:
        if strategy == 2:
            raise LoginRejected("Login dialog has no buttons")
        return submit_login(driver, field, strategy=3)

    if strategy == 1:
        for element in candidates:
            text = norm(element.text)
            if text and len(text) <= 20 and matches(text, LOGIN_SUBMIT_WORDS):
                if click(driver, element):
                    log(f'Clicked login button ("{text}")')
                    return

    for element in candidates:
        if element.get_attribute("type") == "submit" and click(driver, element):
            log("Clicked submit button")
            return

    for element in candidates:
        text = norm(element.text)
        if not text or any(word in text for word in ("cancel", "close", "back", "取消", "닫기")):
            continue
        if click(driver, element):
            log(f'Clicked "{text}"')
            return

    submit_login(driver, field, strategy=3)


def login_error_text(driver, scope) -> str:
    """Visible, short validation errors -- preferably from inside the dialog."""
    chunks = []
    roots = [scope] if scope is not None else []
    roots.append(driver)
    for root in roots:
        for selector in (
            "[role='alert']",
            "[class*='error']",
            "[class*='Error']",
            "[class*='invalid']",
        ):
            try:
                for element in root.find_elements(By.CSS_SELECTOR, selector):
                    if not visible(element):
                        continue
                    text = norm(element.text)
                    if text and len(text) <= 160 and text not in chunks:
                        chunks.append(text)
            except WebDriverException:
                continue
    return " | ".join(chunks)


def has_captcha(driver) -> bool:
    try:
        for element in driver.find_elements(
            By.CSS_SELECTOR,
            "iframe[src*='captcha'], iframe[src*='turnstile'], iframe[src*='hcaptcha'], "
            "[class*='captcha'], [id*='captcha']",
        ):
            if visible(element):
                return True
    except WebDriverException:
        return False
    return False


def user_id_input_visible(driver) -> bool:
    try:
        return any(visible(e) for e in driver.find_elements(By.CSS_SELECTOR, USER_ID_SELECTOR))
    except WebDriverException:
        return False


def wait_login(driver, timeout: float) -> str:
    """Return "ok", "error:<text>" or "timeout"."""
    deadline = time.time() + timeout
    closed_since = None

    while time.time() < deadline:
        if has_session(driver):
            return "ok"

        error = login_error_text(driver, None)
        if error:
            return "error:" + error

        if user_id_input_visible(driver):
            closed_since = None
        else:
            closed_since = closed_since or time.time()
            if time.time() - closed_since >= 2.0:
                return "ok"

        time.sleep(0.5)

    return "timeout"


def login(driver, user_id: str) -> None:
    field = open_login_form(driver)
    if field is None:
        # With a persistent profile the shop may already be logged in, in which
        # case there is no login button and no dialog at all.
        if find_free_button(driver) is not None:
            log("No login form, but the store is loaded -- reusing the existing session")
            return
        raise LoginRejected(
            f"User id input ({USER_ID_SELECTOR}) never appeared -- "
            "the shop layout may have changed."
        )

    for attempt in (1, 2, 3):
        if attempt > 1:
            field = wait_for_user_id_input(driver, 5) or field

        fill_user_id(driver, field, user_id)
        log(f"Login attempt {attempt}")
        submit_login(driver, field, strategy=attempt)

        outcome = wait_login(driver, LOGIN_TIMEOUT if attempt == 1 else 30)
        if outcome == "ok":
            log("Logged in")
            dismiss_overlays(driver)
            return
        if outcome.startswith("error:"):
            raise LoginRejected(outcome[6:])
        if has_captcha(driver):
            raise LoginRejected(
                "The shop is asking for a captcha -- a headless browser cannot pass it. "
                "Try HEADLESS=false on a machine with a screen."
            )
        log("Login did not complete; retrying with the next submit strategy")

    raise LoginRejected("Login did not complete after 3 attempts")


# --------------------------------------------------------------------------- #
# Claiming the free daily item
# --------------------------------------------------------------------------- #


def card_text(element, levels: int = 6) -> str:
    """Text of the closest ancestor that looks like an item card."""
    node = element
    best = ""
    for _ in range(levels):
        try:
            node = node.find_element(By.XPATH, "..")
        except (NoSuchElementException, StaleElementReferenceException):
            break
        try:
            text = norm(node.text)
        except (StaleElementReferenceException, WebDriverException):
            break
        if len(text) >= 20:
            best = text
            break
    return best


def find_free_button(driver):
    """The store's free/gift button, targeted by data attribute (language agnostic)."""
    try:
        for element in driver.find_elements(By.CSS_SELECTOR, FREE_BUTTON_SELECTOR):
            if visible(element):
                return element
    except WebDriverException:
        pass
    return None


def button_is_owned(button) -> bool:
    """True once the item has been claimed (button disabled / shows "owned")."""
    try:
        if button.get_attribute("disabled") is not None:
            return True
        if "disabled" in (button.get_attribute("class") or ""):
            return True
        return bool(
            button.find_elements(By.CSS_SELECTOR, "[data-testid='owned'], [data-id='owned']")
        )
    except (StaleElementReferenceException, WebDriverException):
        return False


def pick_claim_button(driver):
    """Fallback for locales/markups without the data attributes: match the label."""
    candidates = []
    for element in buttons(driver):
        if not visible(element) or not element.is_enabled():
            continue
        text = norm(element.text)
        if not text or any(word in text for word in DANGEROUS_WORDS):
            continue
        if matches(text, CLAIM_WORDS):
            candidates.append((element, text, card_text(element)))

    if not candidates:
        return None, None

    for element, text, card in candidates:
        if any(word in card for word in TARGET_WORDS):
            return element, card or text

    if len(candidates) == 1:
        return candidates[0][0], candidates[0][2] or candidates[0][1]

    log(f"{len(candidates)} candidate buttons, using the first one")
    return candidates[0][0], candidates[0][2] or candidates[0][1]


def confirm_dialog(driver) -> bool:
    """Click through a "claim this item?" confirmation if one appears."""
    time.sleep(1.5)
    for scope_selector in ("[role='dialog']", "[class*='modal']", "[class*='Modal']"):
        try:
            scopes = [s for s in driver.find_elements(By.CSS_SELECTOR, scope_selector) if visible(s)]
        except WebDriverException:
            continue
        for scope in scopes:
            try:
                scope_buttons = scope.find_elements(By.XPATH, ".//button | .//*[@role='button']")
            except WebDriverException:
                continue
            for element in scope_buttons:
                if not visible(element) or not element.is_enabled():
                    continue
                text = norm(element.text)
                if matches(text, CLAIM_WORDS + ["confirm", "yes", "ok", "確定", "확인"]):
                    if click(driver, element):
                        log(f'Confirmed dialog ("{text}")')
                        return True
    return False


def wait_for_result(driver, button, timeout: float) -> str:
    """Wait until the page says the claim worked."""
    deadline = time.time() + timeout
    missing = 0

    while time.time() < deadline:
        toast = toast_text(driver)
        if matches(toast, SUCCESS_WORDS):
            log(f"Toast: {toast[:120]}")
            return "claimed"
        if matches(toast, ALREADY_WORDS):
            log(f"Toast: {toast[:120]}")
            return "already"

        if button is not None and button_is_owned(button):
            log("Free item is now marked as owned")
            return "claimed"

        if button is not None:
            try:
                button.is_enabled()
            except StaleElementReferenceException:
                log("Free button was re-rendered")
                button = None
            except WebDriverException:
                pass
        else:
            current = find_free_button(driver)
            if current is None:
                missing += 1
                if missing >= 2:
                    log("Free button disappeared from the page")
                    return "claimed"
            elif button_is_owned(current):
                log("Free item is now marked as owned")
                return "claimed"
            else:
                button = current
                missing = 0

        if matches(page_text(driver), ALREADY_WORDS):
            return "already"

        time.sleep(1.0)

    if matches(toast_text(driver), SUCCESS_WORDS):
        return "claimed"
    return "unknown"


def claim(driver) -> str:
    deadline = time.time() + CLAIM_TIMEOUT
    button = None
    card = ""

    while time.time() < deadline:
        button = find_free_button(driver)
        if button is not None:
            card = card_text(button)
            if button_is_owned(button):
                log("Free item already shows as owned")
                return "already"
        else:
            button, card = pick_claim_button(driver)
            if button is None:
                dismiss_overlays(driver)
                log("Free item button not found yet, waiting")
                time.sleep(3)
                continue

        log(f'Claiming: "{card[:100]}"')
        if click(driver, button):
            break
        log("Click was blocked, retrying")
        time.sleep(2)

    if button is None:
        raise RuntimeError(
            f"No free item button found within {CLAIM_TIMEOUT:.0f}s "
            "(the store layout changed, or the offer is closed)"
        )

    for _ in range(3):
        if not confirm_dialog(driver):
            break
        time.sleep(1.0)

    return wait_for_result(driver, button, RESULT_TIMEOUT)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def get_user_id(cli_value: str | None) -> str:
    user_id = (cli_value or os.getenv("NINJA_USER_ID") or os.getenv("USER_ID") or "").strip()

    # Nobody likes a one-line error when they double-clicked a .bat file.
    if not user_id and sys.stdin is not None and sys.stdin.isatty():
        log("No account id supplied.")
        for _ in range(3):
            try:
                typed = input("Account ID (26 letters/digits): ").strip()
            except (EOFError, KeyboardInterrupt):
                raise SystemExit("Aborted while asking for the account id")
            if USER_ID_RE.match(typed):
                return typed
            log(f"{typed!r} is not a 26 character id -- find it at the bottom of the in-game profile page.")

    if not user_id:
        raise SystemExit(
            "Missing account id.\n"
            "  Docker : docker run --rm --shm-size=1g -e NINJA_USER_ID=<26 chars> ninja-defenders-free\n"
            "  Local  : python claim.py <26 chars>\n"
            "  Where  : in game, profile picture (top left) -> the id sits at the bottom of the page."
        )

    if not USER_ID_RE.match(user_id):
        raise SystemExit(
            "Invalid account id: expected 26 letters/digits (the account id shown at the "
            f"bottom of the in-game profile), got {user_id!r}"
        )
    return user_id


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Claim the daily free Ruby Cat Stone bundle on the Ninja Defenders web shop."
    )
    parser.add_argument("user_id", nargs="?", help="26 character in-game account id")
    parser.add_argument("--debug", action="store_true", help="save screenshot + DOM on failure")
    parser.add_argument("--visible", action="store_true", help="run a visible browser")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global DEBUG, HEADLESS

    args = parse_args(argv or sys.argv[1:])
    DEBUG = DEBUG or args.debug
    if args.visible:
        HEADLESS = False

    try:
        user_id = get_user_id(args.user_id)
    except SystemExit as exc:
        log(str(exc))
        return 2

    log(f"Ninja Defenders daily reward -- target {BASE_URL}")
    driver = None
    started = time.time()

    try:
        driver = build_driver()
        driver.set_page_load_timeout(90)
        driver.get(BASE_URL)
        log("Page loaded")
        dismiss_overlays(driver)

        login(driver, user_id)

        result = claim(driver)
        elapsed = time.time() - started

        if result == "claimed":
            log(f"Daily free Ruby Cat Stone claimed ({elapsed:.0f}s)")
            return 0
        if result == "already":
            log(f"Already claimed today ({elapsed:.0f}s), nothing to do")
            return 0

        log(f"Could not confirm the claim after {elapsed:.0f}s")
        save_artifacts(driver, "claim-unconfirmed")
        return 1

    except LoginRejected as exc:
        log(f"Login failed: {exc}")
        if driver is not None:
            save_artifacts(driver, "login-failed")
        return 1
    except TimeoutException as exc:
        log(f"Timed out: {exc}")
        if driver is not None:
            save_artifacts(driver, "timeout")
        return 1
    except RuntimeError as exc:
        log(f"Failed: {exc}")
        if driver is not None:
            save_artifacts(driver, "claim-failed")
        return 1
    except WebDriverException as exc:
        log(f"Browser error: {exc.msg or exc}")
        if driver is not None:
            save_artifacts(driver, "browser-error")
        return 1
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass


if __name__ == "__main__":
    sys.exit(main())
