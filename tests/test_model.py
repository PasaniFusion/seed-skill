"""seed-model tests. The Leashly assumptions are seed-model/assumptions.example.json (the reel's
fictional startup); tiny.json is small enough to check by hand."""

import copy
import csv
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from decimal import Decimal, ROUND_HALF_UP

from _load import load, FIX, ROOT

model = load("seed-model", "model")

EXAMPLE = os.path.join(ROOT, "seed-model", "assumptions.example.json")
TINY = os.path.join(FIX, "seed-model", "tiny.json")
BAD = os.path.join(FIX, "seed-model", "bad.json")
PLAN_MODEL = os.path.join(FIX, "seed-plan", "leashly", "model.json")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = model.main(argv)
    return code, out.getvalue(), err.getvalue()


def half_up(x):
    return int(Decimal(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))


class Leashly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = read(EXAMPLE)
        cls.m = model.run_model(cls.doc)

    def test_unit_economics_exact(self):
        ue = self.m["unit_economics"]
        self.assertEqual(ue["revenue_per_order"], 3.75)                  # 25 x 15%
        self.assertEqual(ue["cost_per_order"], 1.525)                    # 25 x 2.9% + 0.30 + 0.50
        self.assertEqual(ue["contribution_per_order"], 2.225)
        self.assertEqual(ue["contribution_per_customer_month"], 17.8)    # 2.225 x 8 walks
        self.assertEqual(ue["ltv"], 254.29)                              # 17.8 / 7%
        self.assertEqual(ue["ltv_cac"], 4.24)                            # 254.2857 / 60
        self.assertEqual(ue["cac_payback_months"], 3.37)                 # 60 / 17.8

    def test_month_one_by_hand(self):
        r = self.m["months"][0]
        self.assertEqual(r["date"], "2027-01")
        self.assertEqual(r["churned"], 15)                               # 210 x 7% = 14.7, half up
        self.assertEqual(r["customers"], 210 - 15 + 150)
        self.assertEqual(r["orders"], 345 * 8)
        self.assertEqual(r["gmv"], 2760 * 25)
        self.assertEqual(r["revenue"], 10350)                            # 69,000 x 15%
        self.assertEqual(r["cost_of_revenue"], 4209)                     # 2,760 x 1.525
        self.assertEqual(r["gross_profit"], 6141)
        self.assertEqual(r["payroll"], 28800)                            # (9,000 + 9,000 + 6,000) x 1.2
        self.assertEqual(r["marketing"], 9000)                           # 150 new x $60
        self.assertEqual(r["other_opex"], 7000)
        self.assertEqual(r["net"], 6141 - 44800)
        self.assertEqual(r["cash"], 1500000 - 38659)

    def test_hires_and_one_offs_land_in_their_month(self):
        m = self.m["months"]
        self.assertEqual(m[1]["payroll"], (24000 + 11000) * 1.2)         # the engineer from month 2
        self.assertEqual(m[4]["other_opex"], 7000 + 25000)               # city 2 launch, month 5
        self.assertEqual(m[4]["payroll"], (24000 + 11000 + 4500 + 6000) * 1.2)
        self.assertEqual(m[5]["other_opex"], 7000)

    def test_growth_rate_changes_each_year(self):
        new = [r["new_customers"] for r in self.m["months"]]
        f12 = Decimal(150) * Decimal("1.1") ** 11
        self.assertEqual(new[11], half_up(f12))
        self.assertEqual(new[12], half_up(f12 * Decimal("1.05")))        # year 2 grows 5% a month
        self.assertEqual(new[24], half_up(f12 * Decimal("1.05") ** 12 * Decimal("1.02")))

    def test_the_reel_summary(self):
        s = self.m["summary"]
        self.assertEqual((s["revenue_y1"], s["revenue_y2"], s["revenue_y3"]), (467400, 1586640, 2993520))
        self.assertEqual(s["gmv_y3"], 19956800)
        self.assertEqual((s["breakeven_month"], s["breakeven_date"]), (29, "2029-05"))
        self.assertEqual((s["peak_burn"], s["peak_burn_month"]), (82801, 5))
        self.assertEqual((s["runway_months"], s["cash_out_month"]), (36, None))
        self.assertEqual((s["cash_low"], s["cash_low_month"]), (252553, 28))
        self.assertEqual(s["customers_end"], 9999)
        self.assertTrue(s["funds_match"])
        self.assertEqual(s["use_of_funds_total"], 1500000)

    def test_summary_agrees_with_the_months(self):
        m, s = self.m["months"], self.m["summary"]
        self.assertEqual(len(m), 36)
        for y in (1, 2, 3):
            rows = m[(y - 1) * 12:y * 12]
            self.assertAlmostEqual(sum(r["revenue"] for r in rows), s["revenue_y%d" % y], places=6)
            self.assertAlmostEqual(sum(r["gmv"] for r in rows), s["gmv_y%d" % y], places=6)
        self.assertLess(m[27]["net"], 0)
        self.assertTrue(all(r["net"] >= 0 for r in m[28:]))
        self.assertEqual(min(r["net"] for r in m), -82801)
        for a, b in zip(m, m[1:]):
            self.assertAlmostEqual(b["cash"], a["cash"] + b["net"], places=6)

    def test_deterministic_and_the_plan_fixture_is_this_output(self):
        self.assertEqual(model.run_model(read(EXAMPLE)), self.m)
        self.assertEqual(read(PLAN_MODEL), json.loads(json.dumps(self.m)))


class Tiny(unittest.TestCase):
    def test_by_hand(self):
        m = model.run_model(read(TINY))
        r = m["months"]
        self.assertEqual([x["customers"] for x in r[:3]], [10, 19, 27])         # churn 0, then 1, then 1.9 -> 2
        self.assertEqual([x["net"] for x in r[:3]], [-1420, -1348, -1284])     # gp 80/152/216, opex 1,500
        self.assertEqual([x["cash"] for x in r[:3]], [8580, 7232, 5948])
        self.assertEqual(r[1]["date"], "2027-12")
        self.assertEqual(r[2]["date"], "2028-01")                               # across the year end
        ue = m["unit_economics"]
        self.assertEqual((ue["contribution_per_order"], ue["ltv"], ue["ltv_cac"], ue["cac_payback_months"]),
                         (8, 80, 1.6, 6.25))
        # the same model in plain integers, to find the month the cash runs out
        cust, cash, out = 0, 0, None
        for k in range(1, 37):
            cust = cust - half_up(Decimal(cust) / 10) + 10
            cash += cust * 8 - 1500 + (10000 if k == 1 else 0)
            if cash < 0 and out is None:
                out = k
        s = m["summary"]
        self.assertEqual(s["cash_out_month"], out)
        self.assertEqual(s["runway_months"], out - 1)
        self.assertIsNone(s["breakeven_month"])
        self.assertEqual((s["peak_burn"], s["peak_burn_month"]), (1420, 1))
        self.assertTrue(s["funds_match"])

    def test_a_raise_that_lands_late(self):
        doc = dict(read(TINY), raise_month=3)
        s = model.run_model(doc)["summary"]
        self.assertEqual((s["cash_out_month"], s["runway_months"]), (1, 0))   # broke before the money lands

    def test_a_business_that_makes_money_from_month_one(self):
        doc = dict(read(TINY), payroll=[], cac=0)
        s = model.run_model(doc)["summary"]
        self.assertEqual((s["breakeven_month"], s["peak_burn"], s["peak_burn_month"]), (1, 0, None))


class Refusals(unittest.TestCase):
    def test_every_problem_is_listed(self):
        with self.assertRaises(model.ModelError) as cm:
            model.validate(read(BAD))
        msg = str(cm.exception)
        for why in ("start_month wants YYYY-MM", "price must be above 0", "take_rate_pct must be 100 or less",
                    "raise is not a number", "churn_monthly_pct must be", "new_growth_pct wants one number",
                    "use_of_funds['Hiring'] must be above 0"):
            self.assertIn(why, msg)
        self.assertEqual(cm.exception.code, 2)

    def test_missing_fields(self):
        with self.assertRaises(model.ModelError) as cm:
            model.validate({"start_month": "2027-01"})
        for k in ("price is missing", "take_rate_pct is missing", "raise is missing", "cac is missing",
                  "customers is missing"):
            self.assertIn(k, str(cm.exception))
        doc = read(TINY)
        del doc["customers"]["churn_monthly_pct"]
        with self.assertRaises(model.ModelError) as cm:
            model.validate(doc)
        self.assertIn("customers.churn_monthly_pct is missing", str(cm.exception))
        with self.assertRaises(model.ModelError):
            model.validate([1, 2])

    def test_funds(self):
        ok, lines = model.check_funds(read(EXAMPLE))
        self.assertTrue(ok)
        self.assertIn("  Product and engineering       $600,000   40.0%", lines)
        self.assertEqual(lines[-1], "Adds up to the raise.")
        short = read(EXAMPLE)
        short["use_of_funds"]["Marketing"] = 250000
        ok, lines = model.check_funds(short)
        self.assertFalse(ok)
        self.assertIn("Short by $50,000", lines[-1])
        over = read(EXAMPLE)
        over["use_of_funds"]["Marketing"] = 300000.5
        ok, lines = model.check_funds(over)
        self.assertFalse(ok)
        self.assertIn("Over by $0.50", lines[-1])
        none = read(EXAMPLE)
        del none["use_of_funds"]
        ok, lines = model.check_funds(none)
        self.assertFalse(ok)
        self.assertFalse(model.run_model(none)["summary"]["funds_match"])


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def test_init_run_write_csv(self):
        code, out, _ = run(["init"])
        self.assertEqual(code, 0)
        self.assertEqual(read(os.path.join("seed", "assumptions.json")), read(EXAMPLE))
        code, _, err = run(["init"])
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertEqual(run(["init", "--force"])[0], 0)

        code, out, _ = run(["run"])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join("seed", "model.json")))
        self.assertIn("Nothing written", out)
        for line in ("  Revenue                  $467,400     $1,586,640     $2,993,520",
                     "  Breakeven          month 29 (May 2029), and every month after it",
                     "  Peak burn          $82,801 in month 5 (May 2027)",
                     "  Runway             the cash lasts all 36 months (low point $252,553 in month 28)",
                     "Not investment advice."):
            self.assertIn(line, out)

        code, out, _ = run(["run", "--write"])
        self.assertEqual(code, 0)
        self.assertIn("Wrote seed/model.json.", out)
        self.assertIn("/seed-plan", out)
        self.assertEqual(read(os.path.join("seed", "model.json")), read(PLAN_MODEL))

        code, out, _ = run(["csv"])
        self.assertEqual(code, 0)
        with open(os.path.join("seed", "model.csv"), encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), 37)
        self.assertEqual(rows[0], model.CSV_FIELDS)
        self.assertEqual(rows[1][:8], ["1", "2027-01", "150", "15", "345", "2760", "69000.00", "10350.00"])
        self.assertEqual(rows[2][9], "8650.80")
        self.assertNotIn("changed since", out)

        doc = read(os.path.join("seed", "assumptions.json"))
        doc["price"] = 30
        with open(os.path.join("seed", "assumptions.json"), "w") as fh:
            json.dump(doc, fh)
        code, out, _ = run(["csv"])
        self.assertIn("changed since", out)
        code, out, _ = run(["csv", "--out", "-"])
        self.assertTrue(out.startswith("month,date,new_customers"))

    def test_json_and_months(self):
        run(["init"])
        code, out, _ = run(["run", "--json"])
        doc = json.loads(out)
        self.assertNotIn("months", doc)
        self.assertEqual(doc["summary"]["breakeven_month"], 29)
        code, out, _ = run(["run", "--json", "--months"])
        self.assertEqual(len(json.loads(out)["months"]), 36)
        code, out, _ = run(["run", "--months"])
        self.assertIn("     29  2029-05", out)

    def test_exit_codes(self):
        code, _, err = run(["run"])
        self.assertEqual(code, 2)
        self.assertIn("run model.py init first", err)
        code, _, err = run(["run", "--assumptions", BAD])
        self.assertEqual(code, 2)
        self.assertIn("need fixing", err)
        self.assertEqual(run(["funds", "--assumptions", EXAMPLE])[0], 0)
        short = read(EXAMPLE)
        short["use_of_funds"]["Marketing"] = 1
        with open("short.json", "w") as fh:
            json.dump(short, fh)
        code, out, _ = run(["funds", "--assumptions", "short.json", "--json"])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)["ok"])
        code, _, err = run(["csv"])
        self.assertEqual(code, 2)
        self.assertIn("run model.py run --write first", err)
        self.assertEqual(run([])[0], 2)
        self.assertNotIn("Traceback", err)

    def test_dir_flag(self):
        code, _, _ = run(["init", "--dir", "elsewhere"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join("elsewhere", "assumptions.json")))
        self.assertEqual(run(["--dir", "elsewhere", "run", "--write"])[0], 0)
        self.assertTrue(os.path.exists(os.path.join("elsewhere", "model.json")))


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "seed-model", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\nname: seed-model\ndescription: >-\n"))
        self.assertGreater(len(text.splitlines()), 60)
        self.assertIn("${CLAUDE_SKILL_DIR}", text)
        self.assertIn("## Example: the reel", text)
        low = " ".join(text.lower().split())
        for must in ("not investment advice", "/seed-plan", "/seed-deck", "$467,400", "month 29", "$82,801",
                     "4.24x", "$252,553", "use of funds", "## steps"):
            self.assertIn(must, low)
        self.assertNotIn("\u2014", text)
        # the example block is the tool's real output
        out = "\n".join(model.describe(model.run_model(read(EXAMPLE))))
        block = text.split("```\nLeashly: 36-month model", 1)[1].split("```", 1)[0]
        for line in ("Leashly: 36-month model" + block).strip("\n").splitlines():
            self.assertIn(line, out)


if __name__ == "__main__":
    unittest.main()
