"""Kiểm thử. Giờ "hiện tại" được cố định ở 01/12/2026 10:00 giờ Việt Nam (thứ Ba) để kết quả không phụ thuộc ngày chạy."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from unittest import mock

os.environ["NO_SLEEP"] = "1"
os.environ["NOTIFY_CHANNEL"] = "log"
os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["RATE_LIMIT_PER_10MIN"] = "1000"
TMP = tempfile.mkdtemp()
os.environ["BOOKINGS_CSV"] = os.path.join(TMP, "b.csv")

from app import notify, server, validate  # noqa: E402
from app.report import daily_report  # noqa: E402
from app.store import BookingStore  # noqa: E402
from app.validate import ValidationError, normalize_booking  # noqa: E402

NOW = datetime(2026, 12, 1, 10, 0)
GOOD = {"name": "Anna", "phone": "+84 905 123 456", "party_size": 12,
        "time": "2026-12-24T19:30", "source": "Google", "type": "event"}


def setUpModule():
    p = mock.patch.object(validate, "now_vn", return_value=NOW)
    p.start()
    unittest.addModuleCleanup(p.stop)


class ValidateTest(unittest.TestCase):
    def ok(self, **kw):
        return normalize_booking({**GOOD, **kw})

    def bad(self, **kw):
        with self.assertRaises(ValidationError):
            normalize_booking({**GOOD, **kw})

    def test_normalize(self):
        b = self.ok()
        self.assertEqual((b["phone"], b["source"], b["type"]), ("0905123456", "google", "event"))

    def test_phone_formats(self):
        self.assertEqual(self.ok(phone="84905123456")["phone"], "0905123456")   # cùng số với +84
        self.assertEqual(self.ok(phone="+8613800138000")["phone"], "+8613800138000")   # Trung Quốc
        self.assertEqual(self.ok(phone="+821012345678")["phone"], "+821012345678")     # Hàn
        self.bad(phone="abc")
        self.bad(phone="+84")

    def test_missing_and_zero(self):
        with self.assertRaisesRegex(ValidationError, "thiếu trường"):
            normalize_booking({"name": "x"})
        with self.assertRaisesRegex(ValidationError, "ngoài khoảng"):
            self.ok(party_size=0)

    def test_party_size_types(self):
        self.assertEqual(self.ok(party_size="4")["party_size"], 4)
        self.assertEqual(self.ok(party_size=4.0)["party_size"], 4)
        for v in (12.9, True, "abc", -1, 301):
            self.bad(party_size=v)

    def test_time_rules(self):
        self.bad(time="tối mai")
        self.bad(time="2026-12-24")                  # thiếu giờ
        self.bad(time="2026-11-30T19:00")            # đã qua
        self.bad(time="2027-06-01T19:00")            # quá 90 ngày
        self.bad(time="2026-12-24T03:00")            # 3h sáng, quán đóng

    def test_opening_hours(self):
        self.ok(time="2026-12-02T07:30")             # thứ Tư mở 07:30
        self.ok(time="2026-12-02T23:30")             # nhận khách cuối 23:30 (đóng 24:00)
        self.bad(time="2026-12-02T23:45")
        self.ok(time="2026-12-06T00:00")             # đêm thứ Bảy sang Chủ nhật, đóng 00:30
        self.bad(time="2026-12-02T00:00")            # đêm thứ Ba sang thứ Tư, đã đóng

    def test_timezone_aware(self):
        b = self.ok(time="2026-12-24T12:30Z")        # 12:30 UTC = 19:30 Việt Nam
        self.assertEqual(b["time"], "2026-12-24T19:30")

    def test_lang_and_length(self):
        self.assertEqual(self.ok(lang="xx")["lang"], "other")
        self.assertEqual(self.ok(lang="de")["lang"], "de")
        self.bad(name="x" * 81)
        self.bad(note="x" * 501)


class NotifyTest(unittest.TestCase):
    def test_retry_then_fail(self):
        with mock.patch.dict(os.environ, {"NOTIFY_CHANNEL": "telegram", "TELEGRAM_BOT_TOKEN": "t",
                                          "TELEGRAM_CHAT_ID": "1"}), \
             mock.patch("urllib.request.urlopen", side_effect=OSError("down")) as m:
            with self.assertRaises(RuntimeError):
                notify.send("hi")
            self.assertEqual(m.call_count, 3)

    def test_mask_phone_in_log(self):
        self.assertEqual(notify.mask_phone("gọi 0905123456"), "gọi 0905***456")


class StoreTest(unittest.TestCase):
    def test_concurrent_duplicates_write_once(self):
        store = BookingStore(os.path.join(TMP, "race.csv"))
        b = normalize_booking(GOOD)
        results = []
        ts = [threading.Thread(target=lambda: results.append(store.add_if_new(b, "k")[0])) for _ in range(30)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(results.count(True), 1)
        self.assertEqual(len(store.rows()), 1)

    def test_sheets_failure_keeps_booking_and_queues(self):
        store = BookingStore(os.path.join(TMP, "sheet.csv"), sheets_url="http://127.0.0.1:9/x")
        created, sheets_ok = store.add_if_new(normalize_booking(GOOD), "k1")
        self.assertTrue(created)
        self.assertFalse(sheets_ok)
        self.assertTrue(os.path.exists(store.pending))

    def test_bad_csv_does_not_crash(self):
        p = os.path.join(TMP, "bad.csv")
        open(p, "w").write("foo,bar\n1,2\n")
        self.assertEqual(BookingStore(p).count(), 0)


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, path, body=None, headers=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Content-Type": "application/json", **(headers or {})}
        r = urllib.request.Request(self.base + path, data=data, headers=h, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_public_form_flow(self):
        body = {**GOOD, "phone": "0905000111"}
        with mock.patch.object(notify, "send_async") as sent:
            self.assertEqual(self.req("/api/booking", body)[0], 201)
            self.assertIn("TIỆC RIÊNG", sent.call_args[0][0])
            self.assertIn("ĐOÀN LỚN", sent.call_args[0][0])
            self.assertEqual(self.req("/api/booking", body)[1]["status"], "duplicate")
            self.assertEqual(self.req("/api/booking", {"name": "x"})[0], 422)

    def test_honeypot(self):
        with mock.patch.object(notify, "send_async") as sent:
            code, _ = self.req("/api/booking", {**GOOD, "phone": "0905000222", "website": "spam"})
            self.assertEqual(code, 201)
            sent.assert_not_called()

    def test_webhook_requires_secret(self):
        body = {**GOOD, "phone": "0905000333"}
        self.assertEqual(self.req("/webhook/booking", body)[0], 401)
        self.assertEqual(self.req("/webhook/booking", body, {"X-Webhook-Secret": "sai"})[0], 401)
        with mock.patch.object(notify, "send_async"):
            self.assertEqual(self.req("/webhook/booking", body, {"X-Webhook-Secret": "test-secret"})[0], 201)

    def test_bad_requests_get_answers(self):
        self.assertEqual(self.req("/api/booking", raw=b"{bad")[0], 400)
        self.assertEqual(self.req("/api/booking", raw=b"x" * 20000)[0], 413)
        self.assertEqual(self.req("/api/booking", GOOD, {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.req("/api/booking", {**GOOD, "time": "2026-12-24T19:30+07:00",
                                                   "phone": "0905000444"})[0] in (201, 200), True)

    def test_50_parallel_requests_all_answered(self):
        body = {**GOOD, "phone": "0905000555"}
        codes = []
        with mock.patch.object(notify, "send_async"):
            ts = [threading.Thread(target=lambda: codes.append(
                self.req("/webhook/booking", body, {"X-Webhook-Secret": "test-secret"})[0])) for _ in range(50)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(len(codes), 50)
        self.assertEqual(codes.count(201), 1)
        self.assertEqual(codes.count(200), 49)

    def test_report_and_health(self):
        self.assertEqual(self.req("/report")[0], 401)
        code, body = self.req("/report?date=2026-12-24", headers={"X-Webhook-Secret": "test-secret"})
        self.assertEqual(code, 200)
        self.assertIn("2026-12-24", body["text"])
        self.assertEqual(self.req("/health?x=1"), (200, {"ok": True}))

    def test_form_has_7_languages(self):
        with urllib.request.urlopen(self.base + "/booking?lang=de") as r:
            html = r.read().decode()
        for code in ("vi:", "en:", "ko:", "zh:", "ru:", "de:", "th:"):
            self.assertIn(code, html)
        self.assertIn('if(!T[L])L="vi"', html)


class RateLimitTest(unittest.TestCase):
    def test_limit(self):
        with mock.patch.object(server.config, "RATE_LIMIT", 3):
            self.assertEqual([server.rate_limited("1.2.3.4") for _ in range(4)], [False, False, False, True])


class ReportTest(unittest.TestCase):
    def test_report(self):
        rows = [{"time": "2026-12-24T19:30", "party_size": "12", "source": "google", "name": "A", "type": "table",
                 "received_at": "2026-12-24T09:00:00+07:00"},
                {"time": "2026-12-24T12:00", "party_size": "6", "source": "zalo", "name": "B", "type": "event",
                 "received_at": "2026-12-20T09:00:00+07:00"},
                {"time": "2026-12-24T12:00", "party_size": "abc"}]          # dòng hỏng bị bỏ qua
        t = daily_report(rows, "2026-12-24")
        self.assertIn("2 bàn, 18 khách đến · 1 đơn mới nhận", t)
        self.assertIn("🎉 Đoàn lớn: A", t)
        self.assertIn("🥂 Tiệc riêng: B", t)


if __name__ == "__main__":
    unittest.main()
