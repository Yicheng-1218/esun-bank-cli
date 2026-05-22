"""CLI 輸出與遮罩工具。"""

import json
from typing import Any


def mask_account(account: str) -> str:
    """遮罩帳號或卡號；網站已遮罩的值會保持原樣。"""

    if "X" in account.upper():
        return account
    digits = "".join(ch for ch in account if ch.isdigit())
    if len(digits) <= 4:
        return account
    return "*" * (len(digits) - 4) + digits[-4:]


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
