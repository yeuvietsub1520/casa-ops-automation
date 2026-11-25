import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

os.environ["NO_SLEEP"] = "1"
TMP = tempfile.mkdtemp()
os.environ["BOOKINGS_CSV"] = os.path.join(TMP, "b.csv")

from app import notify, server  # noqa: E402
from app.report import daily_report  # noqa: E402
from app.validate import ValidationError, normalize_booking  # noqa: E402

GOOD = {"name": "Anna", "phone": "+84 905 123 456", "party_size": 12,
        "time": "2099-12-24T19:30", "source": "Google", "type": "event"}


class ValidateTest(unittest.TestCase):
    def test_normalize(self):
        b = normalize_booking(GOOD)
        self.assertEqual(b["phone"], "0905123456")
        self.assertEqual(b["source"], "google")

    def test_missing(self):
        with self.assertRaises(ValidationError):
            normalize_booking({"name": "x"})

    def test_past_time(self):
        with self.assertRaises(ValidationError):
            normalize_booking({**GOOD, "time": "2020-01-01T19:00"})

    def test_bad_time(self):
        with self.assertRaises(ValidationError):
            normalize_booking({**GOOD, "time": "tối mai"})


class NotifyTest(unittest.TestCase):
    def test_retry_then_fail(self):
        with mock.patch.dict(os.environ, {"NOTIFY_CHANNEL": "telegram", "TELEGRAM_BOT_TOKEN": "t",
                                          "TELEGRAM_CHAT_ID": "1"}), \
             mock.patch("urllib.request.urlopen", side_effect=OSError("down")) as m:
            with self.assertRaises(RuntimeError):
                notify.send("hi")
            self.assertEqual(m.call_count, 3)


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def post(self, body):
        req = urllib.request.Request(self.base + "/webhook/booking", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_flow(self):
        with mock.patch.object(notify, "send") as sent:
            self.assertEqual(self.post(GOOD)[0], 201)
            self.assertIn("TIỆC RIÊNG", sent.call_args[0][0])
            self.assertIn("ĐOÀN LỚN", sent.call_args[0][0])
            self.assertEqual(self.post(GOOD)[1]["status"], "duplicate")
            self.assertEqual(self.post({"name": "x"})[0], 422)
        with urllib.request.urlopen(self.base + "/booking") as r:
            self.assertIn("Reserve a table", r.read().decode())
        with urllib.request.urlopen(self.base + "/health") as r:
            self.assertTrue(json.loads(r.read())["ok"])


class ReportTest(unittest.TestCase):
    def test_report(self):
        rows = [{"time": "2099-12-24T19:30", "party_size": "12", "source": "google", "name": "A"},
                {"time": "2099-12-24T12:00", "party_size": "2", "source": "zalo", "name": "B"}]
        t = daily_report(rows, "2099-12-24")
        self.assertIn("2 đơn, 14 khách", t)
        self.assertIn("Tiệc lớn: A", t)


if __name__ == "__main__":
    unittest.main()
