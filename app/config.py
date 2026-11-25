"""Cấu hình đọc từ biến môi trường. Giá trị sai thì báo rõ và dùng mặc định, không làm sập server."""
import logging
import os
from datetime import timedelta, timezone

log = logging.getLogger("config")

# Việt Nam không đổi giờ theo mùa nên dùng độ lệch cố định +07:00, không phụ thuộc múi giờ của máy chủ.
VN_TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("biến %s=%r không phải số, dùng mặc định %s", name, raw, default)
        return default


# Giờ mở cửa theo casamika.com (25/11/2026). Đóng sau nửa đêm thì ghi giờ > 24, ví dụ 24:30.
# Định dạng: "mon-fri=07:30-24:00;sat-sun=07:30-24:30". Cần chốt lại với quán trước khi chạy thật.
OPEN_HOURS = os.getenv("OPEN_HOURS", "mon-fri=07:30-24:00;sat-sun=07:30-24:30")
LAST_SEATING_MIN = env_int("LAST_SEATING_MIN", 30)   # nhận khách cuối trước giờ đóng
MAX_DAYS_AHEAD = env_int("MAX_DAYS_AHEAD", 90)
LARGE_PARTY = env_int("LARGE_PARTY", 10)
RATE_LIMIT = env_int("RATE_LIMIT_PER_10MIN", 10)     # số đơn tối đa mỗi IP trong 10 phút ở form công khai
MAX_BODY = 16 * 1024
RATE_LIMIT_PHONE = env_int("RATE_LIMIT_PHONE_PER_HOUR", 5)   # số đơn tối đa mỗi số điện thoại trong 1 giờ
# Đặt TRUST_PROXY=1 khi chạy sau Caddy/Nginx: lấy IP khách từ X-Forwarded-For do proxy của mình thêm vào.
# Không đặt khi chạy trực tiếp, để khách không tự sửa header lách giới hạn.
TRUST_PROXY = os.getenv("TRUST_PROXY", "") == "1"
DATA_DIR = os.path.dirname(os.path.abspath(os.getenv("BOOKINGS_CSV", "bookings.csv")))
