"""seed-updates tests. tests/fixtures/seed-updates/metrics.json is the Leashly pilot example
(fictional) with seed-plan's example config; edge.json covers a raise landing, an explicit net
burn, a gap month, a metric that starts late and a month where the cash grows."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from decimal import Decimal

from _load import load, FIX, ROOT

upd = load("seed-updates", "update")

LEASHLY = os.path.join(FIX, "seed-updates", "metrics.json")
CONFIG = os.path.join(FIX, "seed-updates", "config.json")
EDGE = os.path.join(FIX, "seed-updates", "edge.json")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = upd.main(argv)
    return code, out.getvalue(), err.getvalue()


class Math(unittest.TestCase):
    def test_growth(self):
        self.assertEqual(upd.change(6600, 5325, "usd"), ("up 23.9%", 1))          # 1,275 / 5,325 = 23.94%
        self.assertEqual(upd.change(171, 210, "count"), ("down 18.6%", -1))
        self.assertEqual(upd.change(100, 100, "count"), ("flat", 0))
        self.assertEqual(upd.change(2.4, 2.8, "pct"), ("down 0.4 pts", -1))
        self.assertEqual(upd.change(4.5, 4.5, "pct"), ("flat", 0))
        self.assertEqual(upd.change(5, None, "usd"), ("new this month", 0))
        self.assertEqual(upd.change(1500, 0, "usd"), ("new this month", 0))
        self.assertEqual(upd.change(0, 0, "usd"), ("flat", 0))
        self.assertEqual(upd.change(-50, -100, "usd"), ("up 50%", 1))               # a smaller loss is up
        self.assertEqual(upd.mom(6600, 5325, "usd"), "+23.9%")
        self.assertEqual(upd.mom(2.4, 2.8, "pct"), "-0.4 pts")

    def test_months(self):
        self.assertEqual(upd.add_months("2026-11", 10), "2027-09")
        self.assertEqual(upd.add_months("2027-01", -1), "2026-12")
        self.assertEqual(upd.add_months("2027-03", 82), "2034-01")
        self.assertEqual(upd.month_name("2026-11"), "November 2026")
        for bad in ("2026-13", "2026-1", "Nov 2026", None):
            with self.assertRaises(upd.UpdateError):
                upd.parse_month(bad)

    def test_the_reel_runway(self):
        doc = read(LEASHLY)
        self.assertEqual(upd.burn_of(doc, "2026-11"), Decimal(18700))              # 196,500 - 177,800
        self.assertEqual(upd.burn_of(doc, "2026-10"), Decimal(17500))              # 214,000 - 196,500
        self.assertIsNone(upd.burn_of(doc, "2026-09"))                             # no August to compare with
        rw = upd.runway(doc, "2026-11")
        self.assertEqual((rw["avg_burn"], rw["months_used"]), (Decimal(18100), 2))
        self.assertEqual(rw["runway"], Decimal("9.8"))                              # 177,800 / 18,100 = 9.82
        self.assertEqual(rw["until"], "2027-09")

    def test_edge_runway(self):
        doc = read(EDGE)
        self.assertEqual(upd.burn_of(doc, "2027-01"), Decimal(6000))
        self.assertEqual(upd.burn_of(doc, "2027-02"), Decimal(6000))               # 44,000 + 500,000 - 538,000
        self.assertEqual(upd.burn_of(doc, "2027-03"), Decimal(7500))               # the explicit net_burn wins
        rw = upd.runway(doc, "2027-03")
        self.assertEqual((rw["avg_burn"], rw["months_used"]), (Decimal(6500), 3))
        self.assertEqual((rw["runway"], rw["until"]), (Decimal("81.7"), "2034-01"))
        self.assertIsNone(upd.burn_of(doc, "2027-05"))                             # April is missing
        self.assertIsNone(upd.runway(doc, "2027-05")["runway"])
        rw = upd.runway(doc, "2027-06")
        self.assertEqual((rw["burn"], rw["runway"]), (Decimal(-3000), None))       # the cash grew


class Text(unittest.TestCase):
    def test_the_reel_investor_update(self):
        text, warnings = upd.investor_update(read(LEASHLY), "2026-11", read(CONFIG))
        self.assertEqual(warnings, [])
        lines = text.splitlines()
        self.assertEqual(lines[0], "Subject: Leashly investor update: November 2026")
        for line in ("**TL;DR:** Revenue $6,600 (+23.9% MoM), walks completed 1,760 (+23.9%), active owners 210 "
                     "(+22.8%). Runway 9.8 months.",
                     "- Revenue: $6,600, up 23.9% from $5,325",
                     "- GMV (what owners paid): $44,000, up 23.9% from $35,500",
                     "- Walks saved by a backup walker: 31, up 19.2% from 26",
                     "- Walker cancellations: 2.4%, down 0.4 pts from 2.8%",
                     "- Walker cancellations are down to 2.4%, still above our 2% goal.",
                     "1. Intros to property managers of dog-friendly apartment buildings in Austin.",
                     "Cash at the end of November: $177,800. Net burn this month: $18,700. Average net burn over the "
                     "last 2 months: $18,100 a month, so the cash lasts about 9.8 months, to around Sep 2027.",
                     "Your Name", "Founder, Leashly"):
            self.assertIn(line, lines)
        order = [text.index(h) for h in ("**TL;DR:**", "**The numbers", "**Highlights**", "**Lowlights**",
                                         "**Asks**", "**Runway**")]
        self.assertEqual(order, sorted(order))

    def test_the_reel_prospect_update(self):
        text, warnings = upd.prospect_update(read(LEASHLY), "2026-11", read(CONFIG))
        lines = text.splitlines()
        self.assertEqual(lines[0], "Subject: Leashly: November 2026 update")
        self.assertEqual(lines[2], "Hi {first_name},")
        self.assertIn("**November 2026:** Revenue $6,600 (+23.9% MoM), walks completed 1,760 (+23.9%), active "
                      "owners 210 (+22.8%).", lines)
        self.assertIn("We are raising a $1.5M seed (post-money SAFE). If the timing is better now, would a "
                      "20-minute call be useful?", lines)
        self.assertIn(upd.OPT_OUT, lines)
        self.assertEqual(sum(1 for l in lines if l.startswith("- ")), 2)          # the top two highlights
        for never in ("$177,800", "Runway", "runway", "burn", "Lowlights", "Card fees", "Asks"):
            self.assertNotIn(never, text)
        self.assertIn("Replace {first_name} for each investor before it goes out.", warnings)

    def test_edge_text(self):
        doc = read(EDGE)
        text, warnings = upd.investor_update(doc, "2027-02")
        self.assertIn("- Revenue: $1,500, new this month", text)                 # up from $0
        self.assertIn("- NPS: 41, new this month", text)
        self.assertIn("- Churn: 4.5%, down 0.5 pts from 5%", text)
        self.assertIn("{your_name}", text)
        self.assertIn("Edge Co", text)
        self.assertTrue(any("No lowlights for 2027-02" in w for w in warnings))
        self.assertTrue(any("No founder name" in w for w in warnings))
        text, _ = upd.investor_update(doc, "2027-03")
        self.assertIn("- Churn: 4.5%, flat on Feb 2027", text)
        text, _ = upd.investor_update(doc, "2027-05")
        self.assertNotIn("NPS", text)
        self.assertIn("there is no runway figure yet", text)
        text, warnings = upd.investor_update(doc, "2027-06")
        self.assertIn("**TL;DR:** Cash went up in June.", text)
        self.assertIn("Cash grew $3,000 this month.", text)
        self.assertIn("the cash is not running down", text)
        self.assertEqual([w for w in warnings if "No " in w and "founder" not in w], [])
        text, warnings = upd.prospect_update(doc, "2027-06")
        self.assertIn("We are raising our seed round.", text)
        self.assertIn("**June 2027:** Revenue $2,600 (+30% MoM), users 230 (+15%).", text)

    def test_refusals(self):
        doc = read(LEASHLY)
        with self.assertRaises(upd.UpdateError) as cm:
            upd.investor_update(doc, "2026-12")
        self.assertIn("no 2026-12 in metrics.json (it has 2026-09, 2026-10, 2026-11)", str(cm.exception))
        bad = read(LEASHLY)
        bad["months"].append(dict(bad["months"][0]))
        bad["metrics"][0]["unit"] = "dollars"
        bad["months"][1]["values"]["mood"] = 7
        bad["months"][2]["cash"] = "lots"
        with self.assertRaises(upd.UpdateError) as cm:
            upd.validate(bad)
        for why in ("months has 2026-09 twice", "unit is usd, count or pct", "'mood' is not one of the metrics",
                    "2026-11 cash is not a number"):
            self.assertIn(why, str(cm.exception))
        with self.assertRaises(upd.UpdateError):
            upd.validate({"months": []})


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def test_init_add_write(self):
        code, out, _ = run(["init"])
        self.assertEqual(code, 0)
        self.assertEqual(read(os.path.join("seed", "metrics.json")),
                         read(os.path.join(ROOT, "seed-updates", "metrics.example.json")))
        code, _, err = run(["init"])
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        shutil.copy(CONFIG, os.path.join("seed", "config.json"))

        code, out, _ = run(["write", "--month", "2026-11"])
        self.assertEqual(code, 0)
        self.assertIn("Wrote seed/updates/2026-11.md (investor update for November 2026).", out)
        self.assertIn("Nothing was sent.", out)
        expected, _ = upd.investor_update(read(LEASHLY), "2026-11", read(CONFIG))
        with open(os.path.join("seed", "updates", "2026-11.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), expected)
        code, out, _ = run(["write", "--month", "2026-11", "--to", "prospects"])
        self.assertTrue(os.path.exists(os.path.join("seed", "updates", "2026-11-prospects.md")))
        self.assertIn("Replace {first_name}", out)

        code, out, _ = run(["add", "--month", "2026-12", "--set", "revenue=7,875", "--set", "walks=2100",
                            "--cash", "1650000", "--money-in", "1500000", "--highlight", "Closed the seed.",
                            "--lowlight", "Hiring is slow.", "--ask", "Engineers."])
        self.assertEqual(code, 0)
        self.assertIn("Saved 2026-12 in seed/metrics.json: 2 values, cash $1,650,000.", out)
        self.assertIn("Not set yet for 2026-12: active_owners, gmv, backup_saves, cancel_rate.", out)
        doc = read(os.path.join("seed", "metrics.json"))
        dec = doc["months"][-1]
        self.assertEqual(dec["values"], {"revenue": 7875, "walks": 2100})
        self.assertEqual((dec["cash"], dec["money_in"]), (1650000, 1500000))
        run(["add", "--month", "2026-12", "--set", "gmv=52500", "--highlight", "Second pilot city signed."])
        dec = read(os.path.join("seed", "metrics.json"))["months"][-1]
        self.assertEqual(dec["values"]["gmv"], 52500)
        self.assertEqual(dec["highlights"], ["Closed the seed.", "Second pilot city signed."])
        run(["add", "--month", "2026-08", "--set", "revenue=3000", "--cash", "230000"])
        self.assertEqual([m["month"] for m in read(os.path.join("seed", "metrics.json"))["months"]],
                         ["2026-08", "2026-09", "2026-10", "2026-11", "2026-12"])

        code, out, err = run(["write", "--stdout"])                    # the latest month, nothing written
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("Subject: Leashly investor update: December 2026"))
        self.assertIn("Net burn this month: $27,800.", out)          # 177,800 + 1,500,000 - 1,650,000
        self.assertIn("Average net burn over the last 3 months: $21,333 a month", out)
        self.assertFalse(os.path.exists(os.path.join("seed", "updates", "2026-12.md")))
        self.assertEqual(err, "")                                    # a full month: nothing to flag
        code, out, err = run(["write", "--stdout", "--to", "prospects"])
        self.assertTrue(out.startswith("Subject: Leashly: December 2026 update"))
        self.assertEqual(err, "Note: Replace {first_name} for each investor before it goes out.\n")

    def test_exit_codes(self):
        code, _, err = run(["write"])
        self.assertEqual(code, 2)
        self.assertIn("run update.py init first", err)
        run(["init"])
        for argv, why in ((["write", "--month", "2027-02"], "no 2027-02"),
                          (["write", "--month", "Nov"], "--month wants YYYY-MM"),
                          (["add", "--month", "2026-12", "--set", "mood=7"], "'mood' is not one of your metrics"),
                          (["add", "--month", "2026-12", "--set", "revenue"], "--set wants key=value"),
                          (["add", "--month", "2026-12", "--set", "revenue=lots"], "not a number"),
                          (["add", "--month", "2026/12"], "--month wants YYYY-MM")):
            code, _, err = run(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(why, err, argv)
            self.assertNotIn("Traceback", err)
        self.assertEqual(len(read(os.path.join("seed", "metrics.json"))["months"]), 3)   # nothing half-written
        self.assertEqual(run([])[0], 2)


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "seed-updates", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\nname: seed-updates\ndescription: >-\n"))
        self.assertGreater(len(text.splitlines()), 60)
        self.assertIn("${CLAUDE_SKILL_DIR}", text)
        self.assertIn("## Example: the reel", text)
        low = " ".join(text.lower().split())
        for must in ("not investment advice", "yes", "opt-out", "not now", "/seed-closer", "{first_name}",
                     "$177,800", "$18,100", "9.8 months", "sep 2027", "never send", "lowlights"):
            self.assertIn(must, low)
        self.assertNotIn("\u2014", text)
        text_out, _ = upd.investor_update(read(LEASHLY), "2026-11", read(CONFIG))
        for line in ("**TL;DR:** Revenue $6,600 (+23.9% MoM), walks completed 1,760 (+23.9%), active owners 210 "
                     "(+22.8%). Runway 9.8 months.", "- Revenue: $6,600, up 23.9% from $5,325",
                     "- Walker cancellations: 2.4%, down 0.4 pts from 2.8%"):
            self.assertIn(line, text)
            self.assertIn(line, text_out)


if __name__ == "__main__":
    unittest.main()
