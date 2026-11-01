"""seed-scout tests. The fixtures in tests/fixtures/seed-scout/ are SYNTHETIC: two made-up apps
(Muttmile, Pawpost) with review texts written for these tests, shaped exactly like the iTunes
Search API, the Lookup API and the customer-reviews RSS (JSON) answered on Oct 26 2026."""

import gzip
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

scout = load("seed-scout", "scout")

DIR = os.path.join(FIX, "seed-scout")
MUTT, PAW = 1900000101, 1900000202


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = scout.main(argv)
    return code, out.getvalue(), err.getvalue()


def no_network(*a, **k):
    raise AssertionError("the tests must never touch the network")


def review(stars, title, text="", date="2026-10-01", rid="1"):
    return {"id": rid, "date": date, "updated": date + "T10:00:00-07:00", "stars": stars, "title": title, "text": text}


class Themes(unittest.TestCase):
    def setUp(self):
        self.rules = scout.load_rules()

    def test_keyword_rules_and_multi_theme_reviews(self):
        rows = [review(1, "Fees on fees", "and customer service never replied", rid="a"),
                review(2, "Nobody came", "The walker didn’t show up", rid="b"),       # curly apostrophe
                review(1, "They keep 25%", rid="c"),
                review(1, "Since the update", "I can’t log in", rid="d"),
                review(1, "Refund?", "charged twice", rid="e"),
                review(1, "Bad", "would not recommend", rid="f"),
                review(3, "Price is fine", "a fee but ok", rid="g"),                       # 3 stars: not low
                review(5, "Great price", rid="h")]
        st = scout.theme_counts(rows, self.rules)
        self.assertEqual(st["low"], 6)
        self.assertEqual(st["read"], 8)
        self.assertEqual(st["counts"], {"fees": 2, "cancellations": 1, "support": 1, "bugs": 1, "trust": 0,
                                        "payments": 1, "availability": 0})
        self.assertEqual(st["unthemed"], 1)
        st3 = scout.theme_counts(rows, self.rules, max_stars=3)
        self.assertEqual((st3["low"], st3["counts"]["fees"]), (7, 3))
        self.assertEqual(scout.theme_counts(rows, self.rules, max_stars=1)["low"], 5)

    def test_words_that_must_not_count(self):
        t = lambda text: scout.theme_counts([review(1, text)], self.rules)["counts"]
        self.assertEqual(t("I feel let down")["fees"], 0)            # "fee" inside "feel"
        self.assertEqual(t("The coffee was cold")["fees"], 0)
        self.assertEqual(t("Feedback ignored")["fees"], 0)
        self.assertEqual(t("Who is in charge here")["payments"], 0)  # "charge" is not "charged"
        self.assertEqual(t("Show me the map")["cancellations"], 0)
        self.assertEqual(t("No-show again")["cancellations"], 1)
        self.assertEqual(t("Stood me up")["cancellations"], 1)
        self.assertEqual(t("the 20% cut")["fees"], 1)

    def test_custom_rules_add_and_replace(self):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "rules.json")
            with open(path, "w") as fh:
                json.dump({"walker_pay": {"label": "walker pay", "patterns": [r"\bwalkers? (?:get|got|make) "]},
                           "fees": {"label": "fees only", "patterns": [r"\bfees?\b"]}}, fh)
            rules = scout.load_rules(path)
            keys = [k for k, _, _ in rules]
            self.assertEqual(keys[-1], "walker_pay")
            self.assertEqual(scout.label_of(rules, "fees"), "fees only")
            st = scout.theme_counts([review(1, "Walkers get almost nothing"), review(1, "Too expensive")], rules)
            self.assertEqual((st["counts"]["walker_pay"], st["counts"]["fees"]), (1, 0))
            with open(path, "w") as fh:
                json.dump({"x": {"patterns": ["(unclosed"]}}, fh)
            with self.assertRaises(scout.ScoutError):
                scout.load_rules(path)
            with open(path, "w") as fh:
                json.dump({"x": {"label": "no patterns"}}, fh)
            with self.assertRaises(scout.ScoutError):
                scout.load_rules(path)
        finally:
            shutil.rmtree(d)


class WeakPoint(unittest.TestCase):
    ORDER = [k for k, _, _ in scout.THEMES]

    def stats(self, low, **counts):
        c = dict((k, 0) for k in self.ORDER)
        c.update(counts)
        return {"low": low, "counts": c}

    def test_the_gap_rule_exactly(self):
        a = self.stats(24, fees=9, cancellations=3, support=5, bugs=3, trust=1, payments=3, availability=1)
        b = self.stats(20, fees=2, cancellations=8, support=9, bugs=1, trust=1, payments=2)
        (ka, ra, ga), (kb, rb, gb) = scout.weak_points([a, b], self.ORDER)
        self.assertEqual((ka, ra, ga), ("fees", "sets it apart", 27.5))          # 9/24 - 2/20 = 37.5 - 10
        self.assertEqual((kb, rb, gb), ("cancellations", "sets it apart", 27.5))  # 8/20 - 3/24 = 40 - 12.5
        # by count, b's weak point is the raw winner: support 9 beats cancellations 8
        self.assertEqual([w[0] for w in scout.weak_points([a, b], self.ORDER, by="count")], ["fees", "support"])
        # one app: the most mentioned
        self.assertEqual(scout.weak_points([b], self.ORDER), [("support", "most mentioned", None)])

    def test_a_tiny_theme_cannot_be_the_weak_point(self):
        # availability 1 of 40 (2.5%) has the biggest gap but is under 5%: it is skipped
        a = self.stats(40, fees=10, availability=1)
        b = self.stats(40, fees=12)
        self.assertEqual(scout.weak_points([a, b], self.ORDER)[0], ("fees", "most mentioned", None))
        a = self.stats(40, fees=10, availability=2)                             # 5%: it counts
        self.assertEqual(scout.weak_points([a, b], self.ORDER)[0], ("availability", "sets it apart", 5.0))

    def test_pooled_shares_with_three_apps(self):
        a = self.stats(10, fees=5)
        b = self.stats(20, fees=2, support=8)
        c = self.stats(30, fees=3, support=3)
        w = scout.weak_points([a, b, c], self.ORDER)
        self.assertEqual(w[0], ("fees", "sets it apart", 40.0))                 # 50% - 5 of 50 (10%)
        self.assertEqual(w[1], ("support", "sets it apart", 32.5))              # 40% - 3 of 40 (7.5%)
        self.assertEqual(w[2], ("fees", "most mentioned", None))               # nothing above the others: a tie
                                                                                # goes to the first theme

    def test_no_low_reviews(self):
        self.assertEqual(scout.weak_points([self.stats(0), self.stats(5, fees=1)], self.ORDER)[0][0], None)


class Feed(unittest.TestCase):
    def test_parse_feed_shapes(self):
        one = {"feed": {"entry": {"im:rating": {"label": "2"}, "id": {"label": "9"}, "title": {"label": "t"},
                                  "content": {"label": "c", "attributes": {"type": "text"}},
                                  "updated": {"label": "2026-10-02T08:00:00-07:00"}, "im:version": {"label": "1"},
                                  "im:voteSum": {"label": "-1"}}}}
        rows = scout.parse_feed(one)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["stars"], rows[0]["date"], rows[0]["votes"]), (2, "2026-10-02", -1))
        app_first = {"feed": {"entry": [{"im:name": {"label": "The app"}, "id": {"label": "1"}}] + [one["feed"]["entry"]]}}
        self.assertEqual(len(scout.parse_feed(app_first)), 1)     # older feeds put the app first
        self.assertEqual(scout.parse_feed({"feed": {}}), [])
        self.assertEqual(scout.parse_feed(None), [])

    def test_offline_pages_dedupe_and_stop(self):
        src = scout.Source(DIR)
        rows, read = scout.fetch_reviews(src, MUTT)
        self.assertEqual((len(rows), read), (30, 2))               # page 2 repeats one review of page 1
        self.assertEqual(len(set(r["id"] for r in rows)), 30)
        rows, read = scout.fetch_reviews(src, MUTT, pages=1)
        self.assertEqual((len(rows), read), (20, 1))
        for bad in (0, 11):
            with self.assertRaises(scout.ScoutError):
                scout.fetch_reviews(src, MUTT, pages=bad)

    def test_resolve_names_and_ids(self):
        src = scout.Source(DIR)
        self.assertEqual(scout.resolve(src, "Muttmile")[0], MUTT)   # the name match with the most ratings
        self.assertEqual(scout.resolve(src, "pawpost")[0], PAW)
        self.assertEqual(scout.resolve(src, "1900000202"), (PAW, None))
        self.assertEqual(scout.resolve(src, "id1900000202"), (PAW, None))
        with self.assertRaises(scout.ScoutError) as cm:
            scout.resolve(src, "Zebra")
        self.assertIn("1900000101", str(cm.exception))             # it lists the ids it did find

    def test_rounding_and_names(self):
        self.assertEqual(scout.rating1(4.88527), 4.9)
        self.assertEqual(scout.rating1(4.7641), 4.8)
        self.assertEqual(scout.rating1(4.75), 4.8)
        self.assertEqual(scout.rating1(4.25), 4.3)
        self.assertIsNone(scout.rating1(None))
        self.assertEqual(scout.short_name("Muttmile – Dog Walkers"), "Muttmile")
        self.assertEqual(scout.short_name("Pawpost - Pet Sitters & Walkers"), "Pawpost")
        self.assertEqual(scout.short_name("Solo"), "Solo")
        self.assertEqual(scout.nice_date("2026-10-04"), "Oct 4 2026")


class FakeResponse(object):
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Live(unittest.TestCase):
    """The live path, with urlopen faked: gzip bodies, a 400 past the last page, the User-Agent."""

    def setUp(self):
        self.real = scout.urllib.request.urlopen
        self.seen = []

    def tearDown(self):
        scout.urllib.request.urlopen = self.real

    def test_pages_until_the_feed_ends(self):
        with open(os.path.join(DIR, "rss-%d-1.json" % PAW), "rb") as fh:
            page1 = gzip.compress(fh.read())

        def fake(req, timeout=None):
            self.seen.append((req.full_url, req.get_header("User-agent"), timeout))
            if "page=1/" in req.full_url:
                return FakeResponse(page1)
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b""))

        scout.urllib.request.urlopen = fake
        rows, read = scout.fetch_reviews(scout.Source(pause=0), PAW)
        self.assertEqual((len(rows), read), (23, 1))
        self.assertEqual(self.seen[0][0], "https://itunes.apple.com/us/rss/customerreviews/page=1/id=%d/sortby=mostrecent/json" % PAW)
        self.assertIn("seed-skill", self.seen[0][1])
        self.assertEqual(self.seen[0][2], scout.TIMEOUT)
        self.assertEqual(len(self.seen), 2)

    def test_server_errors_are_reported(self):
        def fake(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 503, "Busy", {}, io.BytesIO(b""))
        scout.urllib.request.urlopen = fake
        with self.assertRaises(scout.ScoutError) as cm:
            scout.Source(pause=0).lookup(PAW)
        self.assertIn("HTTP 503", str(cm.exception))

        def down(req, timeout=None):
            raise urllib.error.URLError("no route")
        scout.urllib.request.urlopen = down
        code, _, err = run(["reviews", str(PAW)])
        self.assertEqual(code, 2)
        self.assertIn("could not reach the App Store", err)


class Cli(unittest.TestCase):
    def setUp(self):
        self.real = scout.urllib.request.urlopen
        scout.urllib.request.urlopen = no_network
        self.d = tempfile.mkdtemp()
        self.seed = os.path.join(self.d, "seed")

    def tearDown(self):
        scout.urllib.request.urlopen = self.real
        shutil.rmtree(self.d)

    def cli(self, *args):
        return run(list(args) + ["--dir", self.seed, "--today", "2026-10-26"])

    def test_find(self):
        code, text, _ = self.cli("find", "dog walking", "--offline", DIR)
        self.assertEqual(code, 0)
        self.assertIn("1900000101", text)
        self.assertIn("204,118", text)
        code, text, _ = self.cli("find", "dog walking", "--offline", DIR, "--json")
        apps = json.loads(text)["apps"]
        self.assertEqual([a["app_id"] for a in apps], [MUTT, 1900000303, PAW])
        self.assertEqual((apps[0]["name"], apps[0]["rating"]), ("Muttmile", 4.9))
        empty = os.path.join(self.d, "empty.json")
        with open(empty, "w") as fh:
            json.dump({"resultCount": 0, "results": []}, fh)
        self.assertEqual(self.cli("find", "nothing", "--offline", empty)[0], 1)

    def test_reviews_compare_pricing_show_round_trip(self):
        code, text, err = self.cli("reviews", "Muttmile", "--offline", DIR, "--write")
        self.assertEqual(code, 0, err)
        self.assertIn("read 30 reviews", text)
        self.assertIn("1-2 star reviews: 24 of 30", text)
        saved = os.path.join(self.seed, "reviews", "%d.json" % MUTT)
        with open(saved) as fh:
            doc = json.load(fh)
        self.assertEqual((doc["app_id"], doc["name"], doc["rating"], doc["ratings"]), (MUTT, "Muttmile", 4.9, 204118))
        self.assertEqual((len(doc["reviews"]), doc["pages"], doc["fetched"]), (30, 2, "2026-10-26"))
        self.assertNotIn("author", doc["reviews"][0])                 # no reviewer names are kept
        self.assertEqual(self.cli("reviews", str(PAW), "--offline", DIR, "--write")[0], 0)

        # compare reads the saved reviews: no --offline, and the network is off
        code, text, err = self.cli("compare", str(MUTT), str(PAW), "--write")
        self.assertEqual(code, 0, err)
        self.assertIn("fees and pricing", text)
        self.assertIn("9 of 24 (37.5%)", text)
        self.assertIn("8 of 20 (40.0%)", text)
        self.assertIn("Pawpost: the most mentioned is customer support (9 of 20)", text)
        with open(os.path.join(self.seed, "competitors.json")) as fh:
            comp = json.load(fh)
        self.assertEqual(comp["generated"], "2026-10-26")
        self.assertEqual(comp["weak_point_by"], "gap")
        m, p = comp["apps"]
        for k in ("name", "app_id", "rating", "ratings", "reviews_read", "low_reviews", "themes", "top_theme",
                  "weak_point", "examples", "source"):
            self.assertIn(k, m, k)
        self.assertEqual(m["themes"], {"fees": 9, "cancellations": 3, "support": 5, "bugs": 3, "trust": 1,
                                       "payments": 3, "availability": 1})
        self.assertEqual((m["top_theme"], m["weak_point"], m["weak_point_count"], m["low_reviews"], m["reviews_read"]),
                         ("fees", "fees and pricing", 9, 24, 30))
        self.assertEqual(m["weak_point_line"], "9 of 24 recent 1-2 star reviews mention fees and pricing")
        self.assertEqual(m["examples"], [{"title": "Fees on fees", "date": "2026-10-20", "stars": 1},
                                         {"title": "Too expensive now", "date": "2026-10-16", "stars": 1},
                                         {"title": "They keep 25%", "date": "2026-10-14", "stars": 2}])
        self.assertEqual((p["top_theme"], p["most_mentioned"], p["weak_point_share"], p["gap_points"]),
                         ("cancellations", "support", 40.0, 27.5))
        self.assertEqual((p["rating"], p["ratings"]), (4.8, 31007))
        self.assertTrue(m["source"].startswith("https://itunes.apple.com/us/rss/customerreviews/page=1/id=1900000101/"))

        code, _, err = self.cli("pricing", "Muttmile", "--note", "keeps 25% of each walk", "--source", "not a url")
        self.assertEqual(code, 1)
        self.assertIn("URL", err)
        code, text, _ = self.cli("pricing", "muttmile", "--note", "keeps 25% of each walk",
                                 "--source", "https://muttmile.example/help/fees", "--write")
        self.assertEqual(code, 0)
        self.assertEqual(self.cli("pricing", "Nobody", "--note", "x", "--source", "https://a.example/b")[0], 1)
        self.cli("compare", str(MUTT), str(PAW), "--write")            # a re-run keeps the pricing notes
        with open(os.path.join(self.seed, "competitors.json")) as fh:
            comp = json.load(fh)
        self.assertEqual(comp["apps"][0]["pricing"], [{"note": "keeps 25% of each walk",
                                                       "source": "https://muttmile.example/help/fees",
                                                       "read": "2026-10-26"}])
        code, text, _ = self.cli("show")
        self.assertEqual(code, 0)
        self.assertIn("Muttmile pricing: keeps 25% of each walk", text)

    def test_by_count_and_stars(self):
        code, text, _ = self.cli("compare", str(MUTT), str(PAW), "--offline", DIR, "--by", "count", "--json")
        doc = json.loads(text)
        self.assertEqual([a["top_theme"] for a in doc["apps"]], ["fees", "support"])
        self.assertEqual(doc["weak_point_by"], "count")
        code, text, _ = self.cli("themes", str(MUTT), "--offline", DIR, "--stars", "3", "--json")
        doc = json.loads(text)
        self.assertEqual((doc["low_reviews"], doc["themes"]["fees"], doc["themes"]["bugs"]), (25, 10, 4))
        code, text, _ = self.cli("themes", str(PAW), "--offline", DIR)
        self.assertEqual(code, 0)
        self.assertIn("customer support                   9 of 20     45.0%", text)
        self.assertIn("Most mentioned: customer support, 9 of 20 low reviews.", text)
        code, text, _ = self.cli("compare", str(MUTT), "--offline", DIR, "--json")     # one app: most mentioned
        self.assertEqual(json.loads(text)["apps"][0]["weak_point_rule"], "most mentioned")

    def test_refusals_and_exit_codes(self):
        self.assertEqual(self.cli("themes", str(MUTT), "--offline", DIR, "--stars", "5")[0], 2)
        self.assertEqual(self.cli("reviews", str(MUTT), "--offline", DIR, "--pages", "11")[0], 2)
        self.assertEqual(self.cli("compare", str(MUTT), str(MUTT), "--offline", DIR)[0], 2)
        self.assertEqual(self.cli("reviews", "1900000999", "--offline", DIR)[0], 1)     # no such app
        self.assertEqual(self.cli("show")[0], 1)
        code, _, err = run(["reviews", str(MUTT), "--offline", DIR, "--today", "26/10/2026"])
        self.assertEqual(code, 2)
        self.assertIn("YYYY-MM-DD", err)
        self.assertEqual(run([])[0], 2)
        self.assertEqual(run(["nope"])[0], 2)
        self.assertFalse(os.path.exists(self.seed))                      # nothing written without --write


if __name__ == "__main__":
    unittest.main()
