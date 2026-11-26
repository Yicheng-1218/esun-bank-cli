"""Read-only card API client for the HTTP transport.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx


class CardProtocolError(Exception):
    pass


class CardHttp:
    ORIGIN = "https://iesc.esunbank.com"
    SPA_BASE = "/IESC"
    READ_PATHS = {
        "credit": "/GW/creditLastYear/getFilterResult",
        "debit": "/GW/debitLastYear/getFilterResult",
    }
    BILL_PATHS = {
        "latest": "/GW/cardBill/getLastBillYearMonth",
        "detail": "/GW/creditBill/getDetailResult",
        "summary": "/GW/creditBill/getSummaryResult",
    }

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self._bearer: str | None = None
        self._project = "CARDTRANS"
        self.sso_initialized = False
        self.bootstrap_stage = "not_started"

    @classmethod
    def classify_handoff_url(cls, redirect_url: str) -> dict[str, str | bool]:
        """Report fixed labels only: NEVER disclose paths, URLs or query values.

        The bank controls redirectUrl; it may include transient secrets.
        The classification is deliberately coarse and does no HTTP work.
        """
        parts = urlsplit(redirect_url)
        if parts.scheme != "https" or parts.username or parts.password:
            host_kind = "untrusted"
        elif parts.netloc == "iesc.esunbank.com":
            host_kind = "card"
        elif parts.netloc == "ebank.esunbank.com.tw":
            host_kind = "main_bank"
        else:
            host_kind = "untrusted"
        normalized_path = parts.path.rstrip("/")
        # The publicly served IESC bundle uses createWebHistory('/IESC/').
        # Routes in the Vue router are relative to that base path, not root.
        if normalized_path.startswith("/IESC/"):
            normalized_path = normalized_path[len(cls.SPA_BASE):]
        elif normalized_path == cls.SPA_BASE:
            normalized_path = ""
        routes = {
            "/authMib/mibOAuth": "mib_oauth",
            "/authMib/mibVerify": "mib_verify",
            "/cardTrans": "card_trans",
            "": "root",
        }
        route_kind = routes.get(normalized_path, "other")
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        return {
            "host_kind": host_kind,
            "route_kind": route_kind,
            "project_is_cardtrans": params.get("prjcd") == "CARDTRANS",
            "tab_is_card": params.get("tab") in ("credit", "debit"),
            "has_token_parameter": "T" in params,
            "has_session_parameter": "S" in params,
            "has_fragment": bool(parts.fragment),
        }

    @classmethod
    def _sso_entry_url(cls, redirect_url: str, token: str) -> str:
        """Build the official SPA handoff URL without leaking to other hosts."""
        parts = urlsplit(redirect_url)
        if (
            parts.scheme != "https"
            or parts.netloc != "iesc.esunbank.com"
            or parts.username is not None
            or parts.password is not None
            or not token
            or parts.fragment
        ):
            raise CardProtocolError("SSO handoff must target the card site")
        if parts.path.rstrip("/") != cls.SPA_BASE + "/authMib/mibOAuth":
            raise CardProtocolError("SSO handoff did not target MIB OAuth")
        query_params = dict(parse_qsl(parts.query, keep_blank_values=True))
        if query_params.get("prjcd") not in ("CARDTRANS", "CARDBILL") or query_params.get("tab") not in ("credit", "debit"):
            raise CardProtocolError("SSO handoff project or tab was unexpected")
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "T"]
        query.append(("T", token))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))

    def bootstrap_from_handoff(
        self,
        *,
        redirect_url: str,
        token: str,
        bank_sso_return: Callable[[str, str], str] | None = None,
    ) -> None:
        """Recreate the published card SPA OAuth flow.

        Uses the documented IESC OAuth handshake. No browser, no retry,
        no cross-host redirect following. Only call on a fresh session.
        """
        if self.sso_initialized or self._bearer:
            raise CardProtocolError("Card SSO already initialized")
        self.bootstrap_stage = "oauth_entry"
        try:
            self._run_bootstrap(
                redirect_url=redirect_url,
                token=token,
                bank_sso_return=bank_sso_return,
            )
        except Exception:
            self.clear()
            raise

    def _get_card_spa(self, target: str) -> None:
        """GET same-host IESC routes only; never execute JS or follow other hosts."""
        # Allow up to 3 *same-origin GET* redirects. Never let an external
        # Location header carry the SSO token or cookies away.
        for redirect_count in range(4):
            page = self.client.get(target, follow_redirects=False)
            if page.status_code not in (301, 302, 303, 307, 308):
                break
            location = page.headers.get("Location")
            if not location or redirect_count == 3:
                raise CardProtocolError("Card SSO redirect not completed")
            target = urljoin(target, location)
            if not self._same_origin_url(target):
                raise CardProtocolError("Card SSO redirect left the card site")
        if page.status_code != 200:
            raise CardProtocolError("Card SSO handoff did not return the page")

    def _run_bootstrap(
        self,
        *,
        redirect_url: str,
        token: str,
        bank_sso_return: Callable[[str, str], str] | None,
    ) -> None:
        target = self._sso_entry_url(redirect_url, token)
        params = dict(parse_qsl(urlsplit(target).query))
        self._project = params["prjcd"]
        self._get_card_spa(target)

        # Official /authMib/mibOAuth Vue component does not simply route
        # to cardTrans. It exchanges the bank's SSO token for a new token
        # plus sessionId before a second /authMib/mibVerify step.
        self.bootstrap_stage = "mib_oauth"
        oauth = self._bootstrap_api_request(
            "mib/doMibOAuth",
            {"token": token, "prjcd": params["prjcd"], "tab": params["tab"]},
        )
        if oauth.get("rtnCode") != "S":
            raise CardProtocolError("Card MIB OAuth was not approved")
        new_url = oauth.get("url")
        new_token = oauth.get("token")
        session_id = oauth.get("sessionId")
        if not all(isinstance(x, str) and x for x in (new_url, new_token, session_id)):
            raise CardProtocolError("Card MIB OAuth redirect information missing")
        verify_url = urlsplit(new_url)
        if (
            verify_url.scheme == "https"
            and verify_url.netloc == "ebank.esunbank.com.tw"
            and verify_url.path.rstrip("/") == "/esb"
            and not verify_url.fragment
            and verify_url.username is None
            and verify_url.password is None
        ):
            # Public ESB SSO page handles ?S=sessionId&T=token by sending
            # a /common/sso/doSSOLogin JSON POST, which then redirects
            # back to the card site. Reuse the existing authenticated bank
            # HTTP session. Never send S/T to an arbitrary redirect host.
            self.bootstrap_stage = "bank_sso_return"
            if bank_sso_return is None:
                raise CardProtocolError("Card SSO requires bank return handshake")
            next_url = bank_sso_return(session_id, new_token)
        elif self._same_origin_url(new_url):
            # Some official integrations may return directly to the
            # card verification page without the bank callback.
            verification_query = [
                (k, v)
                for k, v in parse_qsl(verify_url.query, keep_blank_values=True)
                if k not in ("T", "S")
            ]
            verification_query.extend([("T", new_token), ("S", session_id)])
            next_url = urlunsplit((
                verify_url.scheme, verify_url.netloc, verify_url.path,
                urlencode(verification_query), ""
            ))
        else:
            raise CardProtocolError("Card MIB OAuth redirect target unrecognized")

        verify_url = urlsplit(next_url)
        if (
            not self._same_origin_url(next_url)
            or verify_url.path.rstrip("/") != self.SPA_BASE + "/authMib/mibVerify"
        ):
            raise CardProtocolError("Card MIB OAuth redirect target unrecognized")
        self.bootstrap_stage = "verify_entry"
        self._get_card_spa(next_url)

        self.bootstrap_stage = "mib_verify"
        verify = self._bootstrap_api_request("mib/doMibVerify", {})
        if (
            verify.get("rtnCode") != "S"
            or verify.get("prjcd") != params["prjcd"]
            or verify.get("tab") != params["tab"]
        ):
            raise CardProtocolError("Card MIB verification not approved")

        self.bootstrap_stage = "card_startup"
        for api, payload in (
            ("common/getSiteCoreContent", {"category": self._project}),
            ("common/isCardholder", {}),
        ):
            self._bootstrap_api_request(api, payload)
        if not self._bearer:
            raise CardProtocolError("Card SSO did not establish a bearer")
        self.sso_initialized = True
        self.bootstrap_stage = "complete"

    def _bootstrap_api_request(self, path: str, body: dict[str, str]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": self.ORIGIN + self.SPA_BASE + (
                "/cardBill" if self._project == "CARDBILL" else "/cardTrans"
            ),
            "Origin": self.ORIGIN,
        }
        if self._bearer:
            headers["Authorization"] = "Bearer " + self._bearer
        response = self.client.post(
            self.ORIGIN + "/GW/" + path,
            json=body,
            headers=headers,
            follow_redirects=False,
        )
        if response.status_code != 200:
            raise CardProtocolError("Card SSO verification did not succeed")
        try:
            content = response.json()
        except ValueError as exc:
            raise CardProtocolError("Card SSO verification did not return JSON") from exc
        if (
            not isinstance(content, dict)
            or content.get("status") != "200"
            or not isinstance(content.get("body"), dict)
        ):
            raise CardProtocolError("Card SSO verification response shape unexpected")
        self.accept_bank_authorization_header(response.headers)
        return content["body"]

    @classmethod
    def _same_origin_url(cls, url: str) -> bool:
        parts = urlsplit(url)
        return (
            parts.scheme == "https"
            and parts.netloc == "iesc.esunbank.com"
            and parts.username is None
            and parts.password is None
            and not parts.fragment
        )

    def accept_bank_authorization_header(self, headers: Mapping[str, str]) -> None:
        """Consume an already-authenticated bank response, without printing it."""
        header = next(
            (v for k, v in headers.items() if k.lower() == "authorization"), None
        )
        if header is None:
            return
        if not header.startswith("Bearer ") or not header[7:].strip():
            raise CardProtocolError("Unrecognized bank authorization header")
        self._bearer = header[7:].strip()

    def fetch(self, source: str, *, cursor: int = 1) -> dict[str, Any]:
        """Fetch one read-only page; never creates or modifies banking records."""
        if source not in self.READ_PATHS:
            raise CardProtocolError("Unsupported card transaction source")
        if self._project != "CARDTRANS":
            raise CardProtocolError("Transaction endpoint requires CARDTRANS SSO")
        if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 1:
            raise CardProtocolError("Cursor must be a positive integer")
        if not self._bearer:
            raise CardProtocolError("Card SSO bearer not established")
        response = self.client.post(
            self.ORIGIN + self.READ_PATHS[source],
            json={"cursor": cursor},
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": "Bearer " + self._bearer,
                "Origin": self.ORIGIN,
                "Referer": self.ORIGIN + self.SPA_BASE + "/cardTrans",
            },
            follow_redirects=False,
        )
        if response.status_code != 200:
            raise CardProtocolError("Card API HTTP status was not successful")
        try:
            payload = response.json()
        except ValueError as exc:
            raise CardProtocolError("Card API did not return JSON") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "200"
            or not isinstance(payload.get("body"), dict)
        ):
            raise CardProtocolError("Card API returned an unexpected body")
        # The publicly served credit/debit last-year UI explicitly treats
        # rtnCode === 'E' as a bank business error and expects cardInfoList
        # and transList arrays before rendering. HTTP 200 and top-level
        # status '200' alone are insufficient proof of a successful query.
        body = payload["body"]
        if body.get("rtnCode") != "S":
            raise CardProtocolError("Card transaction query was not approved")
        if (
            not isinstance(body.get("cardInfoList"), list)
            or not isinstance(body.get("transList"), list)
        ):
            raise CardProtocolError("Card transaction result shape unexpected")
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("transDetailList"), list)
            for item in body["transList"]
        ):
            raise CardProtocolError("Card transaction result shape unexpected")
        # The official frontend supports rotating the bearer in responses.
        self.accept_bank_authorization_header(response.headers)
        return payload

    def fetch_bill(self, kind: str, *, period: str | None = None) -> dict[str, Any]:
        """Only the three observed, read-only card-statement endpoints.

        Requires a separate CARDBILL bearer, but not a new bank login.
        """
        if (kind not in self.BILL_PATHS or self._project != "CARDBILL"
                or not self.sso_initialized or not self._bearer):
            raise CardProtocolError("Statement API not available in this session")
        if kind == "latest":
            data = {"cardType": "C"}
        else:
            if not isinstance(period, str) or len(period) != 6 or not period.isdigit():
                raise CardProtocolError("Statement period must be YYYYMM")
            data = {"billPeriod": period}
        resp = self.client.post(
            self.ORIGIN + self.BILL_PATHS[kind],
            json=data,
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": "Bearer " + self._bearer,
                "Origin": self.ORIGIN,
                "Referer": self.ORIGIN + self.SPA_BASE + "/cardBill",
            },
            follow_redirects=False,
        )
        if resp.status_code != 200:
            raise CardProtocolError("Statement HTTP request failed")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise CardProtocolError("Statement response is not JSON") from exc
        if (not isinstance(payload, dict) or payload.get("status") != "200"
                or not isinstance(payload.get("body"), dict)
                or payload["body"].get("rtnCode") != "S"):
            raise CardProtocolError("Statement API returned an unapproved response")
        body = payload["body"]
        if kind == "latest" and not isinstance(body.get("lastBillYearMonth"), str):
            raise CardProtocolError("Statement latest period missing")
        if kind == "detail" and not isinstance(body.get("transList"), list):
            raise CardProtocolError("Statement details missing")
        if kind == "summary" and not isinstance(body.get("billInfo"), dict):
            raise CardProtocolError("Statement summary missing")
        self.accept_bank_authorization_header(resp.headers)
        return body

    def clear(self) -> None:
        self._bearer = None
        self._project = "CARDTRANS"
        self.sso_initialized = False
