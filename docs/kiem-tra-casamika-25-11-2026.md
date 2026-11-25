# Kiểm tra website casamika.com (25/11/2026)

Kiểm tra từ bên ngoài bằng `curl`, không đăng nhập, không gửi form. Ai cũng chạy lại được bằng các lệnh dưới.

| Kiểm tra | Lệnh | Kết quả |
|---|---|---|
| File menu PDF | `curl -sI https://www.casamika.com/menu/casa-mika-menu-au.pdf` | 200, `content-length: 93605900` (khoảng 93,6MB) |
| Video trang chủ 1 | `curl -sI https://www.casamika.com/assets/video-highlight-1-D1dR3Jey.mp4` | `content-length: 57981080` (khoảng 58MB) |
| Video trang chủ 2 | `curl -sI https://www.casamika.com/assets/video-highlight-2-CQKr7FbD.mp4` | `content-length: 89482821` (khoảng 89,5MB) |
| Trang tuyển dụng tiếng Việt | `curl -sL -o /dev/null -w '%{http_code}' https://www.casamika.com/vi/career/` | 200 |
| Trang tuyển dụng 6 ngôn ngữ khác | thay `vi` bằng `en ko de zh th ru` | cả 6 trả 404 |
| Trang có trong sitemap | `curl -s https://www.casamika.com/sitemap.xml` | 30 URL, có `/doi-tac.html` |
| `/doi-tac.html` | `curl -s -o /dev/null -w '%{http_code}' https://www.casamika.com/doi-tac.html` | 404 (sitemap trỏ tới trang không tồn tại) |
| `llms.txt` cho công cụ AI | `curl -s -o /dev/null -w '%{http_code}' https://www.casamika.com/llms.txt` | 404 |

## Ý nghĩa với quán

- Khách mở trang trên điện thoại phải tải khoảng 147MB video và 93,6MB nếu mở menu, nên trang chậm và tốn dữ liệu di động của khách du lịch.
- Khách nước ngoài bấm "Career" ở bản tiếng Anh, Hàn, Đức, Trung, Thái, Nga đều gặp trang lỗi.
- Sitemap trỏ tới trang 404 khiến Google tốn lượt quét vào trang lỗi.

Cách sửa đề xuất: nén video và menu (hoặc tách menu theo trang), sửa hoặc ẩn link Career ở 6 ngôn ngữ, bỏ `/doi-tac.html` khỏi sitemap, thêm `llms.txt`. `tools/check_links.py` trong repo dùng để kiểm lại sau khi sửa.
