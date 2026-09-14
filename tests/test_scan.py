# -*- coding: utf-8 -*-
"""인영 이미지와 스캔 열화 파이프라인을 검증한다."""

import io
import random
import unittest

from minutes_generator.generator import build_minutes, force_seals
from minutes_generator.render import ground_truth

try:
    from PIL import Image  # noqa: F401
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import reportlab  # noqa: F401
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

from minutes_generator import fonts

HAS_FONT = fonts.find_font("gothic") is not None


def _has_rasterizer() -> bool:
    for mod in ("pypdfium2", "fitz"):
        try:
            __import__(mod)
            return True
        except ImportError:
            continue
    return False


HAS_RASTER = _has_rasterizer()


class SealAssignmentTest(unittest.TestCase):
    """인영은 Pillow 없이도 결정되고 정답셋에 실린다."""

    def test_seal_is_consistent_with_style(self):
        for seed in range(1, 121):
            m = build_minutes(seed)
            gt = ground_truth(m)
            enabled = gt["seals"]["enabled"]
            for signer, row in zip(m.signers, gt["signers"]):
                self.assertEqual(signer.seal is not None, enabled, seed)
                if enabled:
                    self.assertEqual(row["seal"]["text"], signer.seal.text, seed)
                    self.assertIn(row["seal"]["shape"], ("circle", "square", "rounded"))
            if enabled:
                self.assertNotEqual(m.style.seal_mark, "(서명)", seed)

    def test_seal_text_mentions_the_person(self):
        for seed in range(1, 121):
            m = build_minutes(seed)
            for officer in m.signers:
                if officer.seal and officer.seal.kind == "성명인":
                    self.assertIn(officer.name, officer.seal.text, (seed, officer.name))

    def test_force_seals_toggles(self):
        for seed in range(1, 41):
            m = build_minutes(seed)
            force_seals(m, True, seed)
            self.assertTrue(m.style.seal_images, seed)
            self.assertTrue(all(o.seal for o in m.signers), seed)
            force_seals(m, False, seed)
            self.assertFalse(m.style.seal_images, seed)
            self.assertTrue(all(o.seal is None for o in m.signers), seed)

    def test_seal_survives_reproduction(self):
        a, b = build_minutes(4242), build_minutes(4242)
        self.assertEqual([o.seal for o in a.signers], [o.seal for o in b.signers])


@unittest.skipUnless(HAS_PIL and HAS_FONT, "Pillow 또는 한글 글꼴 없음")
class SealImageTest(unittest.TestCase):

    def test_draws_visible_ink(self):
        from minutes_generator.seal import make_seal

        rng = random.Random(1)
        for shape in ("circle", "square", "rounded"):
            img = make_seal("김철수印", rng, size=200, shape=shape)
            self.assertEqual(img.mode, "RGBA")
            alpha = img.getchannel("A")
            inked = sum(1 for v in alpha.getdata() if v > 40)
            self.assertGreater(inked, 400, shape)
            self.assertLess(inked, alpha.width * alpha.height * 0.6, shape)

    def test_no_missing_glyph_boxes(self):
        """글꼴에 없는 글자를 새기지 않는지 본다."""
        from minutes_generator.seal import hanja_available, seal_text

        rng = random.Random(9)
        hanja = hanja_available()
        for _ in range(50):
            text, _kind = seal_text("김철수", "대표이사", rng, hanja)
            if not hanja:
                self.assertTrue(all(ch < "　" or "가" <= ch <= "힣" for ch in text), text)

    def test_stamp_renders(self):
        from minutes_generator.seal import make_stamp

        img = make_stamp("원본대조필", random.Random(2))
        self.assertEqual(img.mode, "RGBA")
        self.assertGreater(img.width, 100)


@unittest.skipUnless(HAS_PIL, "Pillow 없음")
class DegradationTest(unittest.TestCase):
    """열화 연산 자체는 PDF 없이도 확인할 수 있다."""

    def _page(self):
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (420, 594), "white")
        draw = ImageDraw.Draw(img)
        for y in range(40, 560, 26):
            draw.rectangle([40, y, 380, y + 8], fill=(30, 30, 30))
        return img

    def test_every_profile_runs(self):
        from minutes_generator import scan

        page = self._page()
        for profile in scan.PROFILES:
            rng = random.Random(5)
            params = scan.sample_params(profile, rng)
            out = scan.apply(page, params, rng)
            self.assertEqual(out.mode, "RGB", profile)
            self.assertGreaterEqual(out.width, page.width - 4, profile)
            self.assertEqual(params["profile"], profile)

    def test_random_profile_is_never_clean(self):
        from minutes_generator import scan

        picks = {scan.sample_params("random", random.Random(i))["profile"]
                 for i in range(60)}
        self.assertNotIn("clean", picks)
        self.assertGreater(len(picks), 3)

    def test_unknown_profile_rejected(self):
        from minutes_generator import scan

        with self.assertRaises(ValueError):
            scan.sample_params("nope", random.Random(1))

    def test_same_seed_same_image(self):
        from minutes_generator import scan

        page = self._page()
        outs = []
        for _ in range(2):
            rng = random.Random(77)
            params = scan.sample_params("photocopy", rng)
            outs.append(scan.apply(page, params, rng).tobytes())
        self.assertEqual(outs[0], outs[1])

    def test_degradation_actually_changes_pixels(self):
        from minutes_generator import scan

        page = self._page()
        for profile in ("office_scan", "mobile_photo", "fax", "aged"):
            rng = random.Random(3)
            params = scan.sample_params(profile, rng)
            out = scan.apply(page, params, rng)
            self.assertNotEqual(out.tobytes(), page.tobytes(), profile)

    def test_perspective_solver(self):
        from minutes_generator.scan import _solve

        matrix = [[2.0, 1.0], [1.0, 3.0]]
        answer = _solve(matrix, [5.0, 10.0])
        self.assertAlmostEqual(answer[0], 1.0, places=6)
        self.assertAlmostEqual(answer[1], 3.0, places=6)


@unittest.skipUnless(HAS_PIL and HAS_REPORTLAB and HAS_FONT and HAS_RASTER,
                     "Pillow, reportlab, 글꼴, 래스터라이저 중 없는 것이 있음")
class ScanPipelineTest(unittest.TestCase):

    def test_scan_produces_one_image_per_page(self):
        from minutes_generator import scan
        from minutes_generator.pdf import pdf_bytes

        minutes = build_minutes(42)
        data = pdf_bytes(minutes, 42)
        clean = scan.rasterize(data, 72)
        pages, params = scan.scan(data, "low_dpi", random.Random(1), dpi=72)
        self.assertEqual(len(pages), len(clean))
        self.assertEqual(params["dpi"], 72)

    def test_images_to_pdf_round_trip(self):
        from minutes_generator import scan
        from minutes_generator.pdf import pdf_bytes

        pages, _params = scan.scan(pdf_bytes(build_minutes(7), 7), "fax",
                                   random.Random(2), dpi=72)
        buf = io.BytesIO()
        scan.images_to_pdf(pages, buf)
        blob = buf.getvalue()
        self.assertTrue(blob.startswith(b"%PDF-"))
        self.assertEqual(len(scan.rasterize(blob, 40)), len(pages))

    def test_dpi_override_changes_size(self):
        from minutes_generator import scan
        from minutes_generator.pdf import pdf_bytes

        data = pdf_bytes(build_minutes(11), 11)
        small, _ = scan.scan(data, "clean", random.Random(1), dpi=60)
        large, _ = scan.scan(data, "clean", random.Random(1), dpi=120)
        self.assertLess(small[0].width, large[0].width)


if __name__ == "__main__":
    unittest.main(verbosity=2)
