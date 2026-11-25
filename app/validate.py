"""Kiểm tra và chuẩn hóa dữ liệu đặt bàn nhận từ webhook (JSON)."""
import re
from datetime import datetime

SOURCES = {"google", "facebook", "zalo", "website", "phone", "walk-in"}
PHONE_RE = re.compile(r"^\+?\d{9,12}$")


class ValidationError(ValueError):
    pass


def normalize_booking(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("body phải là JSON object")
    missing = [k for k in ("name", "phone", "party_size", "time") if not data.get(k)]
    if missing:
        raise ValidationError("thiếu trường: " + ", ".join(missing))

    phone = re.sub(r"[\s.\-()]", "", str(data["phone"]))
    if phone.startswith("+84"):
        phone = "0" + phone[3:]
    if not PHONE_RE.match(phone):
        raise ValidationError("số điện thoại không hợp lệ")

    try:
        party = int(data["party_size"])
    except (TypeError, ValueError):
        raise ValidationError("party_size phải là số")
    if not 1 <= party <= 300:
        raise ValidationError("party_size ngoài khoảng 1-300")

    try:
        when = datetime.fromisoformat(str(data["time"]))
    except ValueError:
        raise ValidationError("time phải theo ISO 8601, ví dụ 2026-12-24T19:30")

    source = str(data.get("source", "website")).lower()
    if source not in SOURCES:
        source = "other"

    return {
        "name": str(data["name"]).strip()[:80],
        "phone": phone,
        "party_size": party,
        "time": when.isoformat(timespec="minutes"),
        "source": source,
        "note": str(data.get("note", "")).strip()[:300],
        "lang": str(data.get("lang", "vi"))[:5],
    }


def booking_key(b: dict) -> str:
    """Khóa chống trùng: cùng số điện thoại + cùng giờ = một đơn."""
    return f"{b['phone']}|{b['time']}"
