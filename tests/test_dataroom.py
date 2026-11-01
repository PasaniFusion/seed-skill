import calendar
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

room = load("seed-dataroom", "dataroom")
with open(os.path.join(FIX, "seed-dataroom", "room.json")) as fh:
    ROOM = json.load(fh)
TODAY = ROOM["today"]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = room.main(argv)
    return code, out.getvalue(), err.getvalue()


def noon_utc(day):
    y, m, d = (int(x) for x in day.split("-"))
    return calendar.timegm((y, m, d, 12, 0, 0))


class Room(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.root = os.path.join(self.d, "dataroom")

    def tearDown(self):
        shutil.rmtree(self.d)

    def build(self):
        self.assertEqual(run(["init", "--dir", self.d])[0], 0)
        for f in ROOM["files"]:
            p = os.path.join(self.root, *f["path"].split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(b"x" * f["bytes"])
            ts = noon_utc(f["modified"])
            os.utime(p, (ts, ts))

    def items(self, stage="all"):
        code, text, _ = run(["check", "--dir", self.d, "--today", TODAY, "--stage", stage, "--json"])
        return code, json.loads(text)

    def test_init_makes_the_nine_folders_and_is_safe_to_rerun(self):
        code, text, _ = run(["init", "--dir", self.d])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(os.listdir(self.root)), sorted(room.FOLDERS))
        self.assertEqual(room.FOLDERS[0], "01 Company")
        self.assertEqual(room.FOLDERS[-1], "09 Customers")
        keep = os.path.join(self.root, "02 Pitch deck", "deck.pdf")
        with open(keep, "w") as fh:
            fh.write("mine")
        code, text, _ = run(["init", "--dir", self.d])
        self.assertIn("nothing changed", text)
        self.assertTrue(os.path.exists(keep))

    def test_check_present_missing_stale(self):
        self.build()
        code, doc = self.items()
        self.assertEqual(code, 1)
        state = {i["key"]: i["state"] for i in doc["items"]}
        self.assertEqual(len(state), 25)
        self.assertEqual(state["deck"], "present")
        self.assertEqual(state["metrics"], "stale")        # dated 2026-06 in its name: 147 days, limit 45
        self.assertEqual(state["cap_table"], "stale")      # modified 2026-08-01: 86 days, limit 30
        self.assertEqual(state["incorporation"], "present")  # legal papers never go stale
        self.assertEqual(state["roadmap"], "missing")
        deck = [i for i in doc["items"] if i["key"] == "deck"][0]["files"][0]
        self.assertEqual((deck["date"], deck["dated_by"]), ("2026-10-24", "name"))
        self.assertEqual(doc["loose"], ["notes from the Northlight call.txt"])
        self.assertEqual([f["file"] for f in doc["flagged"]], [os.path.join("09 Customers", "customer list export.csv")])
        self.assertEqual([o["file"] for o in doc["other"]], [os.path.join("05 Product", "Brand colours.pdf")])

    def test_check_before_stage(self):
        self.build()
        code, text, _ = run(["check", "--dir", self.d, "--today", TODAY, "--stage", "before"])
        self.assertEqual(code, 1)
        self.assertIn("9 of 12 items present (before a term sheet)", text)
        self.assertIn("DO NOT SHARE: %s" % os.path.join("09 Customers", "customer list export.csv"), text)
        self.assertIn("3 to fix: Traction and KPIs stale; Product roadmap missing; Testimonials and reviews missing.",
                      text)

    def test_a_complete_fresh_stage_passes(self):
        run(["init", "--dir", self.d])
        for folder, key, label, stage, words, limit in room.CHECKLIST:
            if stage == "before":
                p = os.path.join(self.root, folder, "%s %s.pdf" % (words[0], TODAY))
                open(p, "w").close()
        self.assertEqual(self.items("before")[0], 0)
        self.assertEqual(self.items("after")[0], 1)

    def test_dates(self):
        self.assertEqual(str(room.name_date("Cap table 2026-10-01.xlsx")), "2026-10-01")
        self.assertEqual(str(room.name_date("metrics_20261015.pdf")), "2026-10-15")
        self.assertEqual(str(room.name_date("Metrics 2026-06.pdf")), "2026-06-01")
        self.assertIsNone(room.name_date("Founder bios.pdf"))
        self.assertIsNone(room.name_date("Plan 2026-13-40.pdf"))

    def test_never_share(self):
        for name in ("passwords.txt", "prod.env", "Casey passport scan.pdf", "api key.txt", "customer emails.csv"):
            self.assertIsNotNone(room.never_reason(name), name)
        for name in ("Pitch deck.pdf", "Waitlist counts by city.csv", "Cap table.xlsx"):
            self.assertIsNone(room.never_reason(name), name)

    def test_index(self):
        self.build()
        with open(os.path.join(self.d, "config.json"), "w") as fh:
            json.dump({"startup": {"name": "Leashly"}}, fh)
        code, text, _ = run(["index", "--dir", self.d, "--today", TODAY])
        self.assertEqual(code, 0)
        self.assertIn("16 files in 9 folders, 11 checklist items missing, 2 out of date", text)
        with open(os.path.join(self.root, "INDEX.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertTrue(md.startswith("# Leashly data room\n"))
        self.assertIn("| Leashly pitch deck 2026-10-24.pdf | Pitch deck (PDF) | 2026-10-24 | 5.0 KB | before |", md)
        self.assertIn("| Cap table.xlsx | Cap table (fully diluted) | 2026-08-01 | 900 B | after |", md)
        self.assertIn("| Brand colours.pdf | Other | 2026-10-01 | 300 B | ask first |", md)
        self.assertNotIn("customer list export", md)
        self.assertIn("Missing: Product roadmap.", md)
        # running it again does not index INDEX.md itself
        run(["index", "--dir", self.d, "--today", TODAY])
        with open(os.path.join(self.root, "INDEX.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), md)

    def test_share_list(self):
        self.build()
        code, text, _ = run(["share-list", "--dir", self.d, "--today", TODAY, "--json"])
        doc = json.loads(text)
        before = {r["label"]: r for r in doc["before"]["share"]}
        self.assertIn("Pitch deck (PDF)", before)
        self.assertEqual(before["Traction and KPIs"]["state"], "stale")
        self.assertNotIn("Cap table (fully diluted)", before)
        self.assertIn("Cap table (fully diluted)", [r["label"] for r in doc["after"]["share"]])
        self.assertEqual(doc["before"]["missing"], ["Product roadmap", "Testimonials and reviews"])
        code, text, _ = run(["share-list", "--dir", self.d, "--today", TODAY, "--stage", "before"])
        self.assertIn("This tool shares nothing", text)
        self.assertNotIn("AFTER a signed term sheet", text)

    def test_errors(self):
        for argv in (["check", "--dir", self.d], ["check", "--dir", self.d, "--today", "10/26/2026"], []):
            code, _, err = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertNotIn("Traceback", err)
