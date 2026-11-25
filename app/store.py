"""Lưu đơn đặt bàn. Mặc định ghi CSV, có thể đẩy tiếp sang Google Sheets qua webhook Apps Script."""
import csv
import json
import os
import threading
import urllib.request
from datetime import datetime

FIELDS = ["received_at", "name", "phone", "party_size", "time", "source", "note", "lang"]
_lock = threading.Lock()


class BookingStore:
    def __init__(self, path: str, sheets_url: str = ""):
        self.path = path
        self.sheets_url = sheets_url
        self._keys = set()
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self._keys.add(f"{row['phone']}|{row['time']}")

    def exists(self, key: str) -> bool:
        return key in self._keys

    def add(self, booking: dict, key: str) -> dict:
        row = {"received_at": datetime.now().isoformat(timespec="seconds"), **booking}
        with _lock:
            new = not os.path.exists(self.path)
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if new:
                    w.writeheader()
                w.writerow({k: row.get(k, "") for k in FIELDS})
            self._keys.add(key)
        if self.sheets_url:
            req = urllib.request.Request(
                self.sheets_url, data=json.dumps(row).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10).read()
        return row

    def rows(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
