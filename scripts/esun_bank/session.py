"""Authentication, credential loading, process locking, and session cleanup."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import tempfile
from pathlib import Path
from typing import Any

ESB_URL = "https://ebank.esunbank.com.tw/esb/"
GLOBAL_CREDENTIALS_FILE = Path("~/.hermes/esun-bank/credentials.json").expanduser()
DEFAULT_LOCK_FILE = Path(tempfile.gettempdir()) / "esun-bank-cli-session.lock"

ENV_ID = "ESUN_ID"
ENV_USER = "ESUN_USER"
ENV_PASSWORD = "ESUN_PASSWORD"


class CliError(RuntimeError):
    pass


class SessionLock:
    """Prevent two local CLI processes from logging into the same bank account."""

    def __init__(self, path: Path = DEFAULT_LOCK_FILE, timeout_ms: int = 120_000) -> None:
        self.path = path
        self.timeout_ms = timeout_ms
        self.file = None

    async def __aenter__(self) -> "SessionLock":
        deadline = asyncio.get_running_loop().time() + self.timeout_ms / 1000
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        while True:
            if self._try_lock():
                self.file.seek(0)
                self.file.truncate()
                self.file.write(str(os.getpid()).encode("ascii"))
                self.file.flush()
                return self
            if asyncio.get_running_loop().time() >= deadline:
                raise CliError(f"Timed out waiting for E.SUN session lock: {self.path}")
            await asyncio.sleep(0.25)

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self.file:
            return
        try:
            self._unlock()
        finally:
            self.file.close()
            self.file = None

    def _try_lock(self) -> bool:
        if os.name == "nt":
            import msvcrt
            self.file.seek(0)
            try:
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False

        import fcntl
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(self) -> None:
        if os.name == "nt":
            import msvcrt
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl
        fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)


def _check_permissions(path: Path) -> None:
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise CliError(f"Credentials file permissions are too open: {path}. Run chmod 600.")


def _read_credentials_file(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        raise CliError(f"Credentials file not found: {path}")
    _check_permissions(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CliError(f"Credentials file is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise CliError("Credentials file must contain a JSON object.")
    return data


def load_credentials(args: argparse.Namespace) -> dict[str, str]:
    """Load one account-level E.SUN credential shared by all Hermes profiles."""

    data: dict[str, Any] = {}
    explicit = getattr(args, "credentials_file", None)
    env_file = os.environ.get("ESUN_CREDENTIALS_FILE")

    if explicit is not None:
        if not explicit:
            raise CliError("Credentials file path must not be empty.")
        data = _read_credentials_file(Path(explicit))
    elif env_file is not None:
        if not env_file:
            raise CliError("ESUN_CREDENTIALS_FILE must not be empty.")
        data = _read_credentials_file(Path(env_file))
    elif GLOBAL_CREDENTIALS_FILE.exists():
        data = _read_credentials_file(GLOBAL_CREDENTIALS_FILE)

    user_id = data.get("id") or os.environ.get(ENV_ID)
    username = data.get("user") or os.environ.get(ENV_USER)
    password = data.get("password") or os.environ.get(ENV_PASSWORD)

    if getattr(args, "prompt_missing", False):
        user_id = user_id or input("E.SUN ID / tax ID: ").strip()
        username = username or input("E.SUN user name: ").strip()
        password = password or getpass.getpass("E.SUN password: ")

    missing = [
        name for name, value in {
            ENV_ID: user_id,
            ENV_USER: username,
            ENV_PASSWORD: password,
        }.items() if not value
    ]
    if missing:
        raise CliError(
            "Missing credentials: " + ", ".join(missing)
            + f". Configure {GLOBAL_CREDENTIALS_FILE}, ESUN_CREDENTIALS_FILE, or environment variables."
        )

    return {"id": str(user_id), "user": str(username), "password": str(password)}


async def login(page: Any, args: argparse.Namespace) -> None:
    creds = load_credentials(args)

    await page.goto(ESB_URL, wait_until="domcontentloaded", timeout=args.timeout_ms)
    await page.locator('input[name="id"]').fill(creds["id"])
    await page.locator('input[name="userName"]').fill(creds["user"])
    await page.locator('input[name="pxssword"]').fill(creds["password"])
    await page.get_by_role("button", name="登入").click()

    confirm = page.get_by_role("button", name="確定登入", exact=True)
    try:
        await confirm.wait_for(state="visible", timeout=4000)
        if not args.force_login:
            raise CliError(
                "E.SUN reports an existing login session. "
                "Re-run with --force-login only if you want to replace it."
            )
        await confirm.click()
    except CliError:
        raise
    except Exception:
        pass

    try:
        await page.wait_for_load_state("networkidle", timeout=min(args.timeout_ms, 15_000))
    except Exception:
        await page.wait_for_timeout(2500)

    if await page.locator('input[name="id"]').count():
        raise CliError("E.SUN login did not complete.")


async def logout(page: Any) -> None:
    """Best-effort logout from the original authenticated ESB page."""

    try:
        text_nodes = page.locator(".header-option-entry-text")
        opened = False
        for i in range(await text_nodes.count()):
            node = text_nodes.nth(i)
            if await node.is_visible() and (await node.inner_text()).strip() == "登出":
                await node.click()
                opened = True
                break

        if not opened:
            return

        await page.wait_for_timeout(300)
        confirms = page.get_by_role("button", name="立即登出", exact=True)
        for i in range(await confirms.count()):
            confirm = confirms.nth(i)
            if await confirm.is_visible():
                await confirm.click()
                break

        try:
            await page.get_by_text("重新登入", exact=True).wait_for(
                state="visible",
                timeout=8_000,
            )
        except Exception:
            await page.wait_for_timeout(2500)
    except Exception:
        pass
