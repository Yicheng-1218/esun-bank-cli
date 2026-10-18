# Pure HTTP feasibility probe (2026-10-18)

## Goal and safety boundary

Determine whether the E.SUN v3 Browser API CLI can eventually run without
Playwright / Chromium. All live probes used **anonymous, new HTTP sessions**.
No user credentials, authenticated banking data, HAR, tokens or cookie values
were accessed or persisted; no existing logged-in session was replaced.

## Confirmed from the VPS

1. `GET https://ebank.esunbank.com.tw/esb/` succeeded with HTTP 200 and
   returned a JavaScript-driven page, not an HTML login form. Initial cookies
   were set.
2. The publicly served 2026-10-13 frontend JavaScript identifies the API
   base URL `/esb/`, and an Axios POST envelope:
   `{"header":{"txnTime":"<Taipei local datetime>","txnFlowToken":""},"requestBody":{}}`.
   Its `txnTime` logic adds UTC+08:00 before formatting.
3. An anonymous stdlib-`urllib` POST to
   `/esb/mib-auth-portal/cpo08/cpo08001/home/init` returned HTTP 200,
   JSON `resultCode = "0000"`, and established a `SESSION` cookie.
   `resultBody.encryptParam` included `hsmPublicKey`, `timeFactor`,
   and `userNamePublicKey` (field names only; no values retained).
4. An unauthenticated POST to
   `/esb/mib-ctw-portal/ctw01/ctw01002/home/preQueryTWTransactionDetail`
   returned HTTP 200 with application `resultCode = "0499"`.
   The HTTP status alone therefore does not prove that a banking query worked.
5. The public frontend includes a `cgjsCrypt.CertEncrypt` password
   encryption routine. Its use, token/session propagation, the full login
   request and the card SSO transition **have not** been validated in Python.

## Reproduce the safe portion

```bash
python3 experiments/http_bootstrap_probe.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The standalone probe uses only the Python standard library, opens no browser,
does not load credentials, and prints only status codes, cookie **names**, and
cryptographic parameter **names**.

## Conclusion

**Anonymous initialization works with pure HTTP. Authenticated account queries
and end-to-end login via pure HTTP are not yet proven.** Do not remove
`playwright` / `requirements.txt` from the production CLI based on these
results. In particular, login, authenticated TWD queries, credit/debit card
SSO tokens and cleanup/logout still require separate verification.

A future test should use one explicitly approved, non-forced authentication
attempt, avoid logging personal data, and stop at MFA/CAPTCHA/device
verification instead of bypassing it. Keep the current Browser API CLI as the
working fallback until authenticated parity is demonstrated.

## Follow-up investigation (2026-10-18)

The user explicitly authorized at most one non-forced live authentication
attempt after offline validation, with mandatory stop at MFA, CAPTCHA, device
verification, or an existing-session conflict. **No live authentication
attempt was made.** An attempt to inspect a locally intercepted, synthetic
login submission was blocked by the execution environment's safety checks;
the investigation did not retry through an alternative mechanism.

Additional safe, public-source checks confirmed that the currently served
modern frontend bundle includes the following named API routes and helpers:

- `CPO08001_HOME_INIT` and `CPO08001_HOME_DO_ACTION`
- `CPO08004_LOGOUT`
- `SSO_PROCESS` and `SSO_LOGIN`
- `encryptPxd` and `encryptStr`
- The `/esb/` Axios base URL, `txnFlowToken` request envelope field, and
  the publicly served `cgjsCrypt.CertEncrypt` routine

These are **static frontend references**, not proof that a direct-HTTP
login request has the correct payload, that the cryptographic output is
equivalent, or that card SSO will work without browser state.

### Verified / not verified

| Area | Status |
| --- | --- |
| Anonymous pure HTTP bootstrap and initialization | Verified |
| Public frontend API/encryption identifiers | Verified statically |
| Offline encrypted-credential equivalence | Not verified |
| One authorized real login | Not attempted; safety restriction |
| Authenticated transaction parity | Not verified |
| Logout/session cleanup without browser | Not verified |

**Recommendation:** leave `requirements.txt`, Playwright, and the production
CLI unchanged. Do not promote this experiment into the production login path.
