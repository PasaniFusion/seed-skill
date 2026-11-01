"""seed-coach tests. tests/fixtures/seed-coach/seed/ is a SYNTHETIC seed folder for the reel's made-up
startup Leashly: config, competitors (the reel's App Store counts, no review text), a model.json in the
seed-model schema, market.json and investors.json written by this repo's own tools, a booked pipeline
row and the call invite seed-closer would write (Thu Nov 5 2026, 15:00 UTC = 10:00 AM ET)."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX, ROOT

coach = load("seed-coach", "coach")

SEED = os.path.join(FIX, "seed-coach", "seed")
BANK = os.path.join(ROOT, "seed-coach", "questions.json")
STRONG = ("15% flat, no owner fee. We keep $3.75 of every $25 walk and $2.23 after card fees and the backup "
          "walker. Rover keeps 20% of sitter bookings and adds an owner fee.")


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = coach.main(argv)
    return code, out.getvalue(), err.getvalue()


class Bank(unittest.TestCase):
    def test_the_bank_covers_every_category(self):
        bank = coach.load_bank()
        cats = bank["categories"]
        self.assertEqual(cats, ["market", "competition", "traction", "unit economics", "team", "why now", "risks",
                                "the ask"])
        ids = [q["id"] for q in bank["questions"]]
        self.assertEqual(len(ids), len(set(ids)))
        for c in cats:
            generic = [q for q in bank["questions"] if q["category"] == c and not coach.fields(q["q"])]
            self.assertGreaterEqual(len(generic), 3, c)
        for q in bank["questions"]:
            for k in ("id", "category", "q", "tests", "strong"):
                self.assertTrue(q.get(k), (q["id"], k))
            self.assertIn(q["category"], cats)


class Tailoring(unittest.TestCase):
    def test_context_from_the_seed_folder(self):
        ctx = coach.context(SEED, "maya-chen", "owners", "walker")
        expect = {"startup": "Leashly", "raise": "$1.5M", "c1_name": "Rover", "c1_ratings": "515,771",
                  "c1_count": 106, "c1_low": 341, "c1_weak": "fees and pricing", "c2_name": "Wag!", "c2_count": 81,
                  "take_rate": "15%", "price": "$25", "revenue_per_order": "$3.75", "contribution_per_order": "$2.23",
                  "ltv_cac": "4.24x", "breakeven_month": 29, "peak_burn": "$82,801", "tam": "$17.04B", "sam": "$960M",
                  "som": "$24M", "som_share": "2.5%", "som_years": 3, "inv_first": "Maya",
                  "inv_check": "$250,000-$1M", "top_fund": "Product and engineering", "provider_pay": "walker pay",
                  "customers": "owners"}
        for k, v in expect.items():
            self.assertEqual(ctx[k], v, k)

    def test_the_reel_questions(self):
        ctx = coach.context(SEED, customers="owners", provider="walker")
        qs = coach.pick(coach.load_bank(), ctx, 10)
        text = [q["q"] for q in qs]
        self.assertIn("Rover has 515,771 ratings. Why will owners switch?", text)
        self.assertIn("What does your 15% take rate leave after walker pay?", text)
        self.assertTrue(all(q["tailored"] for q in qs))                  # tailored ones come first
        self.assertEqual(len(set(q["category"] for q in qs[:5])), 5)     # one per category before seconds
        take = [q for q in qs if q["id"] == "ue-take"][0]
        self.assertEqual(take["hint"], "Per walk: $25 price, you keep $3.75, $2.23 after costs.")

    def test_missing_files_fall_back_to_generic(self):
        d = tempfile.mkdtemp()
        try:
            ctx = coach.context(d)
            self.assertEqual(ctx["provider_pay"], "costs")
            qs = coach.pick(coach.load_bank(), ctx, 8)
            self.assertFalse(any(q["tailored"] for q in qs))
            self.assertEqual([q["category"] for q in qs], coach.load_bank()["categories"])
        finally:
            shutil.rmtree(d)

    def test_category_and_seed_are_repeatable(self):
        bank, ctx = coach.load_bank(), coach.context(SEED)
        a = coach.pick(bank, ctx, 5, "team", seed=7)
        self.assertEqual(a, coach.pick(bank, ctx, 5, "team", seed=7))
        self.assertTrue(all(q["category"] == "team" for q in a))
        with self.assertRaises(coach.CoachError):
            coach.pick(bank, ctx, 5, "vibes")

    def test_fill_needs_every_placeholder(self):
        self.assertIsNone(coach.fill("{a} and {b}", {"a": 1}))
        self.assertEqual(coach.fill("{a} and {b}", {"a": 1, "b": 2}), "1 and 2")
        self.assertEqual(coach.money(2.225), "$2.23")
        self.assertEqual(coach.money(17040000000), "$17.04B")


class Grade(unittest.TestCase):
    def test_a_strong_answer(self):
        g = coach.grade(STRONG)
        self.assertEqual((g["score"], g["passed"], g["words"], g["seconds"]), (100, True, 32, 13))

    def test_each_check(self):
        g = coach.grade("I think we could maybe disrupt the market")
        self.assertEqual(g["score"], 20)
        notes = dict((c["check"], (c["ok"], c["note"])) for c in g["checks"])
        self.assertIn("i think, maybe", notes["no hedging"][1])
        self.assertIn("disrupt", notes["specific"][1])
        self.assertFalse(notes["a number"][0])
        long = " ".join(["Rover charges 20% and we charge 15%."] * 30)
        g = coach.grade(long)
        notes = dict((c["check"], (c["ok"], c["note"])) for c in g["checks"])
        self.assertFalse(notes["length"][0])
        self.assertIn("over a minute", notes["length"][1])
        rambling = ("Well so the thing about our company and how we got here and what we learned along the way "
                    "over many months of work with our customers is that we charge 15% to Rover users.")
        g = coach.grade(rambling)
        self.assertFalse([c for c in g["checks"] if c["check"] == "answer first"][0]["ok"])
        self.assertTrue(coach.grade("We charge 15% to owners in Austin and Denver, and 340 of them booked twice "
                                    "in the first month.")["passed"])
        with self.assertRaises(coach.CoachError):
            coach.grade("   ")

    def test_hedges_are_whole_words(self):
        g = coach.grade("Mighty Paws pays 15% to walkers in Austin, Denver and Boise every single week, and 40 "
                        "of them stayed a year.")
        self.assertTrue([c for c in g["checks"] if c["check"] == "no hedging"][0]["ok"])   # "Mighty" is not "might"


class Agenda(unittest.TestCase):
    def test_minutes_always_add_up(self):
        self.assertEqual(coach.split_minutes(20), [2, 3, 4, 4, 4, 2, 1])
        for total in range(10, 61):
            m = coach.split_minutes(total)
            self.assertEqual(sum(m), total, total)
            self.assertTrue(all(x >= 1 for x in m))
        for bad in (9, 61):
            with self.assertRaises(coach.CoachError):
                coach.split_minutes(bad)

    def test_the_call_time_from_the_invite(self):
        call = coach.read_call(os.path.join(SEED, "calls", "maya-chen.ics"))
        self.assertEqual(call, {"when": "Thu Nov 5 2026, 10:00 AM ET", "link": "https://meet.google.com/abc-defg-hij"})
        # the day the clocks change: 06:30 UTC on Nov 1 2026 is 1:30 AM EST, 05:30 UTC is 1:30 AM EDT
        dt = coach.datetime.datetime
        self.assertEqual(coach.utc_to_eastern(dt(2026, 11, 1, 6, 30)), dt(2026, 11, 1, 1, 30))
        self.assertEqual(coach.utc_to_eastern(dt(2026, 11, 1, 5, 30)), dt(2026, 11, 1, 1, 30))
        self.assertEqual(coach.utc_to_eastern(dt(2026, 3, 8, 7, 0)), dt(2026, 3, 8, 3, 0))
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "x.ics")
            with open(p, "w") as fh:
                fh.write("BEGIN:VEVENT\nDTSTART;TZID=America/New_York:20261105T100000\nEND:VEVENT\n")
            self.assertEqual(coach.read_call(p), {"when": "Thu Nov 5 2026, 10:00 AM (America/New_York)"})
            self.assertIsNone(coach.read_call(os.path.join(d, "none.ics")))
        finally:
            shutil.rmtree(d)

    def test_the_agenda_for_maya(self):
        ag = coach.build_agenda(SEED, "maya-chen")
        self.assertEqual((ag["name"], ag["firm"], ag["status"]), ("Maya Chen", "Northlight Ventures", "booked"))
        self.assertEqual([b["minutes"] for b in ag["blocks"]], [2, 3, 4, 4, 4, 2, 1])
        self.assertEqual(ag["blocks"][-1]["end"], 20)
        text = json.dumps(ag)
        self.assertIn("Saw you led two pet-care seed rounds", text)
        self.assertIn("Rover: 106 of 341 recent 1-2 star reviews mention fees and pricing.", text)
        self.assertIn("TAM $17.04B, SAM $960M, SOM $24M", text)
        self.assertIn("$1.5M post-money SAFE", text)
        with self.assertRaises(coach.CoachError) as cm:
            coach.build_agenda(SEED, "nobody")
        self.assertEqual(cm.exception.code, 1)


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.seed = os.path.join(self.d, "seed")
        shutil.copytree(SEED, self.seed)

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_drill_grade_agenda_round_trip(self):
        code, text, _ = run(["drill", "--dir", self.seed, "--customers", "owners", "--provider", "walker"])
        self.assertEqual(code, 0)
        self.assertIn(" 2. [competition] Rover has 515,771 ratings. Why will owners switch?", text)
        self.assertFalse(os.path.exists(os.path.join(self.seed, "coach")))     # nothing written without --write
        code, text, _ = run(["drill", "--dir", self.seed, "--n", "3", "--json", "--write"])
        self.assertEqual(len(json.loads(text)["questions"]), 3)
        with open(os.path.join(self.seed, "coach", "drill.md")) as fh:
            self.assertTrue(fh.read().startswith("# Pitch drill"))
        code, text, _ = run(["drill", "--dir", self.seed, "--investor", "maya-chen", "--category", "the ask"])
        self.assertIn("Maya's record:", text)
        self.assertEqual(run(["grade", "--answer", STRONG, "--question", "ue-take"])[0], 0)
        code, text, _ = run(["grade", "--answer", "maybe soon"])
        self.assertEqual(code, 1)
        self.assertIn("Fix the unchecked lines", text)
        p = os.path.join(self.d, "a.txt")
        with open(p, "w") as fh:
            fh.write(STRONG)
        code, text, _ = run(["grade", "--file", p, "--json"])
        self.assertEqual((code, json.loads(text)["score"]), (0, 100))
        code, text, _ = run(["agenda", "--dir", self.seed, "--investor", "maya-chen", "--write"])
        self.assertEqual(code, 0)
        self.assertIn("When: Thu Nov 5 2026, 10:00 AM ET, https://meet.google.com/abc-defg-hij", text)
        self.assertIn(" 0-2  min  Hello and why them", text)
        self.assertTrue(os.path.isfile(os.path.join(self.seed, "coach", "agenda-maya-chen.md")))

    def test_exit_codes(self):
        self.assertEqual(run(["grade"])[0], 2)                               # no answer
        self.assertEqual(run(["grade", "--file", os.path.join(self.d, "none.txt")])[0], 2)
        self.assertEqual(run(["grade", "--answer", STRONG, "--question", "nope"])[0], 2)
        self.assertEqual(run(["drill", "--dir", self.seed, "--n", "0"])[0], 2)
        self.assertEqual(run(["drill", "--dir", self.seed, "--category", "vibes"])[0], 2)
        self.assertEqual(run(["drill", "--dir", self.seed, "--investor", "nobody"])[0], 1)
        self.assertEqual(run(["agenda", "--dir", self.seed, "--investor", "nobody"])[0], 1)
        self.assertEqual(run(["agenda", "--dir", os.path.join(self.d, "empty"), "--investor", "maya-chen"])[0], 1)
        self.assertEqual(run(["agenda", "--dir", self.seed, "--investor", "maya-chen", "--minutes", "5"])[0], 2)
        self.assertEqual(run([])[0], 2)


if __name__ == "__main__":
    unittest.main()
