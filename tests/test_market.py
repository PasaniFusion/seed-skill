"""seed-market tests. The worked example is the reel's made-up startup Leashly: the only real
numbers are APPA's (71M US homes with a dog, 53% of homes, $158B of US pet spend in 2025); every
other input is a labelled assumption. tests/fixtures/seed-market/market-bad.json is synthetic."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from decimal import Decimal

from _load import load, FIX

mk = load("seed-market", "market")

BAD = os.path.join(FIX, "seed-market", "market-bad.json")
APPA = "APPA 2026 State of the Industry report (americanpetproducts.org)"
TOP = ["top-down", "--population", "71M", "--population-name", "US homes with a dog", "--population-source", APPA,
       "--share", "10%", "--share-name", "share that pays for dog walking",
       "--share-source", "assumption: about 1 in 10 dog homes pays for walks; check it with an owner survey",
       "--spend", "2400", "--spend-name", "spend on walks a year per paying home",
       "--spend-source", "assumption: 8 walks a month at the $25 flat price, as in seed/model.json"]
BOTTOM = ["bottom-up", "--customers", "400K", "--customers-name", "paying dog homes in the 3 launch cities",
          "--customers-source", "assumption: launch-city dog homes x the same 1 in 10; replace with city data",
          "--frequency", "96", "--frequency-source", "assumption: 8 walks a month, as in seed/model.json",
          "--price", "25", "--price-source", "Leashly pricing: $25 flat per 30-minute walk", "--unit", "walk"]
SOM = ["som", "--share", "2.5%", "--years", "3", "--reason",
       "Owners leaving Rover over fees and Wag! over cancellations switch to flat $25 walks with a backup walker"]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = mk.main(argv)
    return code, out.getvalue(), err.getvalue()


class Numbers(unittest.TestCase):
    def test_parsing(self):
        for text, v in (("71M", 71000000), ("400K", 400000), ("1.5B", 1500000000), ("2,400", 2400), ("$25", 25),
                        ("12.5", Decimal("12.5")), (96, 96)):
            self.assertEqual(mk.num(text, "x"), v, text)
        for bad in ("lots", "0", "-3", "", None, True):
            with self.assertRaises(mk.MarketError):
                mk.num(bad, "x")
        for text, v in (("10%", Decimal("0.1")), ("0.1", Decimal("0.1")), ("10", Decimal("0.1")), ("100%", 1),
                        ("2.5%", Decimal("0.025")), ("1", 1)):
            self.assertEqual(mk.share(text), v, text)
        for bad in ("0%", "150%", "abc", "-5%"):
            with self.assertRaises(mk.MarketError):
                mk.share(bad)
        self.assertEqual((mk.big(17040000000), mk.big(960000000), mk.big(24000000), mk.big(158000000000), mk.big(950)),
                         ("$17.04B", "$960M", "$24M", "$158B", "$950"))
        self.assertEqual(mk.pct_text(Decimal("0.025")), "2.5%")
        self.assertEqual(mk.whole(Decimal("1.5")), 2)          # half up
        self.assertEqual(mk.whole(Decimal("2.5")), 3)
        self.assertEqual(mk.whole(Decimal("2.49")), 2)

    def test_sources(self):
        self.assertEqual(mk.source_kind(APPA, "x")[1], "publication")
        self.assertEqual(mk.source_kind("https://americanpetproducts.org/industry-trends", "x")[1], "url")
        self.assertEqual(mk.source_kind("Assumption: 1 in 10 homes pays", "x")[1], "assumption")
        for bad in ("", "google", "TBD", "ChatGPT", "assumption", "assumption: guess", "Statista", None):
            with self.assertRaises(mk.MarketError) as cm:
                mk.source_kind(bad, "x")
            self.assertEqual(cm.exception.code, 1, bad)


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.seed = os.path.join(self.d, "seed")
        self.path = os.path.join(self.seed, "market.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def cli(self, *args):
        return run(list(args) + ["--dir", self.seed, "--today", "2026-10-26"])

    def doc(self):
        with open(self.path) as fh:
            return json.load(fh)

    def test_the_reel_tam_sam_som(self):
        code, text, _ = self.cli(*TOP)
        self.assertEqual(code, 0)
        self.assertIn("Not saved", text)
        self.assertFalse(os.path.exists(self.path))                    # nothing written without --write
        code, text, err = self.cli(*(TOP + ["--write"]))
        self.assertEqual(code, 0, err)
        self.assertIn("TAM (top-down): $17.04B a year", text)
        self.assertIn("71,000,000 US homes with a dog x 10% x $2,400 = $17,040,000,000", text)
        self.assertIn("Assumptions in it", text)
        self.assertIn("Not investment advice", text)
        self.assertEqual(self.cli(*(BOTTOM + ["--write"]))[0], 0)
        code, text, _ = self.cli(*(SOM + ["--write"]))
        self.assertEqual(code, 0)
        self.assertIn("SOM: $24M a year within 3 years (2.5% of SAM $960M)", text)
        self.cli("cite", "--name", "US pet industry spend, 2025", "--value", "158B", "--source", APPA, "--write")
        self.cli("cite", "--name", "Share of US homes with a dog", "--value", "53", "--unit", "% of US homes",
                 "--source", APPA, "--write")
        d = self.doc()
        self.assertEqual((d["tam"], d["sam"], d["som"], d["currency"]), (17040000000, 960000000, 24000000, "USD"))
        self.assertEqual(d["method"], "top-down TAM, bottom-up SAM, SOM 2.5% of SAM in 3 years")
        self.assertEqual((d["som_share_pct"], d["som_years"]), (2.5, 3))
        self.assertTrue(d["som_reason"].startswith("Owners leaving Rover"))
        by = dict(((x["level"], x["name"]), x) for x in d["inputs"])
        self.assertEqual(by[("tam", "US homes with a dog")]["value"], 71000000)
        self.assertEqual(by[("tam", "US homes with a dog")]["kind"], "publication")
        self.assertEqual(by[("tam", "share that pays for dog walking")]["value"], 10)
        self.assertEqual(by[("tam", "share that pays for dog walking")]["kind"], "assumption")
        self.assertEqual(by[("sam", "price per walk")]["value"], 25)
        self.assertEqual(by[("context", "US pet industry spend, 2025")]["value"], 158000000000)
        for x in d["inputs"]:
            for k in ("name", "value", "unit", "source"):
                self.assertIn(k, x)
        code, text, _ = self.cli("show")
        self.assertEqual(code, 0)
        self.assertIn("Fact: US pet industry spend, 2025 = $158B", text)
        self.assertIn("Fact: Share of US homes with a dog = 53% of US homes", text)
        self.assertEqual(self.cli("check")[0], 0)
        # citing the same fact again replaces it
        self.cli("cite", "--name", "US pet industry spend, 2025", "--value", "158B", "--source", APPA, "--write")
        self.assertEqual(sum(1 for x in self.doc()["inputs"] if x["level"] == "context"), 2)

    def test_som_follows_sam_and_the_order_is_enforced(self):
        self.cli(*(TOP + ["--write"]))
        self.cli(*(BOTTOM + ["--write"]))
        self.cli(*(SOM + ["--write"]))
        b2 = list(BOTTOM)
        b2[b2.index("400K")] = "200K"
        code, text, _ = self.cli(*(b2 + ["--write"]))
        self.assertEqual(code, 0)
        self.assertIn("SOM recomputed from the new SAM: $12M", text)
        self.assertEqual((self.doc()["sam"], self.doc()["som"]), (480000000, 12000000))
        # a SAM bigger than the TAM is refused and the file stays as it was
        b3 = list(BOTTOM)
        b3[b3.index("400K")] = "8M"
        code, _, err = self.cli(*(b3 + ["--write"]))
        self.assertEqual(code, 1)
        self.assertIn("SAM $19.2B is bigger than TAM $17.04B", err)
        self.assertEqual(self.doc()["sam"], 480000000)
        code, text, _ = self.cli(*(b3 + ["--json"]))
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)["ok"])

    def test_refusals_and_exit_codes(self):
        code, _, err = self.cli(*SOM)
        self.assertEqual(code, 1)
        self.assertIn("size SAM first", err)
        self.cli(*(BOTTOM + ["--write"]))
        self.assertEqual(self.cli("som", "--share", "2%", "--years", "3", "--reason", "we are great")[0], 1)
        self.assertEqual(self.cli("som", "--share", "2%", "--years", "0", "--reason", SOM[-1])[0], 2)
        code, text, _ = self.cli("som", "--share", "20%", "--years", "3", "--reason", SOM[-1])
        self.assertEqual(code, 0)
        self.assertIn("is a lot: be ready to defend it", text)
        t = list(TOP)
        t[t.index(APPA)] = "google"
        code, _, err = self.cli(*(t + ["--write"]))
        self.assertEqual(code, 1)
        self.assertIn("needs a real source", err)
        t = list(TOP)
        t[t.index("10%")] = "150%"
        self.assertEqual(self.cli(*t)[0], 2)
        self.assertEqual(self.cli("top-down", "--population", "71M")[0], 2)     # argparse: missing flags
        self.assertEqual(run([])[0], 2)
        self.assertEqual(run(["show", "--dir", os.path.join(self.d, "none")])[0], 1)
        self.assertEqual(run(["check", "--dir", os.path.join(self.d, "none")])[0], 1)

    def test_rounding_half_up_to_the_dollar(self):
        code, text, _ = self.cli("top-down", "--population", "1", "--population-source", APPA, "--share", "50%",
                                 "--share-source", APPA, "--spend", "3", "--spend-source", APPA, "--json")
        self.assertEqual(json.loads(text)["market"]["tam"], 2)            # 1.5 -> 2
        code, text, _ = self.cli("bottom-up", "--customers", "3", "--customers-source", APPA, "--frequency", "1",
                                 "--frequency-source", APPA, "--price", "12.5", "--price-source", APPA, "--json")
        self.assertEqual(json.loads(text)["market"]["sam"], 38)           # 37.5 -> 38

    def test_check_reads_a_bad_file(self):
        os.makedirs(self.seed)
        shutil.copy(BAD, self.path)
        code, text, _ = self.cli("check")
        self.assertEqual(code, 1)
        self.assertIn("SAM $960M is bigger than TAM $500M", text)
        self.assertIn("SOM is not sized yet", text)
        self.assertIn("'google'", text)
        self.assertIn("'TBD'", text)
        code, text, _ = self.cli("check", "--json")
        self.assertEqual(len(json.loads(text)["problems"]), 4)
        code, text, _ = self.cli("show")
        self.assertEqual(code, 0)
        self.assertIn("Check: SAM $960M is bigger than TAM $500M", text)


if __name__ == "__main__":
    unittest.main()
