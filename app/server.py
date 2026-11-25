"""Webhook nhận đặt bàn: POST /webhook/booking, GET /health, GET /report.

Chạy: python -m app.server  (cổng mặc định 8080)
"""
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import notify
from app.report import daily_report
from app.store import BookingStore
from app.validate import ValidationError, booking_key, normalize_booking

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format='{"t":"%(asctime)s","lvl":"%(levelname)s","src":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("server")

STORE = BookingStore(os.getenv("BOOKINGS_CSV", "bookings.csv"), os.getenv("SHEETS_WEBHOOK_URL", ""))
SECRET = os.getenv("WEBHOOK_SECRET", "")
LARGE_PARTY = int(os.getenv("LARGE_PARTY", "10"))


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": True, "bookings": len(STORE.rows())})
        if self.path == "/report":
            return self._json(200, {"text": daily_report(STORE.rows())})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/webhook/booking":
            return self._json(404, {"error": "not found"})
        if SECRET and self.headers.get("X-Webhook-Secret") != SECRET:
            return self._json(401, {"error": "sai secret"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            booking = normalize_booking(json.loads(self.rfile.read(length) or b"{}"))
        except json.JSONDecodeError:
            return self._json(400, {"error": "JSON không hợp lệ"})
        except ValidationError as e:
            return self._json(422, {"error": str(e)})

        key = booking_key(booking)
        if STORE.exists(key):
            return self._json(200, {"status": "duplicate", "key": key})
        try:
            STORE.add(booking, key)
        except Exception as e:
            log.error("ghi đơn lỗi: %s", e)
            notify.send(f"⚠️ LỖI ghi đơn đặt bàn {booking['name']} {booking['time']}: {e}")
            return self._json(502, {"error": "lưu thất bại, đã báo quản lý"})

        tag = "🎉 TIỆC LỚN " if booking["party_size"] >= LARGE_PARTY else ""
        try:
            notify.send(f"{tag}Đặt bàn mới: {booking['name']} · {booking['party_size']} khách · "
                        f"{booking['time']} · nguồn {booking['source']} · {booking['phone']}")
        except Exception as e:
            log.error("báo tin lỗi: %s", e)
        self._json(201, {"status": "created", "key": key})


def main():
    port = int(os.getenv("PORT", "8080"))
    log.info("listening on %s", port)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
