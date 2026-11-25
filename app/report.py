"""Báo cáo đặt bàn theo ngày: tổng đơn, tổng khách, theo nguồn, tiệc lớn.

Chạy tay: python -m app.report 2026-12-24   (gửi qua kênh NOTIFY_CHANNEL)
"""
import os
import sys
from collections import Counter
from datetime import date

from app import notify


def daily_report(rows, day: str = None, large: int = 10) -> str:
    day = day or date.today().isoformat()
    today = [r for r in rows if r["time"].startswith(day)]
    guests = sum(int(r["party_size"]) for r in today)
    by_src = Counter(r["source"] for r in today)
    big = [r for r in today if int(r["party_size"]) >= large]
    lines = [f"📊 Đặt bàn {day}: {len(today)} đơn, {guests} khách"]
    if by_src:
        lines.append("Nguồn: " + ", ".join(f"{k} {v}" for k, v in by_src.most_common()))
    for r in big:
        lines.append(f"🎉 Tiệc lớn: {r['name']} {r['party_size']} khách lúc {r['time'][11:]}")
    return "\n".join(lines)


if __name__ == "__main__":
    from app.store import BookingStore
    store = BookingStore(os.getenv("BOOKINGS_CSV", "bookings.csv"))
    print("sent via", notify.send(daily_report(store.rows(), sys.argv[1] if len(sys.argv) > 1 else None)))
