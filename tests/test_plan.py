"""seed-plan tests. tests/fixtures/seed-plan/leashly/ is a seed/ folder in the shapes of the
spec: config.json (seed-plan's own example), plan.json with the nine sections written,
model.json (seed-model's output for its example), and synthetic market.json and
competitors.json carrying the reel's numbers."""

import copy
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from decimal import Decimal

from _load import load, FIX, ROOT

plan = load("seed-plan", "plan")
model = load("seed-model", "model")

LEASHLY = os.path.join(FIX, "seed-plan", "leashly")
TINY = os.path.join(FIX, "seed-model", "tiny.json")
SECTION_TITLES = ["Executive summary", "Problem", "Solution", "Market", "Competition", "Business model",
                  "Go-to-market", "Financial plan", "Use of funds"]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write(path, doc):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = plan.main(argv)
    return code, out.getvalue(), err.getvalue()


class Numbers(unittest.TestCase):
    def test_parse_money(self):
        for text, want in (("1500000", 1500000), ("1,500,000", 1500000), ("$1.5M", 1500000), ("750k", 750000),
                           ("2B", 2000000000), (" $250K ", 250000)):
            self.assertEqual(plan.parse_money(text), Decimal(want), text)
        for bad in ("lots", "1.5 million dollars", "-5", ""):
            with self.assertRaises(plan.PlanError):
                plan.parse_money(bad)

    def test_short_money(self):
        for v, want in ((158000000000, "$158B"), (8520000000, "$8.5B"), (228000000, "$228M"),
                        (22800000, "$22.8M"), (2993520, "$2.99M"), (1586640, "$1.59M"), (1500000, "$1.5M"),
                        (467400, "$467K"), (82801, "$82.8K"), (950, "$950"), (-82801, "-$82.8K")):
            self.assertEqual(plan.short_money(v), want, v)

    def test_tokens_and_tracing(self):
        known = plan.known_values({"tam": 8520000000, "c": 2.225, "take": 15, "share": 0.4, "ltv_cac": 4.24,
                                   "ratings": 515771, "label": "card processing (2.9% + $0.30)", "when": "2029-12"})
        cases = [("$8.5B", True), ("$8.52B", True), ("$9B", False), ("$2.23", True), ("$2.22", False),
                 ("15%", True), ("40%", True), ("4.24x", True), ("4.2x", True), ("515,771", True),
                 ("515,000", False), ("2.9%", True), ("$0.30", True), ("12", False)]
        for text, ok in cases:
            toks = [t for t in plan.tokens(text) if plan.worth_checking(t)]
            self.assertEqual(len(toks), 1, text)
            self.assertEqual(plan.matches(toks[0], known), ok, text)
        # years, small counts, minutes and ordinals are not checked
        self.assertEqual(plan.untraced("In 2025, 3 cities, a 30m walk, the 1st city, 1-2 stars.", known), [])
        self.assertEqual(plan.untraced("Revenue of $9B in 2029.", known), ["$9B"])

    def test_unit_economics(self):
        a = read(os.path.join(LEASHLY, "model.json"))["assumptions"]
        ue = plan.unit_economics(a)
        self.assertEqual((ue["price"], ue["take_rate_pct"], ue["revenue_per_order"], ue["cost_per_order"]),
                         (25, 15, 3.75, 1.525))
        self.assertEqual((ue["contribution_per_order"], ue["contribution_per_customer_month"]), (2.225, 17.8))
        self.assertEqual((ue["ltv"], ue["ltv_cac"], ue["cac_payback_months"]), (254.29, 4.24, 3.37))
        self.assertEqual([c["amount"] for c in ue["costs"]], [1.025, 0.5])
        # the same as seed-model's own numbers, for any assumptions
        for doc in (read(os.path.join(ROOT, "seed-model", "assumptions.example.json")), read(TINY)):
            mine = plan.unit_economics(model.clean(doc))
            theirs = model.run_model(doc)["unit_economics"]
            for k, v in theirs.items():
                self.assertEqual(mine[k], v, k)
        with self.assertRaises(plan.PlanError):
            plan.unit_economics({"price": 25})


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def leashly(self):
        shutil.copytree(LEASHLY, "seed")

    def path(self, name):
        return os.path.join("seed", name)

    def edit(self, name, fn):
        doc = read(self.path(name))
        fn(doc)
        write(self.path(name), doc)

    def flags(self):
        code, out, _ = run(["check", "--json"])
        doc = json.loads(out)
        self.assertEqual(code, 0 if doc["ok"] else 1)
        return doc["flags"], doc["notes"]

    def test_init_writes_the_shared_config_and_the_skeleton(self):
        code, out, err = run(["init", "--name", "Leashly", "--one-liner", "A dog-walking app", "--raise", "$1.5M",
                              "--instrument", "post-money SAFE", "--founder", "Your Name", "--email",
                              "you@leashly.example", "--tagline", "Dog walks without the surprise fees.",
                              "--brand", "#112233"])
        self.assertEqual(code, 0, err)
        cfg = read(self.path("config.json"))
        self.assertEqual(sorted(cfg["startup"]), sorted(["name", "one_liner", "sector", "stage", "geography", "raise",
                                                        "instrument"]))
        self.assertEqual(cfg["startup"]["raise"], 1500000)
        self.assertEqual(cfg["startup"]["stage"], "seed")
        self.assertEqual(sorted(cfg["founder"]), ["company_address", "email", "name"])
        self.assertEqual(cfg["sec_user_agent"], "Your Name you@leashly.example")
        self.assertEqual(cfg["outreach"], {"daily_cap": 20, "followup_days": [3, 7], "max_touches": 3,
                                           "business_days": True})
        p = read(self.path("plan.json"))
        self.assertEqual([s["title"] for s in p["sections"]], SECTION_TITLES)
        self.assertTrue(all(s["text"] == "" and s["pitch"] == "" and s["points"] == [] for s in p["sections"]))
        self.assertEqual(p["brand"], {"brand": "#112233", "ink": "#0E1B33", "accent": "#FFB020"})
        self.assertEqual(p["team"], [{"name": "Your Name", "role": "Founder", "line": ""}])
        self.assertIn("Wrote seed/config.json.", out)
        self.assertIn("Wrote seed/plan.json.", out)
        # the shape matches the example in the skill folder
        ex = read(os.path.join(ROOT, "seed-plan", "config.example.json"))
        self.assertEqual(sorted(k for k in ex if not k.startswith("_")), sorted(cfg))
        self.assertEqual(sorted(ex["startup"]), sorted(cfg["startup"]))
        self.assertEqual(ex["outreach"], cfg["outreach"])

        code, _, err = run(["init", "--name", "X", "--one-liner", "Y"])
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        os.remove(self.path("plan.json"))
        code, out, _ = run(["init"])                 # an existing config is kept
        self.assertEqual(code, 0)
        self.assertIn("Kept the existing", out)
        self.assertEqual(read(self.path("config.json")), cfg)
        code, _, _ = run(["init", "--force", "--name", "Other", "--one-liner", "Z"])
        self.assertEqual(code, 0)
        self.assertEqual(read(self.path("config.json"))["startup"]["name"], "Other")

    def test_init_refusals(self):
        code, _, err = run(["init"])
        self.assertEqual(code, 2)
        self.assertIn("--name and --one-liner", err)
        code, _, err = run(["init", "--name", "A", "--one-liner", "B", "--brand", "blue"])
        self.assertEqual(code, 2)
        self.assertIn("#2F6FEB", err)
        code, _, err = run(["init", "--name", "A", "--one-liner", "B", "--raise", "lots"])
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.path("plan.json")))
        code, out, _ = run(["init", "--name", "A", "--one-liner", "B"])
        self.assertIn("no raise yet", out)

    def test_build_the_reel(self):
        self.leashly()
        code, out, err = run(["build", "--today", "2026-10-26"])
        self.assertEqual(code, 0, err)
        for line in ("Leashly: business plan, 9 of 9 sections written.",
                     "  Per walk     price $25.00, take 15% = $3.75, contribution $2.23",
                     "  LTV:CAC      4.24x, CAC payback 3.37 months",
                     "Every check passed",
                     "Wrote seed/plan.md and seed/plan.json.", "/seed-deck"):
            self.assertIn(line, out)
        with open(self.path("plan.md"), encoding="utf-8") as fh:
            md = fh.read()
        for line in ("# Leashly: business plan",
                     "Raising a $1,500,000 seed round on a post-money SAFE. Built Oct 26, 2026",
                     "| Market (TAM / SAM / SOM) | $8.5B / $228M / $22.8M |",
                     "| Revenue, years 1 to 3 | $467,400 / $1,586,640 / $2,993,520 |",
                     "| Breakeven | month 29 (May 2029) |",
                     "- Rover: 106 of 341 recent 1 and 2 star reviews mention fees and pricing.",
                     "- Wag!: 81 of 324 recent 1 and 2 star reviews mention cancellations and no-shows.",
                     "| Rover | 4.9 | 515,771 | 341 of 500 read | Fees and pricing | 106 of 341 mention fees and pricing |",
                     "| US pet industry spend, 2025 | $158,000,000,000 | APPA 2026 State of the Industry report",
                     "| **Contribution per walk** | **$2.23** |",
                     "| CAC payback | 3.37 months (CAC / contribution per customer a month) |",
                     "| **LTV:CAC** | **4.24x** |",
                     "| Revenue | $467,400 | $1,586,640 | $2,993,520 |",
                     "| Net | -$680,476 | -$525,714 | $96,275 |",
                     "| City launches (3 cities) | $450,000 | 30% |",
                     "Adds up to the $1,500,000 raise.",
                     "**Team.** Your Name, Founder and CEO. Ran the Austin pilot with 210 owners.",
                     "Not investment advice."):
            self.assertIn(line, md)
        for i, t in enumerate(SECTION_TITLES, start=1):
            self.assertIn("## %d. %s" % (i, t), md)
        p = read(self.path("plan.json"))
        n = p["numbers"]
        self.assertEqual((p["flags"], p["notes"], p["built"]), ([], [], "2026-10-26"))
        self.assertEqual(p["startup"]["name"], "Leashly")
        self.assertEqual(p["founder"], {"name": "Your Name", "email": "you@leashly.example"})
        self.assertEqual((n["raise"], n["instrument"]), (1500000, "post-money SAFE"))
        self.assertEqual((n["market"]["tam"], n["market"]["sam"], n["market"]["som"]), (8520000000, 228000000, 22800000))
        self.assertEqual([(c["name"], c["top_count"], c["low_reviews"]) for c in n["competitors"]],
                         [("Rover", 106, 341), ("Wag!", 81, 324)])
        self.assertEqual(n["unit_economics"]["contribution_per_order"], 2.225)
        self.assertEqual(n["financials"]["breakeven_month"], 29)
        self.assertEqual([y["revenue"] for y in n["financials"]["years"]], [467400, 1586640, 2993520])
        self.assertEqual(n["use_of_funds_pct"], {"Product and engineering": 40, "City launches (3 cities)": 30,
                                                 "Marketing": 20, "Operations and insurance": 10})
        # the deck's fixture is this build
        self.assertEqual(p, read(os.path.join(FIX, "seed-deck", "leashly", "plan.json")))
        self.assertEqual(run(["check"])[0], 0)

    def test_flags_disagreements(self):
        self.leashly()
        cases = [
            ("config.json", lambda d: d["startup"].update({"raise": 1200000}),
             "The raise disagrees: config.json says $1,200,000, model.json says $1,500,000."),
            ("model.json", lambda d: d["summary"]["use_of_funds"].update({"Marketing": 250000}),
             "The use of funds adds up to $1,450,000, not the $1,500,000 raise."),
            ("market.json", lambda d: d.update(som=300000000), "The SOM ($300M) is bigger than the SAM ($228M)."),
            ("market.json", lambda d: d.update(sam=9000000000), "The SAM ($9B) is bigger than the TAM ($8.5B)."),
            ("market.json", lambda d: d.update(som=15000000),
             "Year 3 GMV ($20M) is above your SOM ($15M): the model sells more"),
            ("market.json", lambda d: d.update(currency="EUR"), "market.json is in EUR but model.json is in USD."),
            ("model.json", lambda d: d["summary"].update(revenue_y2=1),
             "model.json says year 2 revenue is $1 but its months add up to $1,586,640"),
            ("model.json", lambda d: d["assumptions"].update(price=30),
             "model.json's unit economics (revenue_per_order, contribution_per_order, ltv, ltv_cac, "
             "cac_payback_months) no longer match its assumptions"),
            ("model.json", lambda d: d["assumptions"].update(take_rate_pct=5),
             "Each walk loses money before opex: contribution is -$0.28."),
            ("plan.json", lambda d: d["sections"][2].update(text=""),
             "Solution is empty: write it in seed/plan.json (sections[2].text)."),
            ("config.json", lambda d: d["startup"].update({"raise": None}),
             "config.json has no startup.raise"),
        ]
        for name, fn, want in cases:
            shutil.rmtree("seed")
            self.leashly()
            self.edit(name, fn)
            flags, _ = self.flags()
            self.assertTrue(any(want in f for f in flags), "%s\n%s" % (want, flags))
        shutil.rmtree("seed")
        self.leashly()
        for f in ("model.json", "market.json", "competitors.json"):
            os.remove(self.path(f))
        flags, notes = self.flags()
        self.assertIn("No seed/model.json: run /seed-model first, then build again.", flags)
        self.assertIn("No seed/market.json: run /seed-market first, then build again.", flags)
        self.assertIn("No seed/competitors.json: run /seed-scout first, then build again.", flags)
        self.assertTrue(any(n.startswith("Problem text: 106, 341, 81, 324 are in none") for n in notes), notes)
        code, out, _ = run(["build", "--today", "2026-10-26"])
        self.assertEqual(code, 0)                     # build still writes, and says what to fix
        self.assertIn("  FIX   No seed/model.json", out)
        self.assertIn("fix the items marked FIX", out)
        with open(self.path("plan.md"), encoding="utf-8") as fh:
            self.assertIn("- **Fix:** No seed/model.json", fh.read())
        self.assertEqual(run(["check"])[0], 1)

    def test_notes(self):
        self.leashly()

        def weak(d):
            d["cac"] = 250                               # LTV:CAC 254.29 / 250, payback 250 / 17.8 months
            d["raise"] = 300000
            d["use_of_funds"] = {"All of it": 300000}

        m = read(self.path("model.json"))
        doc = m["assumptions"]
        weak(doc)
        write(self.path("model.json"), model.run_model(doc))
        self.edit("config.json", lambda d: d["startup"].update({"raise": 300000}))

        def prose(d):
            d["tagline"] = ""
            d["team"] = []
            d["sections"][1]["pitch"] = ""
            d["sections"][3]["text"] += " It grows 12% a year."
        self.edit("plan.json", prose)
        flags, notes = self.flags()
        self.assertEqual(flags, [])
        joined = "\n".join(notes)
        for want in ("LTV:CAC is 1.02x, under the 3x", "CAC payback is 14.04 months, over the 12",
                     "The cash runs out in month", "No breakeven inside the 36 months",
                     "Market text: 12% is in none of the seed/ files.", "No tagline", "No team",
                     "Problem has no pitch line"):
            self.assertIn(want, joined)

    def test_missing_files_and_bad_json(self):
        code, _, err = run(["build"])
        self.assertEqual(code, 2)
        self.assertIn("run plan.py init first", err)
        self.leashly()
        with open(self.path("market.json"), "w") as fh:
            fh.write("{not json")
        code, _, err = run(["check"])
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)
        code, _, err = run(["build", "--today", "26/10/2026"])
        self.assertEqual(code, 2)
        self.assertIn("--today wants YYYY-MM-DD", err)
        self.assertEqual(run([])[0], 2)

    def test_market_as_objects_and_a_missing_top_theme(self):
        self.leashly()
        self.edit("market.json", lambda d: d.update(tam={"value": 8520000000}, sam={"value": 228000000},
                                                    som={"value": 22800000}))
        self.edit("competitors.json", lambda d: [(a.pop("top_theme"), a.pop("weak_point_count")) for a in d["apps"]]
                  and d.pop("theme_labels"))
        code, out, _ = run(["build", "--today", "2026-10-26", "--json"])
        doc = json.loads(out)
        self.assertEqual(doc["flags"], [])
        self.assertEqual(doc["numbers"]["market"]["som"], 22800000)
        self.assertEqual(doc["numbers"]["competitors"][0]["top_theme"], "fees")


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "seed-plan", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\nname: seed-plan\ndescription: >-\n"))
        self.assertGreater(len(text.splitlines()), 60)
        self.assertIn("${CLAUDE_SKILL_DIR}", text)
        self.assertIn("## Example: the reel", text)
        low = " ".join(text.lower().split())
        for must in ("not investment advice", "/seed-deck", "/seed-model", "/seed-market", "/seed-scout",
                     "investors decide", "106 of 341", "81 of 324", "515,771", "$158b", "$8.5b", "$2.23", "4.24x",
                     "month 29", "config.example.json"):
            self.assertIn(must, low)
        self.assertNotIn("\u2014", text)
        for t in SECTION_TITLES:
            self.assertIn(t.lower(), low)


if __name__ == "__main__":
    unittest.main()
