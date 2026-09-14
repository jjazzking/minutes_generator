# -*- coding: utf-8 -*-
"""HTML·PDF·UI 출력 경로를 검증한다."""

import json
import re
import threading
import unittest
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from io import BytesIO

from minutes_generator.generator import build_minutes
from minutes_generator.html_render import render_html
from minutes_generator.render import ground_truth

SEEDS = range(1, 61)

try:
    import reportlab  # noqa: F401
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

from minutes_generator import fonts

HAS_FONT = fonts.find_font("gothic") is not None


class HtmlTest(unittest.TestCase):

    def test_renders_and_balances_tags(self):
        for seed in SEEDS:
            html = render_html(build_minutes(seed), seed)
            self.assertTrue(html.startswith("<!doctype html>"), seed)
            for tag in ("article", "table", "dl"):
                opens = len(re.findall(rf"<{tag}[ >]", html))
                closes = html.count(f"</{tag}>")
                self.assertEqual(opens, closes, (seed, tag))

    def test_key_values_present(self):
        for seed in SEEDS:
            m = build_minutes(seed)
            html = render_html(m, seed)
            gt = ground_truth(m)
            self.assertIn(gt["meeting"]["chair"]["name"], html, seed)
            for d in gt["directors"]:
                if d["present"]:
                    self.assertIn(d["name"], html, (seed, d["name"]))

    def test_escapes_ampersand(self):
        """상호에 & 가 들어가는 문서를 찾아 이스케이프 여부를 본다."""
        entity = re.compile(r"&(?!amp;|lt;|gt;|quot;|nbsp;|#x?[0-9A-Fa-f]+;)")
        checked = 0
        for seed in range(1, 401):
            m = build_minutes(seed)
            raw = json.dumps(ground_truth(m), ensure_ascii=False)
            if "&" not in raw:
                continue
            html = render_html(m, seed)
            self.assertIn("&amp;", html, seed)
            body = html.split("<body>", 1)[1]
            self.assertIsNone(entity.search(body), seed)
            checked += 1
            if checked >= 3:
                break
        self.assertGreater(checked, 0, "& 가 들어간 문서를 찾지 못했다")


@unittest.skipUnless(HAS_REPORTLAB and HAS_FONT, "reportlab 또는 한글 글꼴 없음")
class PdfTest(unittest.TestCase):

    def test_produces_valid_pdf(self):
        from minutes_generator.pdf import pdf_bytes
        for seed in (1, 42, 303, 777, 2025):
            blob = pdf_bytes(build_minutes(seed), seed)
            self.assertTrue(blob.startswith(b"%PDF-"), seed)
            self.assertGreater(len(blob), 5000, seed)
            self.assertIn(b"%%EOF", blob[-2048:], seed)

    def test_both_font_families(self):
        from minutes_generator.pdf import pdf_bytes
        for family in ("gothic", "myeongjo"):
            m = build_minutes(11)
            m.style.font_family = family
            self.assertTrue(pdf_bytes(m, 11).startswith(b"%PDF-"), family)


class UiTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from minutes_generator.ui import Handler
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=60) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()

    def test_index_and_status(self):
        code, ctype, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        code, _c, body = self.get("/api/status")
        payload = json.loads(body)
        self.assertEqual(len(payload["kinds"]), 22)
        self.assertIn("ok", payload["pdf"])

    def test_preview_is_reproducible(self):
        _c, _t, first = self.get("/preview?seed=4242")
        _c, _t, second = self.get("/preview?seed=4242")
        self.assertEqual(first, second)
        self.assertIn(b"<article", first)

    def test_agenda_filter_applies(self):
        _c, _t, body = self.get("/preview?seed=9&agenda=borrowing&n_agenda=1")
        self.assertIn("자금 차입의 건".encode("utf-8"), body)

    def test_downloads(self):
        for fmt, sniff in (("txt", b""), ("json", b"{"), ("html", b"<!doctype")):
            code, _t, body = self.get(f"/download?fmt={fmt}&seed=55")
            self.assertEqual(code, 200, fmt)
            self.assertTrue(body.startswith(sniff), fmt)

    @unittest.skipUnless(HAS_REPORTLAB and HAS_FONT, "reportlab 또는 한글 글꼴 없음")
    def test_pdf_download(self):
        code, ctype, body = self.get("/download?fmt=pdf&seed=55")
        self.assertEqual(code, 200)
        self.assertEqual(ctype, "application/pdf")
        self.assertTrue(body.startswith(b"%PDF-"))

    def test_batch_zip(self):
        _c, ctype, body = self.get("/batch?count=3&seed=700&formats=txt,json")
        self.assertEqual(ctype, "application/zip")
        with zipfile.ZipFile(BytesIO(body)) as zf:
            self.assertEqual(len(zf.namelist()), 6)
            payload = json.loads(zf.read("minutes_0002.json"))
            self.assertEqual(payload["seed"], 701)

    def test_unknown_route_is_404(self):
        try:
            self.get("/nope")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)
        else:
            self.fail("404 가 나와야 한다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
