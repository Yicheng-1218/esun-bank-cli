"""登入、登出與瀏覽器 session 共用流程。"""

import argparse
import getpass
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from playwright.async_api import Frame, Page


DEFAULT_URL = "https://ebank.esunbank.com.tw/index.jsp"
ENV_ID = "ESUN_ID"
ENV_USER = "ESUN_USER"
ENV_PASSWORD = "ESUN_PASSWORD"
SKILL_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CREDENTIALS_FILE = SKILL_DIR / "credentials.json"
LOGIN_SUCCESS_TEXT = "登入成功"
LOGOUT_SELECTOR = 'a.log_out, a[href="/fco/fco08002/logout"], a[href*="/fco/fco08002/logout"]'

CommandHandler = Callable[[Frame], Awaitable[dict[str, Any]]]


class CliError(RuntimeError):
    """CLI 可預期錯誤，用於輸出簡潔的使用者訊息。"""

    pass


def load_credentials(args: argparse.Namespace) -> dict[str, str]:
    """依序從參數、credentials.json、環境變數或互動提示載入登入憑證。"""

    data: dict[str, Any] = {}
    credentials_file = args.credentials_file
    if credentials_file:
        path = Path(credentials_file).expanduser()
        if not path.exists():
            raise CliError(f"Credentials file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
    elif DEFAULT_CREDENTIALS_FILE.exists():
        data = json.loads(DEFAULT_CREDENTIALS_FILE.read_text(encoding="utf-8"))

    user_id = args.id or data.get("id") or os.environ.get(ENV_ID)
    username = args.user or data.get("user") or os.environ.get(ENV_USER)
    password = args.password or data.get(
        "password") or os.environ.get(ENV_PASSWORD)

    if args.prompt_missing:
        user_id = user_id or input("E.SUN ID / tax ID: ").strip()
        username = username or input("E.SUN user name: ").strip()
        password = password or getpass.getpass("E.SUN password: ")

    missing = [
        name
        for name, value in {
            ENV_ID: user_id,
            ENV_USER: username,
            ENV_PASSWORD: password,
        }.items()
        if not value
    ]
    if missing:
        raise CliError(
            "Missing credentials: "
            + ", ".join(missing)
            + ". Create credentials.json in the skill directory, set environment variables, "
            + "pass CLI options, or use --credentials-file."
        )

    return {"id": str(user_id), "user": str(username), "password": str(password)}


async def get_main_frame(page: Page) -> Frame:
    """取得玉山網銀主要操作 iframe。"""

    frame = page.frame(name="iframe1")
    if frame:
        return frame
    if len(page.frames) > 1:
        return page.frames[1]
    return page


async def login(page: Page, credentials: dict[str, str], url: str, timeout_ms: int) -> Any:
    """開啟登入頁、填入憑證並等待登入成功。"""

    await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
    frame = await get_main_frame(page)

    await frame.locator('[id="loginform:custid"]').fill(credentials["id"])
    await frame.locator('[id="loginform:name"]').fill(credentials["user"])
    await frame.locator('[id="loginform:pxsswd"]').fill(credentials["password"])
    await complete_login(frame, timeout_ms)

    return frame


async def complete_login(frame: Frame, timeout_ms: int) -> None:
    """送出登入表單，並處理可能出現的重複登入確認。"""

    await frame.locator('[id="loginform:linkCommand"]').click()
    await confirm_duplicate_login_if_present(frame)
    await wait_for_logged_in_home(frame, timeout_ms)


async def confirm_duplicate_login_if_present(frame: Frame) -> None:
    """若頁面出現重複登入確認按鈕，快速點選確認。"""

    confirm_button = frame.locator('button:has-text("確定登入")')
    try:
        await confirm_button.click(timeout=1500)
    except Exception:
        return


async def wait_for_logged_in_home(frame: Frame, timeout_ms: int) -> None:
    """等待登入成功訊息；逾時時嘗試回報頁面上的登入錯誤。"""

    try:
        await frame.get_by_text(LOGIN_SUCCESS_TEXT).wait_for(timeout=timeout_ms)
    except Exception as exc:
        message = await read_login_error(frame)
        if message:
            raise CliError(
                f"Login did not reach home page: {message}") from exc
        raise CliError(
            "Login did not reach home page before timeout.") from exc


async def read_login_error(frame: Frame) -> str | None:
    """從頁面文字中擷取登入失敗相關訊息。"""

    texts = await frame.locator("body").all_inner_texts()
    body = "\n".join(texts)
    for line in body.splitlines():
        if "登入" in line and ("不正確" in line or "錯誤" in line or "失敗" in line):
            return line.strip()
    return None


async def logout(page: Page) -> None:
    """嘗試點擊登出連結；失敗時不影響原本查詢結果或錯誤。"""

    try:
        frame = await get_main_frame(page)
        await frame.locator(LOGOUT_SELECTOR).first.click(timeout=3000)
        await page.wait_for_timeout(500)
    except Exception:
        return


async def run_with_login(args: argparse.Namespace, handler: CommandHandler) -> dict[str, Any]:
    """執行共用的開瀏覽器、登入、查詢、登出與關閉流程。"""

    credentials = load_credentials(args)

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise CliError(
            "Playwright is not installed. Run: python -m pip install playwright && "
            "python -m playwright install chromium"
        ) from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed)
        page = await browser.new_page()
        try:
            frame = await login(page, credentials, args.url, args.timeout_ms)
            result = await handler(frame)
        finally:
            await logout(page)
            if not args.keep_open:
                await browser.close()

    return result
