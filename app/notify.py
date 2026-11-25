"""Gửi tin về Telegram hoặc Zalo OA, có thử lại khi lỗi mạng."""
import json
import logging
import os
import time
import urllib.request

log = logging.getLogger("notify")


def _post(url: str, payload: dict, headers: dict = None, retries: int = 3) -> dict:
    h = {"Content-Type": "application/json", **(headers or {})}
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h, method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read() or b"{}")
        except Exception as e:  # mạng chập chờn: chờ rồi thử lại
            last = e
            log.warning("gửi lỗi lần %s: %s", attempt, e)
            time.sleep(0 if os.getenv("NO_SLEEP") else 2 ** attempt)
    raise RuntimeError(f"gửi thất bại sau {retries} lần: {last}")


def send(text: str) -> str:
    """Kênh chọn theo biến môi trường NOTIFY_CHANNEL=telegram|zalo|log."""
    channel = os.getenv("NOTIFY_CHANNEL", "log")
    if channel == "telegram":
        token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
        _post(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat, "text": text})
    elif channel == "zalo":
        _post("https://openapi.zalo.me/v3.0/oa/message/cs",
              {"recipient": {"user_id": os.environ["ZALO_USER_ID"]}, "message": {"text": text}},
              headers={"access_token": os.environ["ZALO_OA_TOKEN"]})
    else:
        log.info("NOTIFY: %s", text)
    return channel
