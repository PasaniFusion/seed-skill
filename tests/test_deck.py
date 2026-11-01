"""seed-deck tests. tests/fixtures/seed-deck/leashly/ is a seed/ folder after seed-plan's
`plan.py build --today 2026-10-26` on its Leashly fixture: plan.json with its numbers block, plus
the model, market, competitors and config files the lint traces numbers to."""

import copy
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX, ROOT

deck = load("seed-deck", "deck")

LEASHLY = os.path.join(FIX, "seed-deck", "leashly")
ORDER = ["title", "problem", "solution", "market", "competition", "business_model", "go_to_market", "team",
         "financials", "ask"]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write(path, doc):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = deck.main(argv)
    return code, out.getvalue(), err.getvalue()


def files():
    return {f: read(os.path.join(LEASHLY, f)) for f in ("model.json", "market.json", "competitors.json", "config.json")}


class Slides(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = read(os.path.join(LEASHLY, "plan.json"))
        cls.slides = deck.build_slides(cls.plan)
        cls.by = {s["key"]: s for s in cls.slides}

    def texts(self, key):
        return deck.body_texts(self.by[key])

    def test_ten_slides_in_the_standard_order(self):
        self.assertEqual([s["key"] for s in self.slides], ORDER)
        self.assertEqual([s["n"] for s in self.slides], list(range(1, 11)))
        self.assertEqual([s["title"] for s in self.slides],
                         ["Leashly", "The problem", "The solution", "The market", "Competition", "Business model",
                          "Go to market", "Team", "Financials", "The ask"])

    def test_what_each_slide_says(self):
        self.assertEqual(self.texts("title"), ["Dog walks without the surprise fees.",
                                               "Raising a $1.5M seed · post-money SAFE"])
        self.assertEqual(self.by["title"]["foot"], "Your Name · you@leashly.example")
        self.assertEqual(self.texts("problem"), [
            "Owners pay fees on top of fees. Walkers cancel last minute.",
            "106 of 341", "recent 1-2★ Rover reviews mention fees",
            "81 of 324", "recent 1-2★ Wag! reviews mention cancellations"])
        self.assertIn("the 500 most recent per app, read 2026-10-25", self.by["problem"]["foot"])
        self.assertEqual(self.texts("market")[1:], ["TAM", "$8.5B", "the whole market", "SAM", "$228M",
                                                    "what we can serve", "SOM", "$22.8M", "what we can win"])
        self.assertIn("APPA 2026 State of the Industry report", self.by["market"]["foot"])
        self.assertNotIn("assumption", self.by["market"]["foot"])
        self.assertEqual(self.texts("competition")[1:9], ["Rover", "4.9★ · 515,771 ratings", "Weak point", "Fees and pricing",
                                                         "Wag!", "4.8★ · 67,447 ratings", "Weak point",
                                                         "Cancellations and no-shows"])
        self.assertEqual(self.texts("business_model")[1:], ["$25", "a walk", "$3.75", "we keep (15%)", "$2.23",
                                                            "contribution a walk", "4.24x", "LTV:CAC", "3.37 mo",
                                                            "CAC payback"])
        self.assertEqual(self.texts("financials")[1:], ["Revenue", "Year 1", "$467K", "Year 2", "$1.59M", "Year 3",
                                                        "$2.99M", "Month 29", "breakeven (May 2029)", "$82.8K",
                                                        "peak monthly burn"])
        self.assertEqual(self.texts("ask"), ["$1.5M seed to launch in 3 cities.", "Post-money SAFE",
                                             "Product and engineering", "$600K · 40%", "City launches (3 cities)",
                                             "$450K · 30%", "Marketing", "$300K · 20%", "Operations and insurance",
                                             "$150K · 10%"])

    def test_word_counts(self):
        counts = {s["key"]: deck.words(deck.body_texts(s)) for s in self.slides}
        self.assertEqual(counts, {"title": 12, "problem": 29, "solution": 22, "market": 28, "competition": 33,
                                  "business_model": 23, "go_to_market": 31, "team": 23, "financials": 27, "ask": 28})
        self.assertEqual(deck.words(["$25 · 15%", "+", "Rover: fees."]), 4)       # symbols are not words
        self.assertEqual(deck.sentences("One. Two! Three?"), 3)
        self.assertEqual(deck.sentences("$1.5M seed to launch in 3 cities."), 1)

    def test_the_reel_lints_clean(self):
        self.assertEqual(deck.lint(self.plan, self.slides, files()), [])

    def test_ask_mentions_the_raise_when_the_line_does_not(self):
        p = copy.deepcopy(self.plan)
        p["sections"][8]["pitch"] = "Launch in three cities."
        ask = {s["key"]: s for s in deck.build_slides(p)}["ask"]
        self.assertEqual(deck.body_texts(ask)[1], "$1.5M seed · post-money SAFE")

    def test_pitch_falls_back_to_the_first_sentence(self):
        p = copy.deepcopy(self.plan)
        p["sections"][2]["pitch"] = ""
        sol = {s["key"]: s for s in deck.build_slides(p)}["solution"]
        self.assertEqual(sol["blocks"][0]["text"], "One flat price per walk with no owner fee, and a second walker "
                                                    "on standby near every booking.")


class Lint(unittest.TestCase):
    def setUp(self):
        self.plan = read(os.path.join(LEASHLY, "plan.json"))
        self.files = files()

    def issues(self):
        return deck.lint(self.plan, deck.build_slides(self.plan), self.files)

    def assertIssue(self, text):
        found = self.issues()
        self.assertTrue(any(text in x for x in found), "%r not in %s" % (text, found))

    def test_too_many_words(self):
        self.plan["sections"][2]["pitch"] = " ".join(["word"] * 23) + "."          # + 13 in the points
        self.assertIssue("Slide 3 (The solution) has 36 words; keep it to 35 or fewer.")

    def test_one_idea_a_slide(self):
        self.plan["sections"][2]["pitch"] = "Flat price. Backup walker. Live tracking."
        self.assertIssue("Slide 3 (The solution) says 3 things in its lead")
        self.plan["sections"][2]["pitch"] = "Flat price."
        self.plan["sections"][2]["points"] = ["One", "Two", "Three", "Four"]
        self.assertIssue("Slide 3 (The solution) has 4 points: one idea a slide, 3 points at most.")

    def test_every_number_traces(self):
        self.plan["sections"][3]["pitch"] = "$9B US dog walking. 43% of owners use apps, 71M homes have a dog."
        found = self.issues()
        self.assertEqual(found, ["Slide 4 (The market) shows $9B, 43%, in none of plan.json, model.json, "
                                 "market.json, competitors.json or config.json."])
        self.plan["sections"][3]["pitch"] = "40% of the raise builds the product."       # the use of funds share
        self.assertEqual(self.issues(), [])
        self.plan["sections"][3]["pitch"] = "$8.5B US dog walking."
        self.assertEqual(self.issues(), [])

    def test_the_ask_adds_up(self):
        self.plan["numbers"]["use_of_funds"]["Marketing"] = 250000
        self.assertIssue("The ask: the use of funds adds up to $1,450,000, not the $1,500,000 raise.")
        self.plan["numbers"]["raise"] = None
        self.assertIssue("The ask has no raise")

    def test_missing_data_and_empty_slides(self):
        del self.plan["numbers"]["market"]
        self.plan["team"] = []
        self.plan["sections"][6].update(text="", pitch="", points=[])
        self.plan["sections"][1].update(text="", pitch="")
        found = self.issues()
        self.assertIn("The market slide has no data: run /seed-market, then plan.py build.", found)
        self.assertIn("The team slide has no people: add the team to seed/plan.json, then plan.py build.", found)
        self.assertIn("Slide 8 (Team) is empty: write its section in seed/plan.json, then plan.py build.", found)
        self.assertIn("Slide 7 (Go to market) is empty: write its section in seed/plan.json, then plan.py build.",
                      found)
        self.assertIn("Slide 2 (The problem) has no line: write the pitch for it in seed/plan.json.", found)

    def test_a_plan_older_than_the_model(self):
        self.files["model.json"]["summary"]["revenue_y1"] = 500000
        self.assertIssue("plan.json is older than model.json")


class Html(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plan = read(os.path.join(LEASHLY, "plan.json"))
        cls.html = deck.render(plan, deck.build_slides(plan), deck.brand_of(plan, {}))

    def test_one_self_contained_file(self):
        h = self.html
        self.assertTrue(h.startswith("<!doctype html>"))
        self.assertEqual(h.count('<section class="slide'), 10)
        for never in ("<link", "src=", "@import", "url(", "http://", "https://", "\u2014"):
            self.assertNotIn(never, h)
        self.assertEqual(h.count("<style>"), 1)
        self.assertEqual(h.count("<script>"), 1)
        self.assertIn("<title>Leashly: pitch deck</title>", h)

    def test_16_by_9_print_and_keys(self):
        h = self.html
        self.assertIn("width:1280px;height:720px", h)
        self.assertIn("@page{size:13.333in 7.5in;margin:0}", h)
        self.assertIn("@media print{", h)
        self.assertIn("break-after:page", h)
        for key in ("ArrowRight", "ArrowLeft", "PageDown", "PageUp", "Home", "End"):
            self.assertIn("'%s'" % key, h)
        self.assertIn("history.replaceState", h)
        self.assertNotIn("%%", h)                                           # every CSS percent was formatted

    def test_brand_colours(self):
        h = self.html
        self.assertIn("--brand:#2F6FEB;--ink:#0E1B33;--accent:#FFB020", h)
        self.assertEqual(deck.mix("#2F6FEB", "#FFFFFF", 0.08), "#EEF3FD")     # 47 x .08 + 255 x .92 = 238.36
        self.assertEqual(deck.mix("#000000", "#FFFFFF", 0.5), "#808080")
        plan = read(os.path.join(LEASHLY, "plan.json"))
        b = deck.brand_of(plan, {"brand": "#123456"})
        self.assertEqual(b, {"brand": "#123456", "ink": "#0E1B33", "accent": "#FFB020"})
        with self.assertRaises(deck.DeckError):
            deck.brand_of(plan, {"accent": "orange"})

    def test_text_is_escaped(self):
        plan = read(os.path.join(LEASHLY, "plan.json"))
        plan["tagline"] = "<script>alert(1)</script> & more"
        plan["team"][0]["name"] = 'A "quoted" <b>name</b>'
        h = deck.render(plan, deck.build_slides(plan), deck.brand_of(plan, {}))
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; more", h)
        self.assertIn("A &quot;quoted&quot; &lt;b&gt;name&lt;/b&gt;", h)
        self.assertEqual(h.count("<script>"), 1)

    def test_charts_use_the_numbers(self):
        h = self.html
        self.assertIn(">$2.99M</text>", h)
        self.assertIn('<div class="fill" style="width:75%"></div>', h)    # $450K of the $600K top bar
        self.assertIn('aria-label="TAM, SAM and SOM, not to scale"', h)


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.d)
        shutil.copytree(LEASHLY, "seed")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def test_build_outline_lint(self):
        code, out, err = run(["build"])
        self.assertEqual(code, 0, err)
        self.assertIn("Wrote seed/deck.html: 10 slides", out)
        self.assertIn("Lint: clean", out)
        self.assertIn("/seed-coach", out)
        with open(os.path.join("seed", "deck.html"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().count('<section class="slide'), 10)
        code, out, _ = run(["outline"])
        self.assertEqual(code, 0)
        self.assertIn(" 2. The problem      29 words  Owners pay fees on top of fees. Walkers cancel last minute.", out)
        code, out, _ = run(["outline", "--json"])
        self.assertEqual([s["key"] for s in json.loads(out)], ORDER)
        code, out, _ = run(["lint"])
        self.assertEqual(code, 0)
        self.assertIn("the most words on one is 33", out)
        code, out, _ = run(["build", "--out", "out/pitch.html", "--brand", "#0F9D58"])
        self.assertEqual(code, 0)
        with open(os.path.join("out", "pitch.html"), encoding="utf-8") as fh:
            self.assertIn("--brand:#0F9D58", fh.read())

    def test_lint_exit_code_and_build_still_writes(self):
        p = read(os.path.join("seed", "plan.json"))
        p["sections"][1]["pitch"] = "Fees cost owners $43 a walk."
        write(os.path.join("seed", "plan.json"), p)
        code, out, _ = run(["lint", "--json"])
        self.assertEqual(code, 1)
        doc = json.loads(out)
        self.assertFalse(doc["ok"])
        self.assertIn("Slide 2 (The problem) shows $43", doc["issues"][0])
        code, out, _ = run(["build"])
        self.assertEqual(code, 0)
        self.assertIn("The lint found 1 thing to fix:", out)

    def test_refusals(self):
        p = read(os.path.join("seed", "plan.json"))
        write(os.path.join("seed", "plan.json"), dict(p, numbers={}, built=None))
        code, _, err = run(["build"])
        self.assertEqual(code, 2)
        self.assertIn("run plan.py build first", err)
        self.assertFalse(os.path.exists(os.path.join("seed", "deck.html")))
        write(os.path.join("seed", "plan.json"), p)
        code, _, err = run(["build", "--accent", "gold"])
        self.assertEqual(code, 2)
        self.assertIn("#RRGGBB", err)
        shutil.rmtree("seed")
        code, _, err = run(["lint"])
        self.assertEqual(code, 2)
        self.assertIn("run /seed-plan first", err)
        self.assertEqual(run([])[0], 2)


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "seed-deck", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\nname: seed-deck\ndescription: >-\n"))
        self.assertGreater(len(text.splitlines()), 60)
        self.assertIn("${CLAUDE_SKILL_DIR}", text)
        self.assertIn("## Example: the reel", text)
        low = " ".join(text.lower().split())
        for must in ("not investment advice", "investors decide", "/seed-plan", "/seed-coach", "/seed-closer",
                     "35 words", "one idea a slide", "16:9", "print", "arrow", "106 of 341", "$8.5b", "4.24x",
                     "month 29", "$600k (40%)"):
            self.assertIn(must, low)
        self.assertNotIn("\u2014", text)
        # the outline lines quoted in the example are the tool's real output
        plan = read(os.path.join(LEASHLY, "plan.json"))
        for s in deck.build_slides(plan):
            t = deck.body_texts(s)
            line = "%2d. %-16s %2d words  %s" % (s["n"], s["title"], deck.words(t), " | ".join(t))
            for quoted in re.findall(r"(?m)^ ?%d\. .*$" % s["n"], text.split("## Example: the reel")[1]):
                self.assertTrue(line.startswith(quoted.rstrip(" .").rstrip(" |").rstrip(" .")), quoted)


if __name__ == "__main__":
    unittest.main()
