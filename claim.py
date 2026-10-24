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
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# --------------------------------------------------------------------------- #
# Configuration (everything can be overridden with environment variables)
# --------------------------------------------------------------------------- #

BASE_URL = os.getenv("SITE_URL", "https://catshinobi.xsolla.site/")

USER_ID_SELECTOR = os.getenv("USER_ID_SELECTOR", "#user-id-input")

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
        "next claim,已領取過,明天再來,明天再来,내일,明日",
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


def build_driver() -> webdriver.Firefox:
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


def submit_login(driver, field) -> None:
    """Press the button that submits the user id, staying inside the dialog."""
    scopes = []
    for xpath in (
        "./ancestor::form[1]",
        "./ancestor::*[@role='dialog'][1]",
        "./ancestor::*[contains(@class,'modal')][1]",
        "./ancestor::*[contains(@class,'Modal')][1]",
    ):
        try:
            scopes.append(field.find_element(By.XPATH, xpath))
        except NoSuchElementException:
            continue

    # No <form>/dialog wrapper: widen the search one ancestor at a time so we
    # never end up clicking the page header's own "Log in" button.
    if not scopes:
        node = field
        for _ in range(5):
            try:
                node = node.find_element(By.XPATH, "..")
            except (NoSuchElementException, StaleElementReferenceException):
                break
            scopes.append(node)

    for scope in scopes:
        try:
            candidates = scope.find_elements(By.XPATH, ".//button | .//*[@role='button']")
        except WebDriverException:
            continue

        for element in candidates:
            if not visible(element) or not element.is_enabled():
                continue
            text = norm(element.text)
            if matches(text, LOGIN_SUBMIT_WORDS) or text in {"→", ">"}:
                if click(driver, element):
                    log(f'Clicked login button ("{text}")')
                    return

        for element in candidates:
            if visible(element) and element.is_enabled() and element.get_attribute("type") == "submit":
                if click(driver, element):
                    log("Clicked submit button")
                    return

    # Last resort: the only button inside the dialog.
    for scope in scopes:
        try:
            candidates = [b for b in scope.find_elements(By.XPATH, ".//button") if visible(b) and b.is_enabled()]
        except WebDriverException:
            continue
        if len(candidates) == 1 and click(driver, candidates[0]):
            log("Clicked the only button in the dialog")
            return

    raise LoginRejected("Could not find the login submit button")


def user_id_input_visible(driver) -> bool:
    try:
        return any(visible(e) for e in driver.find_elements(By.CSS_SELECTOR, USER_ID_SELECTOR))
    except WebDriverException:
        return False


def wait_for_login(driver, timeout: float) -> None:
    """The dialog closing (or a token appearing) means the id was accepted."""
    deadline = time.time() + timeout
    closed_since = None

    while time.time() < deadline:
        error = alerts_text(driver)
        if error and any(
            word in error
            for word in ("invalid", "not found", "incorrect", "error", "無效", "오류", "エラー")
        ):
            raise LoginRejected(error)

        if has_session(driver):
            log("Session token detected")
            return

        if user_id_input_visible(driver):
            closed_since = None
        else:
            closed_since = closed_since or time.time()
            if time.time() - closed_since >= 2.0:
                log("Login dialog closed")
                return

        time.sleep(0.5)

    raise LoginRejected(f"Login did not complete within {timeout:.0f}s")


def login(driver, user_id: str) -> None:
    field = open_login_form(driver)
    if field is None:
        raise LoginRejected(
            f"User id input ({USER_ID_SELECTOR}) never appeared -- "
            "the shop layout may have changed."
        )
    fill_user_id(driver, field, user_id)
    submit_login(driver, field)
    wait_for_login(driver, LOGIN_TIMEOUT)
    dismiss_overlays(driver)


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


def pick_claim_button(driver):
    """Return (button, card description) or (None, None)."""
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

    # Prefer a button whose card mentions the target item.
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
    """Wait until the page tells us the claim worked."""
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

        if button is not None:
            try:
                if not button.is_enabled():
                    log("Claim button became disabled")
                    return "claimed"
            except StaleElementReferenceException:
                log("Claim button was re-rendered, re-checking the page")
                button = None
            except WebDriverException:
                pass
        else:
            # After a successful claim the free card usually stops being
            # clickable.  Require two consecutive misses so a re-render does
            # not look like a success.
            remaining, _ = pick_claim_button(driver)
            if remaining is None:
                missing += 1
                if missing >= 2:
                    log("No claimable free item left on the page")
                    return "claimed"
            else:
                missing = 0

        text = page_text(driver)
        if matches(text, ALREADY_WORDS):
            return "already"

        time.sleep(1.0)

    # Slow sites: give the toast one last chance.
    if matches(toast_text(driver), SUCCESS_WORDS):
        return "claimed"
    return "unknown"


def claim(driver) -> str:
    deadline = time.time() + CLAIM_TIMEOUT
    button = None
    while time.time() < deadline:
        button, card = pick_claim_button(driver)
        if button is not None:
            log(f'Claiming: "{card[:100]}"')
            if not click(driver, button):
                log("Click was blocked, retrying")
                time.sleep(2)
                continue
            break
        dismiss_overlays(driver)
        log("Free item not found yet, waiting")
        time.sleep(3)

    if button is None:
        raise RuntimeError(
            f"No claimable free item found within {CLAIM_TIMEOUT:.0f}s "
            "(already claimed today, or the selector needs updating)"
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
    if not user_id:
        raise SystemExit("Missing user id: set NINJA_USER_ID or pass it as the first argument")
    if not USER_ID_RE.match(user_id):
        raise SystemExit(
            "Invalid user id: expected 26 letters/digits (the account id shown at the "
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
        log("Logged in")

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
