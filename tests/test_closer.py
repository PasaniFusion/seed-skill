import datetime
import email
import email.policy
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

closer = load("seed-closer", "closer")
F = os.path.join(FIX, "seed-closer")
D = datetime.date
RULES = closer.outreach_rules({})
MAYA_LINE = "Saw you led two pet-care seed rounds, so you know the 20% fee problem better than anyone."


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = closer.main(argv)
    return code, out.getvalue(), err.getvalue()


def investors():
    with open(os.path.join(F, "investors.json")) as fh:
        return {r["id"]: r for r in json.load(fh)["investors"]}


class BusinessDays(unittest.TestCase):
    def test_plus_three_and_seven_from_monday(self):
        self.assertEqual(closer.add_days(D(2026, 10, 26), 3, RULES), D(2026, 10, 29))
        self.assertEqual(closer.add_days(D(2026, 10, 26), 7, RULES), D(2026, 11, 4))

    def test_weekends_and_holidays_are_skipped(self):
        self.assertEqual(closer.add_days(D(2026, 10, 30), 1, RULES), D(2026, 11, 2))
        self.assertEqual(closer.add_days(D(2026, 10, 31), 1, RULES), D(2026, 11, 2))
        hol = closer.outreach_rules({"outreach": {"holidays": ["2026-11-26"]}})
        self.assertEqual(closer.add_days(D(2026, 11, 25), 1, hol), D(2026, 11, 27))
        self.assertEqual(closer.next_workday(D(2026, 11, 1), RULES), D(2026, 11, 2))

    def test_calendar_days_when_business_days_is_off(self):
        cal = closer.outreach_rules({"outreach": {"business_days": False}})
        self.assertEqual(closer.add_days(D(2026, 10, 26), 7, cal), D(2026, 11, 2))
        self.assertTrue(closer.is_workday(D(2026, 10, 31), cal))

    def test_config_limits(self):
        for bad in ({"daily_cap": 51}, {"daily_cap": 0}, {"daily_cap": True}, {"max_touches": 4},
                    {"followup_days": [7, 3]}, {"followup_days": [0, 3]}, {"holidays": ["Nov 26"]}):
            with self.assertRaises(closer.CloserError, msg=str(bad)):
                closer.outreach_rules({"outreach": bad})
        two = closer.outreach_rules({"outreach": {"max_touches": 2}})
        self.assertEqual((two["followup_days"], two["max_touches"]), ([3], 2))

    def test_next_due_spacing_hold_and_stops(self):
        rec = {"status": "sent", "touches": [{"from": "us", "kind": "intro", "date": "2026-10-26"}]}
        self.assertEqual(closer.next_due(rec, RULES), D(2026, 10, 29))
        rec["touches"].append({"from": "us", "kind": "followup", "date": "2026-11-02"})   # sent late
        self.assertEqual(closer.next_due(rec, RULES), D(2026, 11, 6))   # keeps the 4-day gap, not Nov 4
        rec["touches"].append({"from": "us", "kind": "followup", "date": "2026-11-06"})
        self.assertIsNone(closer.next_due(rec, RULES))                  # three touches
        held = {"status": "sent", "touches": rec["touches"][:1], "hold_until": "2026-11-09"}
        self.assertEqual(closer.next_due(held, RULES), D(2026, 11, 10))
        replied = {"status": "replied", "touches": rec["touches"][:1] + [{"from": "them", "kind": "reply"}]}
        self.assertIsNone(closer.next_due(replied, RULES))


class PersonalLine(unittest.TestCase):
    def test_the_reel_lines_pass(self):
        for rid, inv in investors().items():
            ok, why = closer.check_personal_line(inv["personal_line"], inv, "Leashly")
            self.assertTrue(ok, "%s: %s" % (rid, why))

    def test_generic_and_broken_lines_are_refused(self):
        inv = {"name": "Marcus Lee", "firm": "Copperline VC", "sectors": ["seed consumer"]}
        for line in ("", "I hope this email finds you well and wanted to reach out about Leashly.",
                     "I love what you're doing at Copperline VC and wanted to connect.",
                     "I'm a big fan of your work and your incredible portfolio of companies.",
                     "I came across your profile and thought Leashly would be a fit.",
                     "You are a great investor and I think you'd love what we are building.",
                     "Saw you led two pet-care seed rounds and...",
                     "Saw you led two pet-care seed rounds…",
                     "{personal_line} goes here for this investor today",
                     "TODO write something specific about this person",
                     "Great fund.",
                     "We think our company would make sense for your firm right now."):
            ok, _ = closer.check_personal_line(line, inv, "Leashly")
            self.assertFalse(ok, line)

    def test_the_firm_name_is_not_personal(self):
        inv = {"name": "Marcus Lee", "firm": "Copperline VC"}
        ok, why = closer.check_personal_line("We would really be glad to have Copperline join this round soon.",
                                             inv, "Leashly")
        self.assertFalse(ok, why)


class Yes(unittest.TestCase):
    ITEMS = [{"name": "Maya Chen", "firm": "Northlight Ventures"}, {"name": "Daniel Okafor", "firm": "Harbor Seed Fund"}]

    def test_a_clear_yes(self):
        for r in ("yes", "Yes.", "y", "yes, send them", "Yes please send all 2", "yes send both", "yes, two"):
            self.assertTrue(closer.parse_batch_yes(r, self.ITEMS)[0], r)

    def test_anything_else(self):
        for r in ("", "sure", "ok", "go ahead", "send it", "yes?", "no", "yes but wait", "yes except Maya",
                  "yes to Daniel", "yes tomorrow", "yes send 3", "yes, after lunch", "yes if it is short",
                  "yes Northlight only"):
            self.assertFalse(closer.parse_batch_yes(r, self.ITEMS)[0], r)


class Ics(unittest.TestCase):
    def test_fold_keeps_75_octets_and_utf8(self):
        line = "SUMMARY:" + "Leashly × Northlight · " * 8
        folded = closer.fold(line)
        for part in folded.split("\r\n"):
            self.assertLessEqual(len(part.encode("utf-8")), 75)
        self.assertEqual(folded.replace("\r\n ", ""), line)

    def test_eastern_time_to_utc_across_the_dst_change(self):
        self.assertEqual(closer.parse_start("2026-11-05 10:00", "America/New_York")[0],
                         datetime.datetime(2026, 11, 5, 15, 0))
        self.assertEqual(closer.parse_start("2026-10-29 10:00", "ET")[0], datetime.datetime(2026, 10, 29, 14, 0))
        self.assertEqual(closer.parse_start("2026-11-05T10:00-05:00", "ET")[0], datetime.datetime(2026, 11, 5, 15, 0))
        self.assertEqual(closer.parse_start("2026-07-01 10:00", "Europe/London")[0], datetime.datetime(2026, 7, 1, 9, 0))
        self.assertEqual(closer.parse_start("2026-07-01 10:00", "Australia/Sydney")[0],
                         datetime.datetime(2026, 7, 1, 0, 0))
        # 1:30 happens twice on Nov 1 2026: the first (daylight) one wins; 2:30 on Mar 8 never happens
        self.assertEqual(closer.parse_start("2026-11-01 01:30", "ET")[0], datetime.datetime(2026, 11, 1, 5, 30))
        with self.assertRaises(closer.CloserError):
            closer.parse_start("2026-03-08 02:30", "ET")
        with self.assertRaises(closer.CloserError):
            closer.parse_start("2026-11-05 10:00", "Mars/Olympus")


class Classify(unittest.TestCase):
    TODAY = D(2026, 10, 30)
    CASES = [
        ("Interesting. What's your take rate, and how do you guarantee the backup walker?", "question"),
        ("Send the deck over?", "interested"),
        ("Happy to chat, I love this.", "interested"),
        ("Thursday 10am works. Send an invite.", "interested"),
        ("Not this quarter, keep me posted.", "not_now"),
        ("We'll pass for now, but keep in touch.", "not_now"),
        ("Pet services are outside our thesis, so we'll pass.", "no"),
        ("No thanks.", "no"),
        ("no", "no"),
        ("No worries if not, but happy to chat next week!", "interested"),
        ("Please remove me from your list.", "optout"),
        ("Unsubscribe", "optout"),
        ("I am out of the office until Monday, November 9 with limited access to email.", "ooo"),
        ("Thanks for the note.", "unclear"),
    ]

    def test_rules(self):
        for text, want in self.CASES:
            self.assertEqual(closer.classify(text, today=self.TODAY)["class"], want, text)

    def test_bounce_from_the_mail_system(self):
        info = closer.classify("Address not found. Your message wasn't delivered to x@y.example.", "Delivery Status "
                               "Notification (Failure)", "Mail Delivery Subsystem <mailer-daemon@mail.example>")
        self.assertEqual(info["class"], "bounce")

    def test_quoted_opt_out_line_is_ignored(self):
        text = ("Sounds good, let's find a time.\n\nOn Mon, Oct 26, 2026 at 9:02 AM Casey Morgan <\n"
                "casey@leashly.example> wrote:\n> Not a fit? Reply 'no' and I won't follow up.\n")
        self.assertEqual(closer.classify(text, today=self.TODAY)["class"], "interested")
        self.assertEqual(closer.strip_quoted("Yes!\n> no\n> no"), "Yes!")

    def test_return_dates(self):
        f = closer.find_return_date
        self.assertEqual(f("out until Monday, November 9", self.TODAY), D(2026, 11, 9))
        self.assertEqual(f("back on 2026-11-12", self.TODAY), D(2026, 11, 12))
        self.assertEqual(f("returning on 3 January", self.TODAY), D(2027, 1, 3))
        self.assertEqual(f("away until 11/16", self.TODAY), D(2026, 11, 16))
        self.assertEqual(f("back on Tuesday", self.TODAY), D(2026, 11, 3))
        self.assertIsNone(f("on vacation, limited email", self.TODAY))


class Flow(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        shutil.copy(os.path.join(F, "config.json"), self.d)
        shutil.copy(os.path.join(F, "investors.json"), self.d)

    def tearDown(self):
        shutil.rmtree(self.d)

    def c(self, *argv, **kw):
        return run(list(argv) + ["--dir", self.d] + (["--today", kw["today"]] if kw.get("today") else []))

    def pipe(self):
        with open(os.path.join(self.d, "pipeline.json")) as fh:
            return {r["id"]: r for r in json.load(fh)["investors"]}

    def batch_id(self, today, *extra):
        code, text, _ = self.c("batch", "--json", *extra, today=today)
        self.assertEqual(code, 0, text)
        return json.loads(text)["batch"]

    def send_all(self, today, ids=None, reply="yes"):
        extra = ["--ids", ids] if ids else []
        b = self.batch_id(today, *extra)
        code, text, err = self.c("approve", "--batch", b, "--reply", reply, *extra, today=today)
        self.assertEqual(code, 0, text + err)
        rows = json.loads(text[text.index("["):text.rindex("]") + 1])
        for r in rows:
            self.assertEqual(self.c("log", "--id", r["id"], "--event", "sent", "--thread-id", "t-" + r["id"],
                                    today=today)[0], 0)
        return rows

    def test_draft_writes_valid_eml_and_the_pipeline(self):
        code, text, _ = self.c("draft", today="2026-10-26")
        self.assertEqual(code, 0, text)
        path = os.path.join(self.d, "outreach", "maya-chen-1.eml")
        with open(path, "rb") as fh:
            data = fh.read()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))           # CRLF only
        msg = email.message_from_bytes(data, policy=email.policy.default)
        self.assertEqual(msg["To"].addresses[0].addr_spec, "maya@northlight.example")
        self.assertEqual(msg["From"].addresses[0].display_name, "Casey Morgan")
        self.assertEqual(str(msg["Subject"]), "Leashly: dog walks without the surprise fees")
        self.assertEqual(str(msg["Date"]), "Mon, 26 Oct 2026 13:00:00 +0000")
        self.assertRegex(str(msg["Message-ID"]), r"^<maya-chen-1\.[0-9a-f]{12}@leashly\.example>$")
        self.assertEqual(msg["MIME-Version"], "1.0")
        body = msg.get_content().replace("\r\n", "\n")
        for part in ("Hi Maya,", MAYA_LINE, "Leashly is a dog-walking app with flat prices and a backup walker on "
                     "every walk.", "We're raising a $1.5M seed.", closer.OPTOUT, "Casey Morgan\nFounder, Leashly\n"
                     "100 Example Street, Austin, TX 78701"):
            self.assertIn(part, body)
        p = self.pipe()
        self.assertEqual(len(p), 6)
        self.assertEqual({r["status"] for r in p.values()}, {"drafted"})
        self.assertEqual(p["maya-chen"]["draft"]["file"], "outreach/maya-chen-1.eml")
        self.assertIn("Nothing is sent", text)

    def test_dry_run_writes_nothing(self):
        code, text, _ = self.c("draft", "--top", "2", "--dry-run", today="2026-10-26")
        self.assertEqual(code, 0)
        self.assertIn("Would draft 2 intros", text)
        self.assertFalse(os.path.exists(os.path.join(self.d, "pipeline.json")))
        self.assertFalse(os.path.exists(os.path.join(self.d, "outreach")))

    def test_bad_rows_are_refused_and_the_rest_drafted(self):
        shutil.copy(os.path.join(F, "investors-bad.json"), os.path.join(self.d, "investors.json"))
        code, text, _ = self.c("draft", today="2026-10-26")
        self.assertEqual(code, 1)
        self.assertEqual(list(self.pipe()), ["maya-chen"])
        for rid, why in (("gary-stone", "generic"), ("nina-hart", "no public source"), ("omar-said", "no valid email"),
                         ("lena-fox", "no personal_line"), ("dana-cole", "already used for maya-chen"),
                         ("ray-kim", "cut off")):
            self.assertRegex(text, r"REFUSED %s: .*%s" % (rid, re.escape(why)))

    def test_the_example_config_name_is_refused(self):
        with open(os.path.join(ROOT, "seed-plan", "config.example.json")) as fh:
            cfg = json.load(fh)
        with self.assertRaises(closer.CloserError) as cm:
            closer.sender_of(cfg)
        self.assertIn("real name", str(cm.exception))

    def test_missing_tagline_falls_back_to_the_one_liner(self):
        cfg_path = os.path.join(self.d, "config.json")
        with open(cfg_path) as fh:
            cfg = json.load(fh)
        del cfg["startup"]["tagline"]
        with open(cfg_path, "w") as fh:
            json.dump(cfg, fh)
        code, text, _ = self.c("draft", "--ids", "maya-chen", today="2026-10-26")
        self.assertEqual(code, 0, text)
        self.assertIn("Subject: Leashly: a dog-walking app with flat prices and a backup walker on every walk", text)
        self.assertIn("note: maya-chen: the subject is", text)

    def test_template_must_keep_the_opt_out(self):
        with open(os.path.join(ROOT, "seed-closer", "template.txt")) as fh:
            tpl = fh.read()
        with open(os.path.join(self.d, "template.txt"), "w") as fh:
            fh.write(tpl.replace("{optout}", ""))
        code, _, err = self.c("draft", today="2026-10-26")
        self.assertEqual(code, 1)
        self.assertIn("{optout}", err)
        with open(os.path.join(self.d, "template.txt"), "w") as fh:
            fh.write(tpl.replace("{personal_line}", "{personal_line} {favorite_color}"))
        code, _, err = self.c("draft", today="2026-10-26")
        self.assertIn("{favorite_color}", err)

    def test_the_yes_gate(self):
        self.c("draft", today="2026-10-26")
        b = self.batch_id("2026-10-26")
        code, text, _ = self.c("batch", today="2026-10-26")
        self.assertIn("BATCH %s: 6 emails" % b, text)
        self.assertIn('"%s"' % MAYA_LINE, text)
        self.assertIn("The first email, in full:", text)
        for reply in ("sure", "yes except Marcus", "yes send 5"):
            code, text, _ = self.c("approve", "--batch", b, "--reply", reply, today="2026-10-26")
            self.assertEqual(code, 1, reply)
            self.assertIn("Not recorded", text)
        self.assertEqual(self.pipe()["maya-chen"]["status"], "drafted")
        code, _, err = self.c("log", "--id", "maya-chen", "--event", "sent", today="2026-10-26")
        self.assertEqual(code, 1)
        self.assertIn("the yes comes first", err)
        # a draft edited after the batch was shown changes the batch id
        path = os.path.join(self.d, "outreach", "marcus-lee-1.eml")
        with open(path, "ab") as fh:
            fh.write(b"P.S. edited\r\n")
        code, _, err = self.c("approve", "--batch", b, "--reply", "yes", today="2026-10-26")
        self.assertEqual(code, 1)
        self.assertIn("changed since it was shown", err)
        b2 = self.batch_id("2026-10-26")
        code, text, _ = self.c("approve", "--batch", b2, "--reply", "Yes, send all 6", today="2026-10-26")
        self.assertEqual(code, 0)
        self.assertIn("one tool call per email", text)
        p = self.pipe()
        self.assertEqual(p["maya-chen"]["status"], "approved")
        self.assertEqual(p["maya-chen"]["draft"]["reply"], "Yes, send all 6")
        code, text, _ = self.c("outbox", "--json")
        rows = json.loads(text)
        self.assertEqual(len(rows), 6)
        self.assertIn(closer.OPTOUT, rows[0]["body"])
        self.assertEqual(self.c("log", "--id", "marcus-lee", "--event", "denied", today="2026-10-26")[0], 0)
        self.assertEqual(self.pipe()["marcus-lee"]["status"], "drafted")

    def test_the_daily_cap(self):
        cfg_path = os.path.join(self.d, "config.json")
        with open(cfg_path) as fh:
            cfg = json.load(fh)
        cfg["outreach"]["daily_cap"] = 4
        with open(cfg_path, "w") as fh:
            json.dump(cfg, fh)
        self.c("draft", today="2026-10-26")
        code, text, _ = self.c("batch", today="2026-10-26")
        self.assertIn("4 emails", text)
        self.assertIn("2 more drafts wait for the next day", text)
        rows = self.send_all("2026-10-26")
        self.assertEqual([r["id"] for r in rows], ["maya-chen", "daniel-okafor", "priya-raman", "sam-whitaker"])
        code, text, _ = self.c("batch", today="2026-10-26")
        self.assertEqual(code, 1)
        self.assertIn("cap of 4 cold emails is used", text)
        self.assertEqual(len(self.send_all("2026-10-27")), 2)

    def test_the_whole_road_to_a_booked_call(self):
        self.c("draft", today="2026-10-26")
        self.send_all("2026-10-26")
        p = self.pipe()
        self.assertEqual((p["maya-chen"]["status"], p["maya-chen"]["next_due"]), ("sent", "2026-10-29"))
        self.assertEqual(p["maya-chen"]["thread_id"], "t-maya-chen")
        code, text, _ = self.c("due", today="2026-10-28")
        self.assertEqual(code, 1)
        code, text, _ = self.c("due", today="2026-10-31")
        self.assertEqual(code, 1)
        self.assertIn("not a business day", text)
        code, text, _ = self.c("due", "--json", today="2026-10-29")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(text)["due"]), 6)
        code, _, err = self.c("followup", "--id", "maya-chen", today="2026-10-28")
        self.assertIn("not due until Thu 2026-10-29", err)
        code, text, _ = self.c("followup", "--due", "--extra", "Here's our 60-second demo: https://leashly.example/demo",
                               today="2026-10-29")
        self.assertEqual(code, 0, text)
        with open(os.path.join(self.d, "outreach", "maya-chen-2.eml"), "rb") as fh:
            fu = email.message_from_bytes(fh.read(), policy=email.policy.default)
        intro_id = self.pipe()["maya-chen"]["touches"][0]["message_id"]
        self.assertEqual((fu["In-Reply-To"], fu["References"]), (intro_id, intro_id))
        self.assertEqual(str(fu["Subject"]), "Re: Leashly: dog walks without the surprise fees")
        body = fu.get_content().replace("\r\n", "\n")
        self.assertIn("my note from Monday, Oct 26 about Leashly", body)
        self.assertIn("60-second demo", body)
        self.assertIn(closer.OPTOUT, body)
        self.assertLess(closer.words(body.split(closer.OPTOUT)[0]), 80)
        # replies arrive: follow-ups stop, the waiting drafts are void, OOO holds Marcus
        code, text, _ = self.c("inbox", "--file", os.path.join(F, "replies.json"), "--write", today="2026-10-30")
        self.assertEqual(code, 0, text)
        p = self.pipe()
        got = {k: (v["status"], v["labels"][-1]) for k, v in p.items()}
        self.assertEqual(got, {"maya-chen": ("replied", "Asked a question"), "daniel-okafor": ("interested", "Interested"),
                               "priya-raman": ("passed", "Not now"), "sam-whitaker": ("interested", "Interested"),
                               "elena-brooks": ("passed", "No"), "marcus-lee": ("sent", "Out of office")})
        self.assertIsNone(p["maya-chen"]["draft"])
        self.assertIsNone(p["marcus-lee"]["draft"])
        self.assertEqual((p["marcus-lee"]["hold_until"], p["marcus-lee"]["next_due"]), ("2026-11-09", "2026-11-10"))
        code, _, err = self.c("followup", "--id", "maya-chen", today="2026-11-04")
        self.assertIn("follow-ups stop after a reply", err)
        code, text, _ = self.c("draft", "--ids", "elena-brooks", today="2026-11-04")
        self.assertEqual(code, 1)
        self.assertIn("REFUSED elena-brooks: the thread is closed for good", text)
        code, _, err = self.c("log", "--id", "elena-brooks", "--event", "interested", today="2026-11-04")
        self.assertEqual(code, 1)
        self.assertIn("ended for good", err)
        # the answer goes into the thread after a new yes
        code, text, _ = self.c("reply", "--id", "maya-chen", "--body-file", os.path.join(F, "answer.txt"),
                               today="2026-11-02")
        self.assertEqual(code, 0, text)
        rows = self.send_all("2026-11-02", ids="maya-chen")
        self.assertEqual((rows[0]["kind"], rows[0]["thread_id"]), ("reply", "t-maya-chen"))
        self.assertTrue(rows[0]["subject"].startswith("Re: "))
        self.assertEqual(self.c("inbox", "--id", "maya-chen", "--text", "Thursday 10am works. Send an invite.",
                                "--write", today="2026-11-02")[0], 0)
        code, text, _ = self.c("book", "--id", "maya-chen", "--start", "2026-11-05 10:00", "--tz", "America/New_York",
                               "--link", "https://meet.google.com/abc-defg-hij", "--stamp", "2026-11-02T15:04:00Z",
                               today="2026-11-02")
        self.assertEqual(code, 0, text)
        self.assertIn("Nothing was sent", text)
        with open(os.path.join(self.d, "calls", "maya-chen.ics"), "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        for line in raw.split(b"\r\n"):
            self.assertLessEqual(len(line), 75)
        ics = raw.decode("utf-8").replace("\r\n ", "")
        props = dict(l.split(":", 1) for l in ics.split("\r\n") if ":" in l)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 1)
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:"))
        self.assertTrue(ics.endswith("END:VEVENT\r\nEND:VCALENDAR\r\n"))
        self.assertEqual((props["DTSTART"], props["DTEND"], props["DTSTAMP"]),
                         ("20261105T150000Z", "20261105T153000Z", "20261102T150400Z"))
        self.assertEqual(props["METHOD"], "REQUEST")
        self.assertRegex(props["UID"], r"^seed-[0-9a-f]{16}@leashly\.example$")
        self.assertEqual(props["SUMMARY"], "Leashly × Northlight Ventures · Intro call")
        self.assertIn("ORGANIZER;CN=Casey Morgan:mailto:casey@leashly.example", ics)
        self.assertIn("ATTENDEE;CN=Maya Chen;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:"
                      "mailto:maya@northlight.example", ics)
        self.assertIn("Thursday\\, November 5\\, 2026\\, 10:00 AM to 10:30 AM America/New_York (UTC-05:00)", ics)
        self.assertEqual(props["LOCATION"], "https://meet.google.com/abc-defg-hij")
        uid = props["UID"]
        # a reschedule keeps the UID and bumps the sequence
        self.c("book", "--id", "maya-chen", "--start", "2026-11-06 10:00", "--link", "https://meet.google.com/abc",
               "--stamp", "2026-11-03T15:00:00Z", today="2026-11-03")
        with open(os.path.join(self.d, "calls", "maya-chen.ics"), "rb") as fh:
            again = fh.read().decode("utf-8").replace("\r\n ", "")
        self.assertIn("UID:%s\r\nSEQUENCE:1\r\n" % uid, again)
        code, text, _ = self.c("status", "--json", today="2026-11-03")
        st = json.loads(text)
        self.assertEqual(st["funnel"], {"drafted": 6, "sent": 6, "replied": 5, "interested": 3, "booked": 1})
        self.assertEqual(st["reply_rate_pct"], 83.3)
        self.assertEqual(st["calls"][0]["start_utc"], "20261106T150000Z")
        code, text, _ = self.c("status", today="2026-11-03")
        self.assertIn("stopped: 2 passed (1 not now)", text)

    def test_book_refusals(self):
        self.c("draft", today="2026-10-26")
        self.send_all("2026-10-26")
        args = ["book", "--id", "maya-chen", "--start", "2026-11-05 10:00", "--link", "https://meet.google.com/x"]
        code, _, err = self.c(*args, today="2026-10-27")
        self.assertIn("only after they replied", err)
        self.c("log", "--id", "maya-chen", "--event", "interested", today="2026-10-27")
        for extra, why in ((["--start", "2026-10-01 10:00"], "in the past"),
                           (["--link", "http://insecure.example"], "https://"),
                           (["--minutes", "5"], "book 10 to 240"),
                           (["--tz", "Mars/Olympus"], "unknown time zone")):
            a = list(args)
            for i in range(0, len(extra), 2):
                if extra[i] in a:
                    a[a.index(extra[i]) + 1] = extra[i + 1]
                else:
                    a += extra[i:i + 2]
            code, _, err = self.c(*a, today="2026-10-27")
            self.assertEqual(code, 1, extra)
            self.assertIn(why, err)
            self.assertNotIn("Traceback", err)

    def test_bounce_and_optout_close_the_thread_and_the_address(self):
        self.c("draft", "--top", "2", today="2026-10-26")
        self.send_all("2026-10-26")
        code, text, _ = self.c("inbox", "--from", "Mail Delivery Subsystem <mailer-daemon@mail.example>",
                               "--subject", "Delivery Status Notification (Failure)",
                               "--text", "Address not found: daniel@harborseed.example could not be delivered.",
                               "--write", today="2026-10-27")
        self.assertIn("[daniel-okafor]: BOUNCED", text)
        self.c("log", "--id", "maya-chen", "--event", "optout", today="2026-10-27")
        p = self.pipe()
        self.assertEqual((p["maya-chen"]["status"], p["daniel-okafor"]["status"]), ("optout", "bounced"))
        self.assertIsNone(closer.next_due(p["maya-chen"], RULES))
        # the same address under a new id is still never emailed
        with open(os.path.join(self.d, "investors.json")) as fh:
            doc = json.load(fh)
        row = dict(doc["investors"][0], id="maya-chen-2")
        doc["investors"].append(row)
        with open(os.path.join(self.d, "investors.json"), "w") as fh:
            json.dump(doc, fh)
        code, text, _ = self.c("draft", "--ids", "maya-chen-2", today="2026-10-28")
        self.assertEqual(code, 1)
        self.assertIn("never emailed again", text)

    def test_errors_exit_1_without_a_traceback(self):
        for argv in (["batch"], ["status", "--id", "nobody"], ["log", "--id", "x", "--event", "sent"],
                     ["due", "--today", "26/10/2026"]):
            code, _, err = self.c(*argv)
            self.assertEqual(code, 1, argv)
            self.assertNotIn("Traceback", err)
        self.assertEqual(run([])[0], 1)
