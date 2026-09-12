# -*- coding: utf-8 -*-
"""생성 결과의 내부 정합성과 다양성을 검증한다."""

import math
import re
import unittest
from collections import Counter

from minutes_generator import GENERATORS, build_minutes, sample
from minutes_generator.render import ground_truth, render_text

SEEDS = range(1, 401)


class ConsistencyTest(unittest.TestCase):
    """문서 안의 숫자들이 서로 모순되지 않는지 본다."""

    def test_capital_matches_shares(self):
        for seed in SEEDS:
            m = build_minutes(seed)
            self.assertEqual(m.company.capital,
                             m.company.par_value * m.company.shares_issued, seed)
            self.assertGreaterEqual(m.company.authorized_shares, m.company.shares_issued, seed)

    def test_quorum_and_vote_arithmetic(self):
        for seed in SEEDS:
            m = build_minutes(seed)
            n = len(m.directors)
            self.assertGreaterEqual(m.present_directors, n // 2 + 1, seed)
            self.assertTrue(m.chair.present, seed)
            for item, v in m.agenda:
                self.assertEqual(v.favor + v.against + v.abstain, v.present, (seed, item.kind))
                self.assertLessEqual(v.present, v.eligible, (seed, item.kind))
                if v.result != "부결":
                    need = (math.ceil(n * 2 / 3) if item.special_majority
                            else v.present // 2 + 1)
                    self.assertGreaterEqual(v.favor, min(need, v.present), (seed, item.kind))
                if item.interested_director:
                    self.assertEqual(v.excluded, item.interested_director, seed)
                    self.assertEqual(v.eligible, n - 1, seed)

    def test_unique_people(self):
        for seed in SEEDS:
            m = build_minutes(seed)
            everyone = [o.name for o in m.directors + m.auditors]
            if m.secretary:
                everyone.append(m.secretary.name)
            self.assertEqual(len(everyone), len(set(everyone)), seed)

    def test_signers_are_present(self):
        for seed in SEEDS:
            m = build_minutes(seed)
            for o in m.signers:
                self.assertTrue(o.present, (seed, o.name))

    def test_agenda_facts_add_up(self):
        checks = 0
        for seed in SEEDS:
            m = build_minutes(seed)
            for item, _v in m.agenda:
                f = item.facts
                k = item.kind
                if k == "third_party_issue":
                    self.assertEqual(sum(a["shares"] for a in f["allottees"]), f["new_shares"], seed)
                    self.assertEqual(f["total_amount"], f["new_shares"] * f["issue_price"], seed)
                    for a in f["allottees"]:
                        self.assertEqual(a["amount"], a["shares"] * f["issue_price"], seed)
                elif k == "convertible_bond":
                    self.assertEqual(f["convertible_shares"],
                                     f["face_value"] // f["conversion_price"], seed)
                    self.assertGreaterEqual(f["ytm"], f["coupon_rate"], seed)
                elif k == "warrant_bond":
                    self.assertEqual(f["exercise_shares"],
                                     f["face_value"] // f["exercise_price"], seed)
                elif k == "financial_statements":
                    self.assertEqual(f["assets"], f["liabilities"] + f["equity"], seed)
                elif k == "interim_dividend":
                    self.assertEqual(f["total_dividend"],
                                     f["dividend_per_share"] * f["target_shares"], seed)
                    self.assertLessEqual(f["target_shares"], m.company.shares_issued, seed)
                elif k == "stock_option":
                    self.assertEqual(f["total_shares"], sum(g["shares"] for g in f["grants"]), seed)
                elif k == "equity_investment":
                    self.assertEqual(f["amount"], f["shares"] * f["unit_price"], seed)
                elif k == "subsidiary":
                    self.assertEqual(f["investment"], int(f["capital"] * f["ratio"] / 100), seed)
                elif k == "treasury_stock":
                    self.assertEqual(f["amount"], f["shares"] * f["unit_price"], seed)
                elif k == "real_estate":
                    self.assertAlmostEqual(f["area_pyeong"], f["area_sqm"] / 3.305785, places=1)
                else:
                    continue
                checks += 1
        self.assertGreater(checks, 200, "검증된 의안 수가 너무 적다")

    def test_dates_are_ordered(self):
        for seed in SEEDS:
            m = build_minutes(seed)
            self.assertLess(m.start_time, m.end_time, seed)
            for item, _v in m.agenda:
                f = item.facts
                if item.kind in ("agm_convocation", "egm_convocation"):
                    self.assertGreater(f["meeting_date"], m.meeting_date.isoformat(), seed)
                if item.kind == "convertible_bond":
                    self.assertGreater(f["maturity_date"], f["issue_date"], seed)
                if item.kind == "real_estate":
                    self.assertGreater(f["balance_date"], f["contract_date"], seed)
                if item.kind == "treasury_stock":
                    self.assertGreater(f["end_date"], f["start_date"], seed)


class RenderTest(unittest.TestCase):

    def test_renders_without_placeholder_josa(self):
        leftovers = re.compile(r"(은\(는\)|이\(가\)|을\(를\)|와\(과\)|\(으\)로)")
        for seed in SEEDS:
            text, _gt = sample(seed)
            self.assertFalse(leftovers.search(text), f"seed={seed} 조사 병기가 남아 있다")
            self.assertIn("의사록", text.replace(" ", "") or "")

    def test_ground_truth_values_appear_in_text(self):
        """정답셋의 핵심 숫자가 본문에 실제로 인쇄되는지 확인한다."""
        for seed in SEEDS:
            m = build_minutes(seed)
            text = render_text(m, seed)
            gt = ground_truth(m)
            for d in gt["directors"] + gt["auditors"]:
                self.assertIn(d["name"], text, (seed, d["name"]))
            for a in gt["agenda"]:
                f = a["facts"]
                for key in ("total_amount", "face_value", "amount", "total_dividend", "limit"):
                    if key in f:
                        self.assertIn(f"{f[key]:,}", text, (seed, a["kind"], key))

    def test_line_width(self):
        for seed in list(SEEDS)[:120]:
            text, _ = sample(seed)
            for line in text.splitlines():
                self.assertLess(len(line), 160, seed)


class DiversityTest(unittest.TestCase):
    """같은 문장·같은 숫자가 반복되지 않는지 본다."""

    def setUp(self):
        self.docs = [sample(s) for s in SEEDS]

    def test_company_names_vary(self):
        names = [gt["company"]["name"] for _t, gt in self.docs]
        self.assertGreater(len(set(names)) / len(names), 0.85)

    def test_people_vary(self):
        people = [d["name"] for _t, gt in self.docs for d in gt["directors"]]
        self.assertGreater(len(set(people)) / len(people), 0.75)

    def test_agenda_kinds_cover_catalog(self):
        kinds = Counter(a["kind"] for _t, gt in self.docs for a in gt["agenda"])
        self.assertEqual(set(kinds) - set(GENERATORS), set())
        self.assertGreaterEqual(len(kinds), len(GENERATORS) - 1,
                                f"등장하지 않은 의안: {set(GENERATORS) - set(kinds)}")

    def test_layout_styles_vary(self):
        for field in ("date_format", "money_format", "agenda_label", "attendance_layout"):
            values = Counter(gt["style"][field] for _t, gt in self.docs)
            self.assertGreaterEqual(len(values), 2, field)

    def test_opening_sentences_vary(self):
        firsts = []
        for text, _gt in self.docs:
            for line in text.splitlines():
                if line.startswith(("의장", "위와 같이", "본 이사회")):
                    firsts.append(line[:24])
                    break
        self.assertGreaterEqual(len(set(firsts)), 8)

    def test_documents_are_not_duplicates(self):
        bodies = [t for t, _g in self.docs]
        self.assertEqual(len(set(bodies)), len(bodies))

    def test_same_seed_is_reproducible(self):
        a, ga = sample(12345)
        b, gb = sample(12345)
        self.assertEqual(a, b)
        self.assertEqual(ga, gb)


if __name__ == "__main__":
    unittest.main(verbosity=2)
