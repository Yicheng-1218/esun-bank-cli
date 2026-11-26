"""Pure-HTTP E.SUN protocol client.

Provides a restricted read-only HTTP transport shared by the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from datetime import timedelta, timezone

TAIPEI = timezone(timedelta(hours=8))
from esun_bank.http_crypto import offline_login_request_body


class HttpProtocolError(Exception):
    """Public, fixed error category for reporting without banking response data."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "protocol_error",
        bank_result_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        # Bank result codes, unlike response bodies, contain no account
        # numbers or transaction records. Only accept four ASCII characters,
        # never an arbitrary response-derived value.
        self.bank_result_code = (
            bank_result_code
            if isinstance(bank_result_code, str)
            and re.fullmatch(r"[A-Z0-9]{4}", bank_result_code)
            else None
        )


@dataclass(frozen=True)
class CardSsoHandoff:
    redirect_url: str
    token: str


class EsunHttp:
    """Bank endpoint adapter with injected httpx client for offline testing.

    The caller owns the client, its cookies and cleanup. In particular, this
    class does not automatically navigate external SSO redirect URLs.
    """

    INIT = "mib-auth-portal/cpo08/cpo08001/home/init"
    LOGIN = "mib-auth-portal/cpo08/cpo08001/home/doAction"
    POST_LOGIN_INIT = "mib-auth-portal/cpo08/cpo08003/home/init"
    TWD_HOME_INIT = "mib-ctw-portal/ctw01/ctw01002/home/init"
    TWD = "mib-ctw-portal/ctw01/ctw01002/home/preQueryTWTransactionDetail"
    SSO = "mib-auth-portal/common/sso/startSSOProcess"
    SSO_RETURN = "mib-auth-portal/common/sso/doSSOLogin"
    LOGOUT = "mib-auth-portal/cpo08/cpo08004/home/logout"

    def __init__(self, client: httpx.Client, *, origin: str) -> None:
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
            raise ValueError("A bare HTTPS origin is required")
        self.client = client
        self.origin = origin.rstrip("/")
        # Same per-page UUID v4 shape as the bank's public SPA
        # window.mibApiService.uuid. This value is client-local, never
        # printed or persisted.
        self._unique_key = str(uuid4())
        self.flow_token = ""
        self._crypto: dict[str, str] | None = None
        self.login_attempted = False
        self.login_accepted = False
        self.session_confirmed = False
        self.twd_task_initialized = False

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        # The bank frontend API client uses a UTC+8 formatted txnTime and
        # carries the last server-provided txnFlowToken into the next POST.
        envelope = {
            "header": {
                "txnTime": datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M:%S"),
                "txnFlowToken": self.flow_token,
            },
            "requestBody": body,
        }
        response = self.client.post(
            f"{self.origin}/esb/{path}",
            json=envelope,
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": self.origin,
                "Referer": f"{self.origin}/esb/",
                "uniqueKey": self._unique_key,
            },
            follow_redirects=False,
        )
        if response.status_code != 200:
            raise HttpProtocolError(
                f"{path}: unexpected HTTP status",
                category="http_status",
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise HttpProtocolError(
                f"{path}: non-JSON response", category="non_json"
            ) from exc
        if not isinstance(data, dict):
            raise HttpProtocolError(
                f"{path}: non-object response", category="non_object"
            )
        token = data.get("txnFlowToken")
        if isinstance(token, str) and token:
            self.flow_token = token
        if data.get("resultCode") != "0000":
            # Never log request bodies, cookies, tokens, or bank response text.
            raise HttpProtocolError(
                f"{path}: request not successful",
                category="bank_result_not_success",
                bank_result_code=data.get("resultCode"),
            )
        return data

    def initialize(self) -> None:
        """Begin a new anonymous session, then fetch ephemeral public keys."""
        response = self.client.get(
            f"{self.origin}/esb/", follow_redirects=False
        )
        if response.status_code != 200:
            raise HttpProtocolError("Anonymous page bootstrap failed")
        data = self._post(self.INIT, {})
        params = (data.get("resultBody") or {}).get("encryptParam")
        if not isinstance(params, dict) or not all(
            isinstance(params.get(key), str)
            for key in ("hsmPublicKey", "timeFactor", "userNamePublicKey")
        ):
            raise HttpProtocolError("Anonymous encryption parameters unavailable")
        self._crypto = params

    def submit_nonforced_login(
        self, *, user_id: str, username: str, password: str
    ) -> None:
        """Send one nonforced request. Success does not confirm a usable session.

        This method is not invoked against the bank by the offline test suite.
        It deliberately does not support force-login or automatic retries.
        """
        if self._crypto is None or self.login_attempted:
            raise HttpProtocolError("Login state invalid or attempt already made")
        payload = offline_login_request_body(
            user_id=user_id,
            username=username,
            password=password,
            time_factor=self._crypto["timeFactor"],
            username_public_pem=self._crypto["userNamePublicKey"],
            hsm_public_pem=self._crypto["hsmPublicKey"],
        )
        # Exactly one attempt per instance, including failure/timeout.
        self.login_attempted = True
        result = self._post(self.LOGIN, payload)
        result_body = result.get("resultBody")
        # Official frontend requires BOTH resultCode SUCCESS and
        # resultBody.valid before transitioning to LOGIN_COMPLETE.
        if not isinstance(result_body, dict) or result_body.get("valid") is not True:
            raise HttpProtocolError("Login response did not confirm a valid session")
        self.login_accepted = True

    def confirm_session(self) -> None:
        if not self.login_accepted:
            raise HttpProtocolError("No accepted login to confirm")
        self._post(self.POST_LOGIN_INIT, {"locale": "zh-TW"})
        self.session_confirmed = True

    def initialize_twd_task(self) -> None:
        """Enter CTW01002 exactly as the public deposit TaskInstance does.

        The deposit microfrontend's task constructor clears the current
        txnFlowToken and calls CTW01002 /home/init with an empty request
        body *before* it mounts the prequery page. An existing authenticated
        session is required. No account or transaction data is requested
        in this initialization step.
        """
        if not self.session_confirmed:
            raise HttpProtocolError("Authenticated session not confirmed")
        if self.twd_task_initialized:
            return
        self.flow_token = ""
        self._post(self.TWD_HOME_INIT, {})
        self.twd_task_initialized = True

    def query_twd(self) -> dict[str, Any]:
        if not self.session_confirmed:
            raise HttpProtocolError("Authenticated session not confirmed")
        self.initialize_twd_task()
        # Publicly served deposit MFE (2026-10-13), module 7187:
        # preQueryTransactionDetail posts {account: pageData.accountNo}.
        # On first navigation to ctw01002-tw-home accountNo is null, NOT
        # an omitted key, unless opening a specific selected account.
        data = self._post(self.TWD, {"account": None})
        body = data.get("resultBody")
        if not isinstance(body, dict) or not isinstance(body.get("twAccountList"), list):
            raise HttpProtocolError(
                "TWD response shape not confirmed",
                category="twd_response_shape",
            )
        detail_query = body.get("queryDeptTxDtlResult")
        if not isinstance(detail_query, dict) or not isinstance(
            detail_query.get("detailListData"), list
        ):
            raise HttpProtocolError(
                "TWD response shape not confirmed",
                category="twd_response_shape",
            )
        return data

    def card_sso_handoff(self, *, purpose: str = "transactions") -> CardSsoHandoff:
        """Obtain a handoff but do not follow or log sensitive redirect token."""
        if not self.session_confirmed:
            raise HttpProtocolError("Authenticated session not confirmed")
        configurations = {
            "transactions": ("IESC-CARDTRANS", "CCM01008"),
            "statements": ("IESC-CARDBILL", "CCM01007"),
        }
        if purpose not in configurations:
            raise HttpProtocolError("Unknown read-only card SSO purpose")
        client_system_id, task_id = configurations[purpose]
        data = self._post(
            self.SSO,
            {"clientSystemId": client_system_id, "taskId": task_id},
        )
        body = data.get("resultBody") or {}
        redirect_url, token = body.get("redirectUrl"), body.get("token")
        if not isinstance(redirect_url, str) or not isinstance(token, str) or not token:
            raise HttpProtocolError("SSO handoff unavailable")
        parsed = urlparse(redirect_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise HttpProtocolError("SSO redirect must be HTTPS")
        # The card app actually lives on iesc.esunbank.com (not .com.tw).
        if parsed.hostname not in {"iesc.esunbank.com", "ebank.esunbank.com.tw"}:
            raise HttpProtocolError("SSO redirect host is outside E.SUN domain")
        return CardSsoHandoff(redirect_url, token)

    def finish_card_sso_return(self, *, session_id: str, token: str) -> str:
        """Model ESB's public SSO callback page without opening a browser.

        This is only called after IESC's public OAuth flow returns a new
        sessionId/token intended for the original banking website. It has
        been tested with synthetic responses ONLY, not real card SSO.
        """
        if not self.session_confirmed or not self.login_accepted:
            raise HttpProtocolError("Bank SSO return requires a confirmed session")
        if not isinstance(session_id, str) or not session_id or not isinstance(token, str) or not token:
            raise HttpProtocolError("Bank SSO return credentials missing")
        data = self._post(
            self.SSO_RETURN, {"sessionId": session_id, "token": token}
        )
        redirect_url = (data.get("resultBody") or {}).get("redirectUrl")
        if not isinstance(redirect_url, str):
            raise HttpProtocolError(
                "Bank SSO return redirect missing", category="sso_return_shape"
            )
        parsed = urlparse(redirect_url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "iesc.esunbank.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path.rstrip("/") != "/IESC/authMib/mibVerify"
            or parsed.fragment
        ):
            raise HttpProtocolError(
                "Bank SSO return redirect not trusted", category="sso_return_host"
            )
        return redirect_url

    def logout(self) -> None:
        if not self.login_accepted:
            return
        try:
            self._post(self.LOGOUT, {})
        finally:
            # Fail closed locally, regardless of the server-side result.
            self.login_accepted = False
            self.session_confirmed = False
            self.twd_task_initialized = False
            self._crypto = None
            self.flow_token = ""
            self.client.cookies.clear()
