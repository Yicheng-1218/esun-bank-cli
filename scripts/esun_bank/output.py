"""CLI 輸出與遮罩工具。"""

import json
from typing import Any


def mask_account(account: str) -> str:
    """遮罩帳號或卡號；網站已遮罩的值會保持原樣。"""

    if "X" in account.upper():
        return account
    digit_count = sum(ch.isdigit() for ch in account)
    if digit_count <= 4:
        return account

    visible_from = digit_count - 4
    seen_digits = 0
    masked = []
    for ch in account:
        if not ch.isdigit():
            masked.append(ch)
            continue
        if seen_digits < visible_from:
            masked.append("*")
        else:
            masked.append(ch)
        seen_digits += 1
    return "".join(masked)


def mask_sensitive_accounts(value: Any) -> Any:
    """Recursively mask values under account/card-number-like keys."""

    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if isinstance(item, str) and (
                "account" in key_text
                or "card_number" in key_text
                or "帳號" in str(key)
                or "卡號" in str(key)
            ):
                masked[key] = mask_account(item)
            else:
                masked[key] = mask_sensitive_accounts(item)
        return masked
    if isinstance(value, list):
        return [mask_sensitive_accounts(item) for item in value]
    return value


def write_output(value: Any, output: str) -> None:
    """依指定格式輸出查詢結果。"""

    if output == "json":
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return

    for line in to_text_lines(value):
        print(line)


def to_text_lines(value: Any, prefix: str = "") -> list[str]:
    """將巢狀資料展平成 key-value 文字行。"""

    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(to_text_lines(item, next_prefix))
        return lines
    if isinstance(value, list):
        lines = []
        for index, item in enumerate(value):
            next_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            lines.extend(to_text_lines(item, next_prefix))
        return lines
    return [f"{prefix}: {value}"]
