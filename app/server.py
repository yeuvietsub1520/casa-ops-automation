"""Máy chủ đặt bàn.

  GET  /booking            form đặt bàn 7 ngôn ngữ (công khai)
  POST /api/booking        form gửi đơn (công khai, giới hạn tần suất theo IP, có bẫy chống bot)
  POST /webhook/booking    kênh khác gửi đơn: n8n, Zalo, Facebook (bắt buộc header X-Webhook-Secret)
  GET  /report?date=...    báo cáo ngày (bắt buộc header X-Webhook-Secret)
  GET  /health             kiểm tra máy chủ còn sống

Chạy: WEBHOOK_SECRET=... python -m app.server
"""
import hmac
import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app import config, notify
from app.llm_parse import parse_message
from app.report import daily_report
from app.store import BookingStore
from app.validate import ValidationError, booking_key, normalize_booking

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format='{"t":"%(asctime)s","lvl":"%(levelname)s","src":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("server")

STORE = BookingStore(os.getenv("BOOKINGS_CSV", "bookings.csv"),
                     os.getenv("SHEETS_WEBHOOK_URL", ""), os.getenv("SHEETS_SECRET", ""))
SECRET = os.getenv("WEBHOOK_SECRET", "")
with open(os.path.join(os.path.dirname(__file__), "static", "booking.html"), "rb") as _f:
    FORM_HTML = _f.read()

_hits = defaultdict(deque)
_hits_lock = threading.Lock()


def _over(key: str, limit: int, window: int) -> bool:
    with _hits_lock:
        now, q = time.time(), _hits[key]
        while q and q[0] < now - window:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(now)
        return False


def rate_limited(ip: str) -> bool:
    return _over("ip:" + ip, config.RATE_LIMIT, 600)


def phone_limited(phone: str) -> bool:
    return _over("tel:" + phone, config.RATE_LIMIT_PHONE, 3600)


def retry_loop(interval: int = 300):
    """Đẩy lại hàng chờ Google Sheets mỗi 5 phút, kể cả khi không có đơn mới."""
    while True:
        time.sleep(interval)
        try:
            left = STORE.retry_pending()
            if left:
                log.warning("còn %s đơn chờ đẩy Google Sheets", left)
        except Exception:
            log.exception("đẩy lại hàng chờ lỗi")


class BadRequest(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, body: dict):
        self._send(code, json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def client_ip(self) -> str:
        if config.TRUST_PROXY:
            fwd = self.headers.get("X-Forwarded-For", "")
            if fwd:
                return fwd.split(",")[-1].strip()   # IP do proxy của mình thêm vào cuối
        return self.client_address[0]

    def _authorized(self) -> bool:
        given = self.headers.get("X-Webhook-Secret", "")
        return bool(SECRET) and hmac.compare_digest(given.encode(), SECRET.encode())

    def _read_json(self):
        if "json" not in self.headers.get("Content-Type", ""):
            raise BadRequest(415, "Content-Type phải là application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise BadRequest(400, "Content-Length không hợp lệ")
        if length > config.MAX_BODY:
            raise BadRequest(413, "dữ liệu quá lớn")
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise BadRequest(400, "JSON không hợp lệ")

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/booking"):
                return self._send(200, FORM_HTML, "text/html; charset=utf-8")
            if url.path == "/health":
                return self._json(200, {"ok": True})
            if url.path == "/report":
                if not self._authorized():
                    return self._json(401, {"error": "cần X-Webhook-Secret"})
                day = parse_qs(url.query).get("date", [None])[0]
                return self._json(200, {"text": daily_report(STORE.rows(), day)})
            self._json(404, {"error": "not found"})
        except Exception:
            log.exception("lỗi GET")
            self._json(500, {"error": "lỗi máy chủ"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/webhook/parse-message":
            if not SECRET:
                return self._json(503, {"error": "máy chủ chưa đặt WEBHOOK_SECRET"})
            if not self._authorized():
                return self._json(401, {"error": "sai secret"})
            try:
                data = self._read_json()
                if not isinstance(data, dict):
                    raise ValidationError("cần object JSON")
                return self._json(200, parse_message(data.get("message"), data.get("source", "other")))
            except BadRequest as e:
                return self._json(e.code, {"error": str(e)})
            except ValidationError as e:
                return self._json(422, {"error": str(e)})
        try:
            if path == "/webhook/booking":
                if not SECRET:
                    return self._json(503, {"error": "máy chủ chưa đặt WEBHOOK_SECRET"})
                if not self._authorized():
                    return self._json(401, {"error": "sai secret"})
            elif path == "/api/booking":
                if rate_limited(self.client_ip()):
                    return self._json(429, {"error": "gửi quá nhiều, vui lòng gọi điện cho quán"})
            else:
                return self._json(404, {"error": "not found"})

            data = self._read_json()
            if path == "/api/booking" and isinstance(data, dict) and data.pop("website", ""):
                return self._json(201, {"status": "created"})   # bẫy bot: ô ẩn có chữ thì bỏ qua đơn
            booking = normalize_booking(data)
            if path == "/api/booking" and phone_limited(booking["phone"]):
                return self._json(429, {"error": "số điện thoại này đã gửi nhiều đơn, vui lòng gọi điện cho quán"})
        except BadRequest as e:
            return self._json(e.code, {"error": str(e)})
        except ValidationError as e:
            return self._json(422, {"error": str(e)})
        except Exception:
            log.exception("lỗi đọc đơn")
            return self._json(500, {"error": "lỗi máy chủ"})

        key = booking_key(booking)
        try:
            created, sheets_ok = STORE.add_if_new(booking, key)
        except Exception:
            log.exception("ghi đơn lỗi")
            notify.send_async(f"⚠️ LỖI ghi đơn {booking['name']} {booking['time']}, gọi lại khách {booking['phone']}")
            return self._json(500, {"error": "chưa lưu được, vui lòng gọi điện cho quán"})
        if not created:
            return self._json(200, {"status": "duplicate", "key": key})

        tag = "🥂 TIỆC RIÊNG " if booking["type"] == "event" else ""
        if booking["party_size"] >= config.LARGE_PARTY:
            tag += "🎉 ĐOÀN LỚN "
        text = (f"{tag}Đặt bàn mới: {booking['name']} · {booking['party_size']} khách · {booking['time']} · "
                f"nguồn {booking['source']} · {booking['lang']} · {booking['phone']}"
                + (f" · ghi chú: {booking['note']}" if booking["note"] else ""))
        if not sheets_ok:
            text += "\n⚠️ Google Sheets đang lỗi, đơn đã lưu và sẽ đẩy lại."
        notify.send_async(text)
        self._json(201, {"status": "created", "key": key})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128   # mặc định 5: nhiều khách gửi cùng lúc sẽ bị rớt kết nối


def main():
    port = config.env_int("PORT", 8080)
    if not SECRET:
        log.warning("chưa đặt WEBHOOK_SECRET: /webhook/booking và /report sẽ từ chối mọi yêu cầu")
    threading.Thread(target=retry_loop, daemon=True).start()
    log.info("listening on %s", port)
    Server(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
