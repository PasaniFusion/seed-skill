import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from fractions import Fraction as Fr

from _load import load, FIX

terms = load("seed-terms", "terms")
F = os.path.join(FIX, "seed-terms")


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = terms.main(argv)
    return code, out.getvalue(), err.getvalue()


def safe(spec):
    return terms.parse_safe(spec)


class Inputs(unittest.TestCase):
    def test_money_and_percent(self):
        self.assertEqual(terms.parse_money("1.5m", "x"), 1500000)
        self.assertEqual(terms.parse_money("$1,500,000", "x"), 1500000)
        self.assertEqual(terms.parse_money("500K", "x"), 500000)
        self.assertEqual(terms.parse_pct("20", "x"), Fr(1, 5))
        self.assertEqual(terms.parse_pct("12.5%", "x"), Fr(1, 8))
        for bad in ("abc", "-5", "0"):
            with self.assertRaises(terms.TermsError):
                terms.parse_money(bad, "x")
        with self.assertRaises(terms.TermsError):
            terms.parse_pct("0.2", "x")            # say 20 for 20%

    def test_safe_spec(self):
        s = safe("Northlight=500k@10m:20")
        self.assertEqual((s["name"], s["investment"], s["cap"], s["discount"]), ("Northlight", 500000, 10 ** 7, Fr(1, 5)))
        s = safe("100k@:20")
        self.assertIsNone(s["cap"])
        with self.assertRaises(terms.TermsError):
            safe("1m@500k")                         # a cap below the investment


class SafeMath(unittest.TestCase):
    def test_ownership_at_the_cap(self):
        rows, total = terms.safe_ownership([safe("500k@10m"), safe("1m@10m")])
        self.assertEqual([o for _, o in rows], [Fr(1, 20), Fr(1, 10)])
        self.assertEqual(total, Fr(3, 20))
        with self.assertRaises(terms.TermsError):
            terms.safe_ownership([safe("6m@10m"), safe("5m@10m")])
        with self.assertRaises(terms.TermsError):
            terms.safe_ownership([safe("100k@:20")])

    def test_converts_at_the_cap(self):
        r = terms.solve_round(9000000, 0, [safe("1m@10m")], Fr(20 * 10 ** 6), Fr(5 * 10 ** 6), Fr(0))
        self.assertEqual((r["fd_pre"], r["pps"], r["new_shares"]), (10 ** 7, 2, 2500000))
        s = r["safes"][0]
        self.assertEqual((s["via"], s["price"], s["shares"]), ("cap", 1, 10 ** 6))
        self.assertEqual(s["shares"] / r["fd_post"], Fr(2, 25))   # 8% after the round

    def test_converts_at_the_discount(self):
        r = terms.solve_round(9000000, 0, [safe("1m@30m:20")], Fr(20 * 10 ** 6), Fr(5 * 10 ** 6), Fr(0))
        s = r["safes"][0]
        self.assertEqual((s["via"], s["shares"], r["fd_pre"], r["new_shares"]), ("discount", 600000, 9600000, 2400000))
        self.assertEqual(s["price"], r["pps"] * Fr(4, 5))
        self.assertEqual(9000000 / r["fd_post"], Fr(3, 4))

    def test_uncapped_converts_at_the_round_price(self):
        r = terms.solve_round(9000000, 0, [safe("1m")], Fr(20 * 10 ** 6), Fr(5 * 10 ** 6), Fr(0))
        self.assertEqual((r["safes"][0]["via"], r["safes"][0]["price"]), ("round price", r["pps"]))


class RoundMath(unittest.TestCase):
    def test_the_option_pool_shuffle(self):
        r = terms.solve_round(7000000, 0, [], Fr(6 * 10 ** 6), Fr(1500000), Fr(1, 10))
        self.assertEqual((r["fd_pre"], r["pps"], r["pool_topup"], r["new_shares"], r["fd_post"]),
                         (8000000, Fr(3, 4), 1000000, 2000000, 10 ** 7))
        self.assertEqual(r["pool_topup"] * r["pps"], 750000)       # effective pre-money $5.25M

    def test_an_existing_pool_counts_toward_the_target(self):
        r = terms.solve_round(8000000, 2000000, [], Fr(6 * 10 ** 6), Fr(1500000), Fr(1, 10))
        self.assertEqual(r["pool_topup"], 0)                       # 2M of 10M is already 20%

    def test_safes_and_a_pool_together_hold_every_invariant(self):
        safes = [safe("500k@10m"), safe("250k@8m:20")]
        V, N, P = Fr(24 * 10 ** 6), Fr(6 * 10 ** 6), Fr(1, 10)
        r = terms.solve_round(9000000, 1000000, safes, V, N, P)
        conv = sum(s["shares"] for s in r["safes"])
        self.assertEqual(r["fd_pre"], 9000000 + conv + r["pool_topup"])
        self.assertEqual(r["company_cap"], 9000000 + conv)
        self.assertEqual(r["safes"][0]["shares"] / r["company_cap"], Fr(1, 20))   # 5% of the capitalization
        self.assertEqual(r["pool_after"] / r["fd_post"], P)
        self.assertEqual(r["new_shares"] / r["fd_post"], N / (V + N))
        self.assertEqual([s["via"] for s in r["safes"]], ["cap", "cap"])

    def test_impossible_inputs_are_refused(self):
        with self.assertRaises(terms.TermsError):
            terms.solve_round(1000, 0, [safe("6m@10m"), safe("5m@10m")], Fr(10 ** 7), Fr(10 ** 6), Fr(0))


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_safe_output_and_write(self):
        code, text, _ = run(["safe", "--investment", "500k", "--cap", "10m", "--name", "Northlight", "--other",
                             "1m@10m", "--write", "--dir", self.d])
        self.assertEqual(code, 0)
        self.assertIn("$500,000 / $10,000,000 = 5.00%", text)
        self.assertIn("Existing holders keep 85.00%", text)
        self.assertIn("Not legal advice", text)
        with open(os.path.join(self.d, "terms", "safe.json")) as fh:
            doc = json.load(fh)
        self.assertEqual((doc["ownership_at_cap"], doc["all_safes"]), (0.05, 0.15))

    def test_round_output_and_write(self):
        code, text, _ = run(["round", "--pre", "6m", "--raise", "1.5m", "--pool", "10", "--shares", "7000000",
                             "--write", "--dir", self.d])
        self.assertEqual(code, 0)
        for part in ("Price per share  $0.7500", "Effective pre-money: $6,000,000 - $750,000 = $5,250,000",
                     "Existing holders go from 100.00% to 70.00%"):
            self.assertIn(part, text)
        with open(os.path.join(self.d, "terms", "round.json")) as fh:
            doc = json.load(fh)
        self.assertEqual((doc["price_per_share"], doc["pool_topup_shares"], doc["new_investor_shares"],
                          doc["effective_pre_money"]), (0.75, 1000000, 2000000, 5250000.0))

    def test_round_from_a_cap_table(self):
        code, text, _ = run(["round", "--pre", "24m", "--raise", "6m", "--pool", "10", "--cap-table",
                             os.path.join(F, "cap-table.json")])
        self.assertEqual(code, 0)
        self.assertIn("Casey Morgan (founder)", text)
        self.assertIn("Northlight, $500,000", text)

    def test_refusals_exit_1(self):
        for argv in (["safe", "--investment", "100k", "--discount", "20"],
                     ["safe", "--investment", "1m", "--cap", "500k"],
                     ["round", "--pre", "6m", "--raise", "1.5m", "--pool", "60"],
                     ["scan", os.path.join(self.d, "missing.txt")]):
            code, _, err = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertNotIn("Traceback", err)


class Scanner(unittest.TestCase):
    def scan(self, name):
        with open(os.path.join(F, name), encoding="utf-8") as fh:
            return terms.scan_text(fh.read())

    def test_the_tough_sheet_flags_every_trap(self):
        found = {f["key"]: f["severity"] for f in self.scan("term-sheet-tough.txt")}
        self.assertEqual(found, {
            "liquidation_preference": "high", "participating": "high", "dividends": "high", "anti_dilution": "high",
            "redemption": "high", "board": "high", "protective_provisions": "high", "pay_to_play": "medium",
            "drag_along": "high", "no_shop": "high", "exploding": "high", "vesting_reset": "high",
            "super_pro_rata": "medium", "mfn": "low", "pool_shuffle": "medium"})
        for f in self.scan("term-sheet-tough.txt"):
            self.assertTrue(f["note"] and f["ask"] and f["excerpt"], f["key"])

    def test_the_clean_sheet_is_standard(self):
        found = {f["key"]: f["severity"] for f in self.scan("term-sheet-clean.txt")}
        self.assertEqual(found, {"liquidation_preference": "standard", "participating": "standard",
                                 "dividends": "standard", "anti_dilution": "standard", "redemption": "standard",
                                 "board": "standard", "protective_provisions": "low", "no_shop": "standard",
                                 "exploding": "low"})

    def test_edges(self):
        one = lambda t: {f["key"]: (f["severity"], f["clause"]) for f in terms.scan_text(t)}
        self.assertEqual(one("No-Shop: forty-five (45) days.")["no_shop"], ("medium", "No-shop of 45 days"))
        self.assertEqual(one("Pro Rata: investors may participate in future rounds."), {})
        self.assertEqual(one("Liquidation Preference: 1.5x, participating, capped at 3x.")["participating"][0],
                         "medium")
        self.assertEqual(one("Board: three directors, two designated by the holders of Common Stock and one "
                             "designated by the Investors.")["board"][0], "standard")

    def test_scan_cli_exit_codes_and_write(self):
        d = tempfile.mkdtemp()
        try:
            code, text, _ = run(["scan", os.path.join(F, "term-sheet-tough.txt"), "--write", "--dir", d])
            self.assertEqual(code, 3)
            self.assertIn("15 flags: 11 high, 3 medium, 1 low", text)
            with open(os.path.join(d, "terms", "scan-term-sheet-tough.md"), encoding="utf-8") as fh:
                self.assertIn("Ask your lawyer", fh.read())
            self.assertEqual(run(["scan", os.path.join(F, "term-sheet-clean.txt")])[0], 0)
            code, text, _ = run(["scan", os.path.join(F, "safe-side-letter.txt"), "--json"])
            self.assertEqual([f["key"] for f in json.loads(text)["flags"]], ["mfn"])
        finally:
            shutil.rmtree(d)
