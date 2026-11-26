"""Pure-HTTP E.SUN login payload encryption (no network or credential storage).

The bank's public frontend uses RSA PKCS#1 v1.5 for both fields.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def _ascii_bytes(value: str, *, field: str) -> bytes:
    # The browser routines use JS charCodeAt, not a normal UTF-8 encode.
    # Prove ASCII equivalence first, rather than silently corrupt Unicode.
    if not value.isascii():
        raise ValueError(f"{field}: only ASCII has been verified")
    return value.encode("ascii")


def _public_key(public_pem: str) -> rsa.RSAPublicKey:
    key = serialization.load_pem_public_key(public_pem.encode("ascii"))
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("RSA public key required")
    return key


def encrypt_username(username: str, username_public_pem: str) -> str:
    """Replicate the browser's forge encryptStr: PKCS#1 v1.5, HEX output."""
    plain = _ascii_bytes(username, field="username")
    return _public_key(username_public_pem).encrypt(
        plain, padding.PKCS1v15()
    ).hex()


def encrypt_password(password: str, time_factor: str, hsm_public_pem: str) -> str:
    """Replicate encryptPxd: '<password JS length>,<RSA ciphertext Base64>'."""
    plain = _ascii_bytes(password + time_factor, field="password/time_factor")
    encrypted = _public_key(hsm_public_pem).encrypt(plain, padding.PKCS1v15())
    return f"{len(password)},{base64.b64encode(encrypted).decode('ascii')}"


def offline_login_request_body(
    *,
    user_id: str,
    username: str,
    password: str,
    time_factor: str,
    username_public_pem: str,
    hsm_public_pem: str,
) -> dict[str, object]:
    """Create a non-forced payload only. Does NOT submit it anywhere."""
    return {
        "isKeepMe": False,
        "account": encrypt_username(username, username_public_pem),
        "pxssword": encrypt_password(password, time_factor, hsm_public_pem),
        "isForceLogin": False,
        "locale": "zh-TW",
        "customerId": user_id,
    }
