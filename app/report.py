"""Báo cáo theo ngày: khách đến trong ngày (theo giờ đặt) và số đơn mới nhận trong ngày.

Chạy tay: python -m app.report 2026-12-24
"""
import logging
import os
import sys
from collections import Counter
from datetime import datetime

from app import config, notify

log = logging.getLogger("report")


def daily_report(rows, day: str = None, large: int = None) -> str:
    day = day or datetime.now(config.VN_TZ).date().isoformat()
    large = large or config.LARGE_PARTY
    coming, received = [], 0
    for r in rows:
        try:
            size = int(r["party_size"])
            if r["time"].startswith(day):
                coming.append({**r, "party_size": size})
            if str(r.get("received_at", "")).startswith(day):
                received += 1
        except (KeyError, ValueError, TypeError, AttributeError):
            log.warning("bỏ qua dòng hỏng: %s", r)
    guests = sum(r["party_size"] for r in coming)
    by_src = Counter(r.get("source", "other") for r in coming)
    lines = [f"📊 Ngày {day}: {len(coming)} bàn, {guests} khách đến · {received} đơn mới nhận trong ngày"]
    if by_src:
        lines.append("Nguồn: " + ", ".join(f"{k} {v}" for k, v in by_src.most_common()))
    for r in coming:
        if r.get("type") == "event" or r["party_size"] >= large:
            tag = "🥂 Tiệc riêng" if r.get("type") == "event" else "🎉 Đoàn lớn"
            lines.append(f"{tag}: {r['name']} {r['party_size']} khách lúc {r['time'][11:16]}")
    return "\n".join(lines)


if __name__ == "__main__":
    from app.store import BookingStore
    store = BookingStore(os.getenv("BOOKINGS_CSV", "bookings.csv"))
    print("sent via", notify.send(daily_report(store.rows(), sys.argv[1] if len(sys.argv) > 1 else None)))
