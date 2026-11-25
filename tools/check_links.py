"""Kiểm tra link hỏng trên một website (chỉ đọc, GET công khai).

Chạy: python tools/check_links.py https://www.casamika.com/en/
In ra mọi link nội bộ trả về lỗi 4xx/5xx. Có thể đặt lịch chạy hằng ngày và báo về Telegram/Zalo.
"""
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

UA = {"User-Agent": "Mozilla/5.0 (link-checker)"}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = set()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                self.found.add(href)


def status(url: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def check(start: str):
    host = urlparse(start).netloc
    html = urllib.request.urlopen(urllib.request.Request(start, headers=UA), timeout=15).read().decode("utf-8", "ignore")
    p = Links()
    p.feed(html)
    broken = []
    for href in sorted(p.found):
        url = urljoin(start, href)
        if urlparse(url).netloc != host:
            continue
        code = status(url)
        if code == 0 or code >= 400:
            broken.append((code, url))
    return len(p.found), broken


if __name__ == "__main__":
    total, broken = check(sys.argv[1])
    print(f"Đã kiểm {total} link, hỏng {len(broken)}")
    for code, url in broken:
        print(code, url)
    sys.exit(1 if broken else 0)
