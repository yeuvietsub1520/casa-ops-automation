"""Kiểm tra và chuẩn hóa dữ liệu đặt bàn (JSON)."""
import re
from datetime import datetime, timedelta

from app import config

SOURCES = {"google", "facebook", "zalo", "website", "phone", "walk-in", "other"}
LANGS = {"vi", "en", "ko", "zh", "ru", "de", "th"}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PHONE_RE = re.compile(r"^\+?\d{8,15}$")   # E.164 tối đa 15 chữ số: đủ cho +86, +82, +7
REQUIRED = ("name", "phone", "party_size", "time")


class ValidationError(ValueError):
    pass


def now_vn() -> datetime:
    """Giờ Việt Nam hiện tại (không kèm múi giờ), đúng dù máy chủ đặt ở đâu."""
    return datetime.now(config.VN_TZ).replace(tzinfo=None)


def normalize_phone(raw) -> str:
    phone = re.sub(r"[\s.\-()]", "", str(raw))
    if phone.startswith("+84"):
        phone = "0" + phone[3:]
    elif phone.startswith("84") and len(phone) == 11:   # 84905123456 → 0905123456
        phone = "0" + phone[2:]
    if not PHONE_RE.match(phone):
        raise ValidationError("số điện thoại không hợp lệ")
    return phone


def parse_party(raw) -> int:
    if isinstance(raw, bool):
        raise ValidationError("party_size phải là số nguyên")
    if isinstance(raw, float):
        if not raw.is_integer():
            raise ValidationError("party_size phải là số nguyên")
        raw = int(raw)
    if isinstance(raw, str):
        if not raw.strip().isdigit():
            raise ValidationError("party_size phải là số nguyên")
        raw = int(raw)
    if not isinstance(raw, int):
        raise ValidationError("party_size phải là số nguyên")
    if not 1 <= raw <= 300:
        raise ValidationError("party_size ngoài khoảng 1-300")
    return raw


def _parse_hours(spec: str):
    """'mon-fri=07:30-24:00;sat-sun=07:30-24:30' → {0: (450, 1440), ...} (phút từ 0h)."""
    out = {}
    for part in filter(None, spec.split(";")):
        days, span = part.split("=")
        a, b = (days.split("-") + [days])[:2]
        start, end = span.split("-")
        mins = [int(h) * 60 + int(m) for h, m in (start.split(":"), end.split(":"))]
        for d in range(DAYS.index(a), DAYS.index(b) + 1):
            out[d] = tuple(mins)
    return out


HOURS = _parse_hours(config.OPEN_HOURS)


def is_open_for_booking(t: datetime) -> bool:
    """Kiểm giờ đặt nằm trong giờ nhận khách, kể cả ca qua nửa đêm của hôm trước."""
    m = t.hour * 60 + t.minute
    last = config.LAST_SEATING_MIN
    today = HOURS.get(t.weekday())
    if today and today[0] <= m <= today[1] - last:
        return True
    prev = HOURS.get((t.weekday() - 1) % 7)
    return bool(prev and prev[1] > 1440 and m + 1440 <= prev[1] - last)


def parse_time(raw) -> datetime:
    s = str(raw)
    if "T" not in s:
        raise ValidationError("time phải có cả ngày và giờ, ví dụ 2026-12-24T19:30")
    try:
        when = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError("time phải theo ISO 8601, ví dụ 2026-12-24T19:30")
    if when.tzinfo:   # có múi giờ thì đổi về giờ Việt Nam
        when = when.astimezone(config.VN_TZ).replace(tzinfo=None)
    now = now_vn()
    if when < now - timedelta(minutes=15):
        raise ValidationError("giờ đặt đã qua")
    if when > now + timedelta(days=config.MAX_DAYS_AHEAD):
        raise ValidationError(f"chỉ nhận đặt trước tối đa {config.MAX_DAYS_AHEAD} ngày")
    if not is_open_for_booking(when):
        raise ValidationError("ngoài giờ nhận khách của quán")
    return when


def normalize_booking(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("body phải là JSON object")
    missing = [k for k in REQUIRED if k not in data or data[k] in (None, "")]
    if missing:
        raise ValidationError("thiếu trường: " + ", ".join(missing))

    name = str(data["name"]).strip()
    note = str(data.get("note", "")).strip()
    if not name or len(name) > 80:
        raise ValidationError("tên phải từ 1 đến 80 ký tự")
    if len(note) > 500:
        raise ValidationError("ghi chú tối đa 500 ký tự")

    source = str(data.get("source", "website")).lower()
    lang = str(data.get("lang", "vi")).lower()
    return {
        "type": "event" if str(data.get("type", "table")).lower() == "event" else "table",
        "name": name,
        "phone": normalize_phone(data["phone"]),
        "party_size": parse_party(data["party_size"]),
        "time": parse_time(data["time"]).isoformat(timespec="minutes"),
        "source": source if source in SOURCES else "other",
        "note": note,
        "lang": lang if lang in LANGS else "other",
    }


def booking_key(b: dict) -> str:
    """Khóa chống trùng: cùng số điện thoại + cùng giờ = một đơn."""
    return f"{b['phone']}|{b['time']}"
