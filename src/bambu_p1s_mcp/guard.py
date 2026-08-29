from __future__ import annotations


def require_confirm(confirm: bool, action: str) -> str | None:
    if confirm:
        return None
    return (
        f"Refused: {action} is a write. Call again with confirm=true after you have "
        "checked printer_status (idle vs printing, current job)."
    )
