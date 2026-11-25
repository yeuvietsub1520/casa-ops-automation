# casa-ops-automation

Hệ thống đặt bàn cho nhà hàng sân vườn: form đặt bàn 7 ngôn ngữ, kiểm tra dữ liệu, chống trùng, lưu đơn, báo quản lý qua Telegram hoặc Zalo OA, báo cáo mỗi tối, cảnh báo khi workflow lỗi.

Tác giả: Nguyễn Hải Bình, làm cùng Claude Code. Dựng làm bài chứng minh cho vị trí AI Engineer – Triển khai & Vận hành AI Agent tại Casa Mika (Đà Nẵng). Đây là bản mẫu chạy được, chưa gắn vào hệ thống thật của quán.

## Kiến trúc

```
Khách trên web ── form /booking ──► POST /api/booking (công khai, giới hạn 10 đơn/10 phút/IP, bẫy bot)
Zalo / Facebook ─► n8n (webhook có header auth) ─► POST /webhook/booking (bắt buộc X-Webhook-Secret)
                                                        │
                        ops-api (Python, không thư viện ngoài) = nơi DUY NHẤT kiểm, chống trùng, lưu đơn
                                                        │
                    CSV (nguồn chính) ──► Google Sheets qua Apps Script (lỗi thì xếp hàng chờ, đẩy lại sau)
                                                        │
                    Telegram hoặc Zalo OA cho quản lý: 🥂 tiệc riêng, 🎉 đoàn lớn, ⚠️ khi Sheets lỗi
n8n 22h ─► GET /report (có secret) ─► Telegram          n8n lỗi bất kỳ ─► workflow cảnh báo ─► Telegram
```

## Quy tắc kiểm đơn

| Trường | Quy tắc |
|---|---|
| Số điện thoại | `+84…`, `84…`, `0…` đều quy về `0…`. Nhận số quốc tế tới 15 chữ số (Trung +86, Hàn +82, Nga +7) |
| Giờ đặt | ISO 8601, có thể kèm múi giờ. Luôn tính theo giờ Việt Nam dù máy chủ đặt ở đâu. Không nhận giờ đã qua, quá 90 ngày, ngoài giờ nhận khách |
| Giờ nhận khách | `OPEN_HOURS`, mặc định theo casamika.com: T2–T6 07:30–24:00, T7–CN 07:30–00:30, khách cuối trước giờ đóng 30 phút |
| Số khách | Số nguyên 1–300. Không nhận `12.9`, `true` |
| Chống trùng | Cùng số điện thoại + cùng giờ = một đơn, kể cả 30 đơn gửi cùng lúc |

## Thành phần

| File | Nội dung |
|---|---|
| `app/validate.py` | Kiểm và chuẩn hóa đơn, giờ mở cửa, múi giờ |
| `app/store.py` | Kiểm trùng và ghi CSV trong cùng một khóa, đẩy Sheets kèm hàng chờ |
| `app/notify.py` | Telegram, Zalo OA, thử lại 3 lần, gửi nền, che số điện thoại trong log |
| `app/server.py` | Các đường dẫn, secret so sánh an toàn, giới hạn tần suất, giới hạn 16 KB mỗi đơn |
| `app/report.py` | Báo cáo ngày: khách đến, đơn mới nhận, tiệc riêng, đoàn lớn |
| `app/static/booking.html` | Form 7 ngôn ngữ (vi, en, ko, zh, ru, de, th) |
| `n8n/` | 3 workflow: nhận đơn từ kênh khác, cảnh báo lỗi, báo cáo 22h |
| `tools/check_links.py` | Quét link hỏng trên một trang |
| `tests/` | 22 bài kiểm thử |

## Chạy thử trên máy

```bash
python3 -m unittest discover -s tests -v
WEBHOOK_SECRET=thu-nghiem NOTIFY_CHANNEL=log python3 -m app.server
# mở http://localhost:8080/booking?lang=ko
curl -H 'X-Webhook-Secret: thu-nghiem' localhost:8080/report
```

## Triển khai VPS

Xem [docs/HUONG-DAN.md](docs/HUONG-DAN.md). Tóm tắt: `cp .env.example .env`, điền giá trị, `docker compose up -d`, đặt reverse proxy HTTPS, import 3 workflow, tạo credential Telegram và Header Auth trong n8n.

## Kết quả kiểm thật

- 33/33 bài kiểm thử đạt (gồm 6 bài cho lỗi Muse tìm ra ở vòng 2 và 4 bài cho phần đọc tin nhắn bằng LLM).
- Muse (AI agent kiểm thử độc lập) chạy 35 trường hợp khó và soát code ngày 25/11/2026. Các lỗi tìm được (ghi trùng khi gửi cùng lúc, múi giờ, số Trung Quốc, form vỡ với ngôn ngữ lạ, secret mặc định tắt…) đã sửa trong bản này, mỗi lỗi có bài kiểm thử riêng.
- Quét casamika.com/en/ ngày 25/11/2026: 16 link, 1 link hỏng `/en/career/` (404).

## Chưa làm (cần thông tin của quán)

Nối tự động đơn Google Maps Reserve (Google chỉ mở cho đối tác đặt bàn), sơ đồ bàn và sức chứa từng khu, nhắn xác nhận cho khách qua Zalo OA hoặc ZNS, nối POS, đặt cọc tiệc.

## Dữ liệu khách

Đơn nằm ở CSV trên VPS, Google Sheets của quán và tin nhắn gửi quản lý. Log che số điện thoại. `.env`, CSV, log hàng chờ không đưa lên Git. Khi chạy thật cần thông báo mục đích thu thập cho khách theo Nghị định 13/2023/NĐ-CP.

## Đọc tin nhắn đặt bàn bằng LLM

`POST /webhook/parse-message` (cần `X-Webhook-Secret`) với `{"message": "mình là Lan, 6 người 19h30 ngày 24/12, 0905123456"}`
trả về đơn nháp JSON. Có `ANTHROPIC_API_KEY` thì dùng Claude (đọc được nhiều ngôn ngữ), không có thì dùng bộ luật dự phòng.
Kết quả luôn qua cùng luật kiểm tra với form, chỉ là bản nháp để nhân viên xác nhận, không tự ghi đơn.

## Bằng chứng

- `docs/n8n-chay-that-25-11-2026.md`: chạy thật n8n → ops-api → Telegram, báo cáo gửi về Telegram.
- `docs/n8n-import-25-11-2026.md`: nhập 3 workflow vào n8n 2.49.5.
- `docs/llm-chay-that-25-11-2026.md`: chạy thật Claude API với 6 tin nhắn (Việt, Hàn, Anh, Trung, lệnh lạ, thiếu thông tin).
- `docs/kiem-tra-casamika-25-11-2026.md`: số liệu kiểm tra casamika.com bằng curl.
