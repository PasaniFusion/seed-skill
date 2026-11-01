"""seed-investors tests. Everything here is SYNTHETIC: the investors are the reel's made-up ones
(seed-investors/investors.example.csv, .example domains), and tests/fixtures/seed-investors/ holds
made-up EDGAR answers (issuers with CIKs 0009990001-4, far above any real CIK, and made-up people)
shaped like efts.sec.gov full-text search hits and Form D primary_doc.xml (schema X0708)."""

import csv
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX, ROOT

inv = load("seed-investors", "investors")

EDGAR = os.path.join(FIX, "seed-investors")
EXAMPLE = os.path.join(ROOT, "seed-investors", "investors.example.csv")
TODAY = inv.datetime.date(2026, 10, 26)
LEASHLY = ["--stage", "seed", "--sectors", "pet care; marketplaces; local services; consumer", "--geo", "US",
           "--ask", "1.5M", "--today", "2026-10-26"]
REEL_FITS = [("maya-chen", 96), ("daniel-okafor", 93), ("priya-raman", 91), ("sam-whitaker", 89),
             ("elena-brooks", 87), ("marcus-lee", 85)]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = inv.main(argv)
    return code, out.getvalue(), err.getvalue()


def no_network(*a, **k):
    raise AssertionError("the tests must never touch the network")


def crit(**k):
    c = {"stage": "seed", "sectors": ["pet care", "marketplaces", "local services", "consumer"], "geo": ["US"],
         "check": {"min": 75000, "max": 750000}}
    c.update(k)
    return c


def row(**k):
    r = {"name": "Test Person", "firm": "Test Fund", "stage": ["seed"], "check_min": 250000, "check_max": 1000000,
         "sectors": ["pet care", "marketplaces"], "geo": ["US"], "sources": ["https://fund.example/team"],
         "last_relevant_deal": {"what": "a deal", "date": "2026-10-26"}, "warm_intro": False}
    r.update(k)
    return r


class Parsing(unittest.TestCase):
    def test_money(self):
        for text, n in (("$250K", 250000), ("1M", 1000000), ("1.5m", 1500000), ("1,500,000", 1500000),
                        ("$2.5MM", 2500000), (750000, 750000), ("1b", 10 ** 9)):
            self.assertEqual(inv.money(text), n, text)
        self.assertEqual(inv.money_range("250K-1M"), (250000, 1000000))
        self.assertEqual(inv.money_range("$250K – $1M"), (250000, 1000000))
        self.assertEqual(inv.money_range("$100K to $500K"), (100000, 500000))
        self.assertEqual(inv.money_range("$50K"), (50000, 50000))
        for bad in ("lots", "1M-250K", "0", "-5"):
            with self.assertRaises(inv.InvError):
                inv.money_range(bad)
        self.assertEqual((inv.short_money(250000), inv.short_money(1500000), inv.short_money(1000000),
                          inv.short_money(25000), inv.short_money(12500)), ("$250K", "$1.5M", "$1M", "$25K", "$12.5K"))

    def test_stages_sectors_geo(self):
        self.assertEqual([inv.norm_stage(s) for s in ("Pre-Seed", "preseed", "Seed", "Series A", "a", "growth")],
                         ["pre-seed", "pre-seed", "seed", "series a", "series a", "growth"])
        with self.assertRaises(inv.InvError):
            inv.norm_stage("mezzanine")
        ours = ["pet care", "marketplaces", "local services", "consumer"]
        self.assertEqual(inv.sector_match(ours, ["Pet Care", "Consumer Marketplaces"]), ["pet care", "marketplaces", "consumer"])
        self.assertEqual(inv.sector_match(ours, ["Pets"]), ["pet care"])  # plural and singular match
        self.assertEqual(inv.sector_match(ours, ["carpet cleaning"]), [])   # "pet" inside a word is not a match
        self.assertEqual(inv.sector_match(ours, ["fintech"]), [])
        self.assertEqual(inv.sector_match(["pet care"], ["pet"]), ["pet care"])
        self.assertTrue(inv.geo_match(["US"], ["United States"])[0])
        self.assertTrue(inv.geo_match(["New York, US"], ["US"])[0])
        self.assertTrue(inv.geo_match(["US"], ["Global"])[0])
        self.assertFalse(inv.geo_match(["New York"], ["New Zealand"])[0])   # "new" alone is not a match
        self.assertFalse(inv.geo_match(["US"], ["Europe"])[0])
        self.assertEqual(inv.split_urls("https://a.example/x https://b.example/y; https://c.example/z"),
                         ["https://a.example/x", "https://b.example/y", "https://c.example/z"])


class Fit(unittest.TestCase):
    def test_every_part_of_the_score(self):
        fit, why = inv.score(row(), crit(), 1500000, TODAY)
        self.assertEqual(fit, 25 + 25 + 20 + 15 + 10)
        self.assertEqual(why[0], "invests at seed (+25)")
        self.assertEqual(inv.score(row(warm_intro=True), crit(), 1500000, TODAY)[0], 100)
        self.assertEqual(inv.score(row(stage=["pre-seed"]), crit(), 1500000, TODAY)[0], 95 - 13)       # one stage off: 12
        self.assertEqual(inv.score(row(stage=["series b"]), crit(), 1500000, TODAY)[0], 95 - 25)
        self.assertEqual(inv.score(row(stage=[]), crit(), 1500000, TODAY)[0], 95 - 25)
        self.assertEqual(inv.score(row(sectors=["pet care"]), crit(), 1500000, TODAY)[0], 95 - 10)     # one match: 15
        self.assertEqual(inv.score(row(sectors=["fintech"]), crit(), 1500000, TODAY)[0], 95 - 25)
        self.assertEqual(inv.score(row(geo=["Europe"]), crit(), 1500000, TODAY)[0], 95 - 10)
        self.assertEqual(inv.score(row(last_relevant_deal=None), crit(), 1500000, TODAY)[0], 95 - 15)

    def test_check_size(self):
        s = lambda lo, hi: inv.score(row(check_min=lo, check_max=hi), crit(), 1500000, TODAY)
        self.assertEqual(s(750000, 2000000)[0], 95)                     # touches the top of the range
        self.assertEqual(s(25000, 50000)[0], 85)                         # within a factor of 2 of $75K
        self.assertIn("close to", s(25000, 50000)[1][2])
        self.assertEqual(s(5000, 25000)[0], 75)                          # far under
        self.assertEqual(s(1000000, 3000000)[0], 85)                     # $1M is within 2x of $750K
        fit, why = s(2000000, 10000000)
        self.assertEqual(fit, 75)
        self.assertIn("bigger than your whole $1.5M round", why[2])
        self.assertEqual(s(None, None)[0], 75)

    def test_recency_exact(self):
        self.assertEqual([inv.recency_points(d) for d in (0, 1, 24, 25, 120, 196, 200, 290, 390, 480, 705, 706, 730, 900)],
                         [15, 15, 15, 14, 13, 11, 11, 9, 7, 5, 1, 0, 0, 0])
        self.assertEqual(inv.recency_points(-3), 15)                     # a deal "after" --today counts as today

    def test_no_source_is_refused_and_never_ranked(self):
        fit, why = inv.score(row(sources=[]), crit(), 1500000, TODAY)
        self.assertIsNone(fit)
        self.assertIn("no public source", why[0])
        self.assertIsNone(inv.score(row(sources=["see notes"]), crit(), 1500000, TODAY)[0])
        hand = row(stage="seed", sectors="pet care; marketplaces", geo="US", sources="https://fund.example/x")
        self.assertEqual(inv.score(hand, crit(), 1500000, TODAY)[0], 95)  # strings from a hand edit still work


class Rows(unittest.TestCase):
    def clean(self, **k):
        r = {"name": "Ada Example", "firm": "Fund", "sources": "https://fund.example/ada", "personal_line": "Hi"}
        r.update(k)
        return inv.clean_row(r, TODAY)

    def test_refusals(self):
        for bad, why in (({"sources": ""}, "no source"),
                         ({"sources": "linkedin"}, "public URL"),
                         ({"name": ""}, "no name"),
                         ({"email": "not-an-email"}, "not an email"),
                         ({"notes": "call her on 415-555-0123"}, "phone number"),
                         ({"notes": "+1 (415) 555 0123"}, "phone number"),
                         ({"last_deal": "led a round", "last_deal_date": "2027-01-01"}, "in the future")):
            with self.assertRaises(inv.InvError) as cm:
                self.clean(**bad)
            self.assertIn(why, str(cm.exception), bad)
        with self.assertRaises(inv.InvError):
            self.clean(last_deal="led a round")                         # a deal needs its date
        with self.assertRaises(inv.InvError):
            self.clean(stage="mezzanine")

    def test_private_columns_are_dropped_and_dates_kept(self):
        r, warns = self.clean(phone="415 555 0100", home_address="1 Home Street", cell="", city_home="x",
                              last_deal="led a seed round", last_deal_date="2026-04",
                              notes="met at the 2026-04-13 demo day, $1,500,000 fund")
        self.assertNotIn("phone", r)
        self.assertNotIn("home_address", r)
        self.assertTrue(any("'phone' column" in w for w in warns))
        self.assertTrue(any("'home_address' column" in w for w in warns))
        self.assertTrue(any("unknown column 'city_home'" in w for w in warns))
        self.assertEqual(r["last_relevant_deal"], {"what": "led a seed round", "date": "2026-04-01"})
        r, warns = self.clean(email_address="ada@fund.example", check_size="$100K-$400K", sector="pet care")
        self.assertEqual((r["email"], r["check_min"], r["check_max"], r["sectors"]),
                         ("ada@fund.example", 100000, 400000, ["pet care"]))
        r, warns = self.clean(email="ada" + "@" + "gmail.com")
        self.assertTrue(any("personal-style address" in w for w in warns))
        r, warns = self.clean(personal_line="")
        self.assertTrue(any("no personal_line" in w for w in warns))

    def test_merge_updates_instead_of_duplicating(self):
        book = {"investors": []}
        a, _ = inv.clean_row({"name": "Ada Example", "firm": "Fund", "sources": "https://a.example/1"}, TODAY)
        self.assertEqual(inv.merge(book, a, TODAY)[0], "added")
        b, _ = inv.clean_row({"name": "ada example", "firm": "FUND", "sources": "https://a.example/2",
                              "email": "ada@fund.example"}, TODAY)
        how, x = inv.merge(book, b, TODAY)
        self.assertEqual((how, len(book["investors"])), ("updated", 1))
        self.assertEqual(x["sources"], ["https://a.example/1", "https://a.example/2"])
        self.assertEqual(x["email"], "ada@fund.example")
        c, _ = inv.clean_row({"name": "Ada Example", "firm": "Other Fund", "sources": "https://o.example/1"}, TODAY)
        how, x = inv.merge(book, c, TODAY)
        self.assertEqual((how, x["id"]), ("added", "ada-example-2"))


class FormD(unittest.TestCase):
    def setUp(self):
        self.page = inv.PAGE
        inv.PAGE = 3                       # the fixtures hold two pages of 3; the real page is 100
        self.real = inv.urllib.request.urlopen
        inv.urllib.request.urlopen = no_network

    def tearDown(self):
        inv.PAGE = self.page
        inv.urllib.request.urlopen = self.real

    def test_search_pages_details_and_dedupe(self):
        sec = inv.Sec(offline=EDGAR)
        filings, total = inv.collect(sec, "pet care", "2025-01-01", "2026-10-26", 40)
        self.assertEqual(total, 6)
        self.assertEqual([f["adsh"] for f in filings], ["0009990004-26-000002", "0009990001-26-000001",
                                                        "0009990003-25-000004", "0009990002-25-000007",
                                                        "0009990001-25-000003"])      # newest first, one per filing
        s, a, fund, nodoc, d = filings
        self.assertEqual((s["company"], s["amount_sold"], s["amount_offered"], s["investors_count"]),
                         ("Snoutwell Inc.", 900000, 1500000, 11))
        self.assertEqual(s["securities"], ["Simple Agreement for Future Equity"])
        self.assertEqual(s["url"], "https://www.sec.gov/Archives/edgar/data/9990004/000999000426000002/"
                                   "0009990004-26-000002-index.htm")
        self.assertEqual(s["doc_url"], "https://www.sec.gov/Archives/edgar/data/9990004/000999000426000002/primary_doc.xml")
        self.assertEqual((s["first_sale"], s["location"], s["city"], s["state"]), ("2026-07-15", "Austin, TX", "Austin", "TX"))
        self.assertEqual(inv.leads_of(s), ["Riley Samplewood"])         # a director who is not an officer
        self.assertTrue(a["amendment"])
        self.assertEqual((fund["amount_offered"], fund["fund_type"], fund["industry"]),
                         ("indefinite", "Venture Capital Fund", "Pooled Investment Fund"))   # namespaced XML
        self.assertNotIn("amount_sold", nodoc)                            # its document is missing: no guess
        self.assertEqual(inv.summarise(filings), {"filings": 5, "companies": 4, "with_amounts": 4,
                                                  "median_sold": 2250000, "total_sold": 17400000})
        text = json.dumps(filings)
        self.assertNotIn("Example Street", text)                          # addresses are never kept
        self.assertNotIn("555-010", text)
        filings, _ = inv.collect(sec, "pet care", "2025-01-01", "2026-10-26", 40, amendments=False)
        self.assertEqual(len(filings), 4)
        filings, _ = inv.collect(sec, "pet care", "2025-01-01", "2026-10-26", 2, details=False)
        self.assertEqual([f["company"] for f in filings], ["Snoutwell Inc.", "Pawtrail Labs, Inc."])
        self.assertNotIn("amount_sold", filings[0])

    def test_the_url_and_the_user_agent(self):
        u = inv.efts_url("pet care", "2025-01-01", "2026-10-26", 0)
        self.assertEqual(u, "https://efts.sec.gov/LATEST/search-index?q=%22pet+care%22&dateRange=custom"
                            "&startdt=2025-01-01&enddt=2026-10-26&forms=D")
        self.assertIn("q=pet&", inv.efts_url("pet", "2025-01-01", "2026-10-26", 0))
        self.assertIn("&from=100", inv.efts_url("pet", "2025-01-01", "2026-10-26", 100))
        self.assertEqual(inv.company_of("Pawtrail Labs, Inc.  (CIK 0009990001)"), "Pawtrail Labs, Inc.")
        d = tempfile.mkdtemp()
        old = os.environ.pop("SEC_USER_AGENT", None)
        try:
            with self.assertRaises(inv.InvError) as cm:
                inv.sec_user_agent(None, d)
            self.assertIn("say who is asking", str(cm.exception))
            for bad in ("Your Name you@example.com", "ada@leashly.co", "Leashly ops@leashly.example", "Ada Lovelace",
                        "Ada name@leashly.co"):
                with self.assertRaises(inv.InvError):
                    inv.sec_user_agent(bad, d)
            self.assertEqual(inv.sec_user_agent("Ada Lovelace ada@leashly.co", d), "Ada Lovelace ada@leashly.co")
            os.environ["SEC_USER_AGENT"] = "Grace Hopper grace@leashly.co"
            self.assertEqual(inv.sec_user_agent(None, d), "Grace Hopper grace@leashly.co")
            del os.environ["SEC_USER_AGENT"]
            with open(os.path.join(d, "config.json"), "w") as fh:
                json.dump({"sec_user_agent": "Alan Turing alan@leashly.co"}, fh)
            self.assertEqual(inv.sec_user_agent(None, d), "Alan Turing alan@leashly.co")
        finally:
            shutil.rmtree(d)
            if old is not None:
                os.environ["SEC_USER_AGENT"] = old

    def test_live_requests_carry_the_user_agent(self):
        seen = []
        with open(os.path.join(EDGAR, "efts-0.json"), "rb") as fh:
            body = fh.read()

        class R(object):
            def __init__(self, b):
                self.b = b

            def read(self):
                return self.b

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=None):
            seen.append((req.full_url, req.get_header("User-agent")))
            if "efts" in req.full_url:
                return R(inv.gzip.compress(body))
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b""))

        inv.urllib.request.urlopen = fake
        inv.PAGE = 100
        filings, total = inv.collect(inv.Sec("Ada Lovelace ada@leashly.co", pause=0), "pet", "2025-01-01",
                                     "2026-10-26", 40)
        self.assertEqual(len(filings), 3)
        self.assertTrue(all(ua == "Ada Lovelace ada@leashly.co" for _, ua in seen))
        self.assertEqual(len(seen), 4)                                     # one search page + three documents

        def refused(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b""))
        inv.urllib.request.urlopen = refused
        with self.assertRaises(inv.InvError) as cm:
            inv.collect(inv.Sec("Ada Lovelace ada@leashly.co", pause=0), "pet", "2025-01-01", "2026-10-26", 5)
        self.assertIn("HTTP 403", str(cm.exception))


class Cli(unittest.TestCase):
    def setUp(self):
        self.real = inv.urllib.request.urlopen
        inv.urllib.request.urlopen = no_network
        self.d = tempfile.mkdtemp()
        self.seed = os.path.join(self.d, "seed")
        self.old_ua = os.environ.pop("SEC_USER_AGENT", None)

    def tearDown(self):
        inv.urllib.request.urlopen = self.real
        shutil.rmtree(self.d)
        if self.old_ua is not None:
            os.environ["SEC_USER_AGENT"] = self.old_ua

    def cli(self, *args):
        return run(list(args) + ["--dir", self.seed])

    def book(self):
        with open(os.path.join(self.seed, "investors.json")) as fh:
            return json.load(fh)

    def test_the_reel_six_import_rank_show(self):
        code, text, err = self.cli("import", EXAMPLE, "--today", "2026-10-26")
        self.assertEqual(code, 0, text + err)
        self.assertIn("Wrote", text)
        self.assertEqual(len(self.book()["investors"]), 6)
        code, text, _ = self.cli("rank", *LEASHLY)
        self.assertEqual(code, 0)
        self.assertIn("Not saved", text)
        self.assertIsNone(self.book()["investors"][0]["fit"])              # rank wrote nothing without --write
        code, text, _ = self.cli("rank", "--write", *LEASHLY)
        b = self.book()
        self.assertEqual([(x["id"], x["fit"]) for x in b["investors"]], REEL_FITS)
        self.assertEqual(b["ask"], 1500000)
        self.assertEqual(b["criteria"], crit())
        self.assertEqual(b["generated"], "2026-10-26")
        maya = b["investors"][0]
        for k in ("id", "name", "firm", "role", "email", "stage", "check_min", "check_max", "sectors", "geo",
                  "last_relevant_deal", "sources", "fit", "reasons", "personal_line"):
            self.assertIn(k, maya, k)
        self.assertEqual((maya["email"], maya["check_min"], maya["check_max"]), ("maya@northlight.example", 250000, 1000000))
        self.assertEqual(maya["reasons"], [
            "invests at seed (+25)", "sectors match: pet care, marketplaces, consumer (+25)",
            "checks of $250K-$1M fit the $75K-$750K you want (+20)",
            "led the second of her two pet-care seed rounds, 196 days ago (+11)", "invests in US (+10)",
            "warm intro available (+5)"])
        self.assertTrue(maya["personal_line"].startswith("Saw you led two pet-care seed rounds"))
        # a second rank reuses the saved criteria: no flags needed
        code, text, _ = self.cli("rank", "--today", "2026-10-26", "--json")
        self.assertEqual([x["fit"] for x in json.loads(text)["investors"]], [f for _, f in REEL_FITS])
        code, text, _ = self.cli("show")
        self.assertEqual(code, 0)
        self.assertIn("96  Maya Chen", text)
        code, text, _ = self.cli("show", "maya-chen")
        self.assertIn("source    https://northlight.example/team/maya-chen", text)
        self.assertEqual(self.cli("show", "nobody")[0], 1)
        # the same file again updates, never duplicates
        self.cli("import", EXAMPLE, "--today", "2026-10-26")
        self.assertEqual(len(self.book()["investors"]), 6)

    def test_criteria_from_config(self):
        os.makedirs(self.seed)
        with open(os.path.join(self.seed, "config.json"), "w") as fh:
            json.dump({"startup": {"name": "Leashly", "stage": "seed", "sector": "pet care, marketplaces, local services, consumer",
                                   "geography": "US", "raise": 1500000}}, fh)
        self.cli("import", EXAMPLE, "--today", "2026-10-26")
        code, text, _ = self.cli("rank", "--today", "2026-10-26", "--json")
        self.assertEqual(code, 0)
        self.assertEqual([x["fit"] for x in json.loads(text)["investors"]], [f for _, f in REEL_FITS])
        code, text, _ = self.cli("rank", "--today", "2026-10-26", "--check", "25K-100K", "--json")
        self.assertEqual(json.loads(text)["criteria"]["check"], {"min": 25000, "max": 100000})

    def test_add_and_refusals(self):
        code, text, _ = self.cli("add", "--name", "Ada Example", "--firm", "Fund", "--stage", "seed",
                                 "--check", "100K-500K", "--sectors", "pet care; consumer", "--geo", "US",
                                 "--source", "https://fund.example/ada", "--source", "https://press.example/ada",
                                 "--last-deal", "led a seed round", "--last-deal-date", "2026-09-26",
                                 "--personal-line", "Your note on pet care stuck with me.", "--today", "2026-10-26")
        self.assertEqual(code, 0)
        self.assertEqual(self.book()["investors"][0]["sources"], ["https://fund.example/ada", "https://press.example/ada"])
        code, text, _ = self.cli("add", "--name", "No Source", "--firm", "Fund", "--today", "2026-10-26")
        self.assertEqual(code, 1)
        self.assertIn("Refused: --name (No Source) has no source", text)
        self.assertEqual(len(self.book()["investors"]), 1)
        # a hand-edited row without a source is refused by rank, and kept out of the ranked list
        b = self.book()
        b["investors"].append(row(id="hand", name="Hand Edit", sources=[]))
        with open(os.path.join(self.seed, "investors.json"), "w") as fh:
            json.dump(b, fh)
        code, text, _ = self.cli("rank", "--write", *LEASHLY)
        self.assertEqual(code, 0)
        self.assertIn("Refused: Hand Edit (hand)", text)
        b = self.book()
        self.assertEqual([x["fit"] for x in b["investors"]], [94, None])   # 25 + 25 + 20 + 14 (30 days ago) + 10
        # a CSV with a phone number and a private column
        path = os.path.join(self.d, "rows.csv")
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["name", "firm", "sources", "phone", "notes"])
            w.writerow(["Bea Example", "Fund B", "https://b.example/bea", "415 555 0100", ""])
            w.writerow(["Cal Example", "Fund C", "https://c.example/cal", "", "cell 415.555.0199"])
        code, text, _ = self.cli("import", path, "--today", "2026-10-26")
        self.assertEqual(code, 1)                                          # one row refused
        self.assertIn("dropped the 'phone' column", text)
        self.assertIn("Refused: row 3 (Cal Example)", text)
        names = [x["name"] for x in self.book()["investors"]]
        self.assertIn("Bea Example", names)
        self.assertNotIn("Cal Example", names)
        self.assertNotIn("415", json.dumps(self.book()))

    def test_formd_cli_and_exit_codes(self):
        code, _, err = self.cli("formd", "--q", "pet care", "--since", "2025-01-01")
        self.assertEqual(code, 1)
        self.assertIn("say who is asking", err)                            # refused before any request
        page = inv.PAGE
        inv.PAGE = 3
        try:
            code, text, _ = self.cli("formd", "--q", "pet care", "--since", "2025-01-01", "--offline", EDGAR,
                                     "--today", "2026-10-26", "--write")
        finally:
            inv.PAGE = page
        self.assertEqual(code, 0)
        self.assertIn("5 filings from 4 companies. Amount sold: median $2,250,000, total $17,400,000", text)
        self.assertIn("Riley Samplewood", text)
        self.assertIn("a venture capital fund raising money", text)
        with open(os.path.join(self.seed, "formd.json")) as fh:
            doc = json.load(fh)
        self.assertEqual((doc["query"], doc["since"], doc["until"], doc["total_hits"]), ("pet care", "2025-01-01", "2026-10-26", 6))
        empty = os.path.join(self.d, "empty")
        os.makedirs(empty)
        self.assertEqual(self.cli("formd", "--q", "pet", "--since", "2025-01-01", "--offline", empty)[0], 1)
        self.assertEqual(self.cli("formd", "--q", "pet", "--since", "2025-13-01", "--offline", empty)[0], 2)
        self.assertEqual(self.cli("formd", "--q", "pet", "--since", "2026-01-01", "--until", "2025-01-01",
                                  "--offline", empty)[0], 2)
        self.assertEqual(self.cli("rank")[0], 1)                            # nobody to rank yet
        self.assertEqual(self.cli("show")[0], 1)
        self.assertEqual(run([])[0], 2)
        self.cli("import", EXAMPLE, "--today", "2026-10-26")
        code, _, err = self.cli("rank", "--today", "2026-10-26")            # no stage, sectors, geo or ask anywhere
        self.assertEqual(code, 2)
        self.assertIn("rank needs your stage", err)


if __name__ == "__main__":
    unittest.main()
