"""Gửi tin về Telegram hoặc Zalo OA, thử lại khi lỗi mạng. Gửi ở luồng riêng để không làm chậm khách."""
import json
import logging
import os
import re
import threading
import time
import urllib.request

log = logging.getLogger("notify")


def mask_phone(text: str) -> str:
    """Che số điện thoại trước khi ghi log: 0905123456 → 0905***456."""
    return re.sub(r"(\+?\d{3,4})\d{3,8}(\d{3})", r"\1***\2", text)


def _post(url: str, payload: dict, headers: dict = None, retries: int = 3) -> dict:
    h = {"Content-Type": "application/json", **(headers or {})}
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h, method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read() or b"{}")
        except Exception as e:
            last = e
            log.warning("gửi lỗi lần %s: %s", attempt, e)
            time.sleep(0 if os.getenv("NO_SLEEP") else 2 ** attempt)
    raise RuntimeError(f"gửi thất bại sau {retries} lần: {last}")


def send(text: str) -> str:
    """Kênh chọn theo NOTIFY_CHANNEL=telegram|zalo|log."""
    channel = os.getenv("NOTIFY_CHANNEL", "log")
    if channel == "telegram":
        token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
        _post(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat, "text": text})
    elif channel == "zalo":
        _post("https://openapi.zalo.me/v3.0/oa/message/cs",
              {"recipient": {"user_id": os.environ["ZALO_USER_ID"]}, "message": {"text": text}},
              headers={"access_token": os.environ["ZALO_OA_TOKEN"]})
    else:
        channel = "log"
        log.info("NOTIFY: %s", mask_phone(text))
    return channel


def send_async(text: str, failed_path: str = None):
    """Gửi nền. Lỗi sau 3 lần thì ghi vào notify_failed.jsonl cạnh file đơn (số điện thoại đã che;
    số đầy đủ nằm trong CSV), không mất tin im lặng."""
    if failed_path is None:
        from app.config import DATA_DIR
        failed_path = os.path.join(DATA_DIR, "notify_failed.jsonl")

    def run():
        try:
            send(text)
        except Exception as e:
            log.error("báo tin thất bại: %s", e)
            with open(failed_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "text": mask_phone(text), "error": str(e)}, ensure_ascii=False) + "\n")
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t
