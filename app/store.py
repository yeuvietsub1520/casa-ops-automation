"""Lưu đơn đặt bàn vào CSV (nguồn chính), đẩy tiếp sang Google Sheets qua Apps Script.

Sheets lỗi thì đơn vẫn được nhận: đơn vào hàng chờ sheets_pending.jsonl, được đẩy lại khi có đơn mới
và theo chu kỳ 5 phút (server.py). Mỗi đơn gửi kèm "key" để Apps Script bỏ qua nếu đẩy trùng.
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
        self._lock = threading.Lock()          # khóa ghi CSV và chống trùng
        self._flush_lock = threading.Lock()    # chỉ một luồng đẩy Sheets tại một thời điểm
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
        row = {"key": key, "received_at": datetime.now(VN_TZ).isoformat(timespec="seconds"), **booking}
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
        """Đẩy đơn mới và mọi đơn đang chờ. File hàng chờ chỉ được thay (atomic) SAU khi đẩy xong,
        nên máy chủ có tắt giữa chừng thì đơn chờ vẫn còn. Trả về True nếu đơn mới đã lên Sheet."""
        if not self.sheets_url:
            return True
        with self._flush_lock:
            queue = self._read_pending() + ([row] if row else [])
            failed = [item for item in queue if not self._send_one(item)]
            tmp = self.pending + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for item in failed:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            os.replace(tmp, self.pending)
            if not failed:
                os.remove(self.pending)
        return row is None or row not in failed

    def retry_pending(self) -> int:
        """Gọi định kỳ: đẩy lại các đơn đang chờ. Trả về số đơn còn chờ."""
        self._push_sheets(None)
        return len(self._read_pending())

    def _send_one(self, item: dict) -> bool:
        try:
            body = json.dumps({**item, "secret": self.sheets_secret}).encode()
            req = urllib.request.Request(self.sheets_url, data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10).read()
            return True
        except Exception as e:
            log.error("đẩy Google Sheets lỗi: %s", e)
            return False

    def _read_pending(self):
        """Đọc hàng chờ. Dòng hỏng được chuyển sang file .bad để người kiểm tra, không làm hỏng đơn mới."""
        if not os.path.exists(self.pending):
            return []
        items, bad = [], []
        with open(self.pending, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    bad.append(line)
        if bad:
            log.warning("hàng chờ Sheets có %s dòng hỏng, chuyển sang file .bad", len(bad))
            with open(self.pending + ".bad", "a", encoding="utf-8") as f:
                f.writelines(bad)
        return items

    def rows(self):
        with self._lock:
            return self._read()
