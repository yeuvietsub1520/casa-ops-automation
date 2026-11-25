# casa-ops-automation

Hệ thống tự động hóa vận hành cho nhà hàng sân vườn: nhận đặt bàn qua webhook, kiểm tra dữ liệu JSON, ghi Google Sheet, báo Telegram hoặc Zalo OA, cảnh báo khi workflow lỗi, báo cáo đặt bàn mỗi tối, kiểm tra link hỏng trên website.

Tác giả: Nguyễn Hải Bình, làm cùng Claude Code. Dựng làm bài chứng minh cho vị trí AI Engineer – Triển khai & Vận hành AI Agent.

## Kiến trúc

```
Google Reserve / Facebook / Zalo / Website
            │  (JSON qua webhook)
            ▼
   n8n: 1-dat-ban.json ──► Kiểm tra JSON ──► Google Sheet "DatBan"
            │                      │               │
            │                 422 + lý do          ├─► Telegram (tiệc ≥10 khách gắn 🎉)
            │                                      └─► Zalo OA
   n8n: 2-canh-bao-loi.json  ◄── mọi workflow lỗi ──► Telegram
   n8n: 3-bao-cao-hang-ngay.json ── 22h ──► ops-api /report ──► Telegram

   ops-api (Python, không thư viện ngoài): /webhook/booking · /report · /health
```

## Thành phần

| Thư mục | Nội dung |
|---|---|
| `app/validate.py` | Kiểm tra, chuẩn hóa đơn (sđt +84, giờ ISO 8601, số khách), khóa chống trùng |
| `app/store.py` | Ghi CSV, tùy chọn đẩy Google Sheets qua Apps Script webhook |
| `app/notify.py` | Gửi Telegram Bot API hoặc Zalo OA API, thử lại 3 lần |
| `app/server.py` | Webhook HTTP, secret header, log JSON, báo lỗi về quản lý khi ghi thất bại |
| `app/report.py` | Báo cáo theo ngày: số đơn, số khách, theo nguồn, tiệc lớn |
| `tools/check_links.py` | Quét link hỏng trên website (đặt lịch chạy hằng ngày) |
| `n8n/` | 3 workflow import được vào n8n |
| `tests/` | Kiểm thử đơn vị và tích hợp |

## Chạy thử trên máy

```bash
python3 -m unittest discover -s tests -v
NOTIFY_CHANNEL=log python3 -m app.server
curl -X POST localhost:8080/webhook/booking -H 'Content-Type: application/json' \
  -d '{"name":"Anna","phone":"+84905123456","party_size":12,"time":"2026-12-24T19:30","source":"google"}'
curl localhost:8080/report
python3 tools/check_links.py https://example.com/
```

## Triển khai VPS (Linux)

```bash
cp .env.example .env    # điền token Telegram / Zalo, SHEET_ID
docker compose up -d    # ops-api :8080, n8n :5678
docker compose exec n8n n8n import:workflow --separate --input=/workflows
```

## Kết quả đo thật

- 7/7 bài kiểm thử đạt (chuẩn hóa, thiếu trường, giờ sai, giờ đã qua, thử lại khi mạng lỗi, luồng webhook 201/duplicate/422, form đặt bàn, báo cáo).
- Form đặt bàn 5 ngôn ngữ tại `/booking`, có loại tiệc riêng. Hướng dẫn đầy đủ kèm ảnh: [docs/HUONG-DAN.md](docs/HUONG-DAN.md).
- Quét casamika.com/en/ ngày 25/11/2026: 16 link, phát hiện 1 link hỏng `/en/career/` trả 404.

## Bảo mật

Không lưu token trong code (`.env` bị bỏ qua khỏi Git). Webhook có thể bật `WEBHOOK_SECRET`. Dữ liệu khách chỉ ghi vào Sheet của nhà hàng.
