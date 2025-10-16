#!/usr/bin/env python3
import os
import sys
import textwrap
import requests


def truthy(val: str) -> bool:
    return str(val or "").strip().lower() in {"1", "true", "yes", "on"}


def clip(msg: str, limit: int = 1000) -> str:
    if msg is None:
        return ""
    if len(msg) <= limit:
        return msg
    suffix = "…"
    return msg[: max(0, limit - len(suffix))] + suffix


def send_alert():
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    use_broadcast = truthy(os.getenv("USE_BROADCAST", ""))
    to = os.getenv("LINE_TO", "").strip()
    alert = os.getenv("ALERT_MESSAGE", "").strip()
    alert = clip(alert, 1000)

    if not token:
        print("[alert] missing LINE_CHANNEL_ACCESS_TOKEN; skip")
        return 0

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if use_broadcast:
        url = "https://api.line.me/v2/bot/message/broadcast"
        payload = {"messages": [{"type": "text", "text": alert or "(empty)"}]}
    else:
        if not to:
            print("[alert] missing LINE_TO for push; skip")
            return 0
        url = "https://api.line.me/v2/bot/message/push"
        payload = {"to": to, "messages": [{"type": "text", "text": alert or "(empty)"}]}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        body = resp.text[:200] if resp.text else ""
        print(f"[alert] status={resp.status_code} summary={body}")
        # Always exit 0 to avoid masking original failure
        return 0
    except Exception as e:
        print(f"[alert] exception: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(send_alert())

