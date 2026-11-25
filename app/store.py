"""Lưu đơn đặt bàn vào CSV (nguồn chính), đẩy tiếp sang Google Sheets qua Apps Script.

Sheets lỗi thì đơn vẫn được nhận: đơn được xếp vào hàng chờ sheets_pending.jsonl và gửi lại ở lần sau.
"""
import csv
import json
import logging
import os
import threading
import urllib.request
from datetime import datetime

from app.config import VN_TZ

FIELDS = ["received_at", "type", "name", "phone", "party_size", "time", "source", "note", "lang"]
log = logging.getLogger("store")


class BookingStore:
    def __init__(self, path: str, sheets_url: str = "", sheets_secret: str = ""):
        self.path = path
        self.pending = os.path.splitext(path)[0] + ".sheets_pending.jsonl"
        self.sheets_url = sheets_url
        self.sheets_secret = sheets_secret
        self._lock = threading.Lock()
        self._keys = set()
        for row in self._read():
            if row.get("phone") and row.get("time"):
                self._keys.add(f"{row['phone']}|{row['time']}")

    def _read(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or "phone" not in reader.fieldnames:
                log.warning("file %s sai cấu trúc, bỏ qua dữ liệu cũ", self.path)
                return []
            return list(reader)

    def count(self) -> int:
        return len(self._keys)

    def add_if_new(self, booking: dict, key: str):
        """Kiểm trùng và ghi trong cùng một khóa: 20 đơn giống nhau gửi cùng lúc chỉ ghi 1 dòng.

        Trả về (created, sheets_ok)."""
        row = {"received_at": datetime.now(VN_TZ).isoformat(timespec="seconds"), **booking}
        with self._lock:
            if key in self._keys:
                return False, True
            new = not os.path.exists(self.path)
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if new:
                    w.writeheader()
                w.writerow({k: row.get(k, "") for k in FIELDS})
            self._keys.add(key)
        return True, self._push_sheets(row)

    def _push_sheets(self, row: dict) -> bool:
        if not self.sheets_url:
            return True
        queue = self._take_pending() + [row]
        failed = []
        for item in queue:
            try:
                body = json.dumps({**item, "secret": self.sheets_secret}).encode()
                req = urllib.request.Request(self.sheets_url, data=body,
                                             headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=10).read()
            except Exception as e:
                log.error("đẩy Google Sheets lỗi: %s", e)
                failed.append(item)
        if failed:
            with self._lock, open(self.pending, "a", encoding="utf-8") as f:
                for item in failed:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return row not in failed

    def _take_pending(self):
        with self._lock:
            if not os.path.exists(self.pending):
                return []
            with open(self.pending, encoding="utf-8") as f:
                items = [json.loads(line) for line in f if line.strip()]
            os.remove(self.pending)
            return items

    def rows(self):
        with self._lock:
            return self._read()
