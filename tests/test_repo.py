import json
import os
import re
import unittest

from _load import ROOT

# the eleven folders the reel's repo card shows, in the reel's order
SKILLS = ["seed-scout", "seed-investors", "seed-plan", "seed-deck", "seed-closer", "seed-market",
          "seed-model", "seed-coach", "seed-terms", "seed-dataroom", "seed-updates"]
ABOUT = ("11 Claude skills that take your startup from idea to funded: competitor research, investor "
         "matching, a business plan, a pitch deck and a closer that books your investor calls.")
# skills that can lead to an email leaving the user's account carry the yes rule
SENDS = ["seed-closer"]
# skills that touch money or contracts carry their disclaimer
DISCLAIMERS = {"seed-terms": "not legal advice"}
PERSONAL = re.compile(r"[A-Za-z0-9._%+-]+@(gmail|yahoo|hotmail|outlook|icloud|proton)\.(com|me)", re.I)


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


def every_text_file():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            if f.endswith((".md", ".py", ".json", ".csv", ".txt", ".xml", ".eml", ".ics", ".html")) or f == "LICENSE":
                yield os.path.join(base, f)


class Repo(unittest.TestCase):
    def test_eleven_skill_folders_at_the_root(self):
        found = sorted(d for d in os.listdir(ROOT)
                       if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, sorted(SKILLS))

    def test_root_matches_the_reel(self):
        root = sorted(d for d in os.listdir(ROOT) if not d.startswith(".git") and d != ".DS_Store")
        self.assertEqual(root, sorted([".claude-plugin", "LICENSE", "README.md", "tests"] + SKILLS))

    def test_every_skill_has_a_tool_and_a_test(self):
        tests = os.listdir(os.path.join(ROOT, "tests"))
        for s in SKILLS:
            py = [f for f in os.listdir(os.path.join(ROOT, s)) if f.endswith(".py")]
            self.assertTrue(py, "%s has no tool" % s)
            self.assertIn("test_%s.py" % s.split("-", 1)[1], tests, s)

    def test_frontmatter_name_and_description(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s\n" % s, fm + "\n", s)
            self.assertRegex(fm, r"description: ", s)
            self.assertGreater(len(fm), 200, "%s description is too thin" % s)
            self.assertGreater(len(text.splitlines()), 60, s)
            self.assertIn("${CLAUDE_SKILL_DIR}", text, s)

    def test_the_closer_never_sends_without_a_yes(self):
        for s in SENDS:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertIn("yes", low, s)
            self.assertIn("opt-out", low, s)
            self.assertIn("daily cap", low, s)

    def test_disclaimers(self):
        for s, line in DISCLAIMERS.items():
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn(line, " ".join(text.lower().split()), s)

    def test_plugin_manifest_points_at_the_root_skills(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as fh:
            plugin = json.load(fh)
        self.assertEqual(plugin["name"], "seed-skill")
        self.assertEqual(plugin["skills"], "./")
        self.assertEqual(plugin["description"], ABOUT)
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as fh:
            market = json.load(fh)
        self.assertEqual(market["name"], "seed-skill")
        self.assertEqual(market["plugins"][0]["name"], "seed-skill")
        self.assertEqual(market["plugins"][0]["source"], "./")

    def test_readme_carries_the_reel_copy(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = " ".join(fh.read().split())
        self.assertTrue(readme.startswith("# The Seed skill"))
        for line in (ABOUT,
                     "https://github.com/Jakeschincariol/seed-skill install skill",
                     "/plugin marketplace add Jakeschincariol/seed-skill",
                     "/plugin install seed-skill@seed-skill",
                     "## Fine print"):
            self.assertIn(line, readme)
        for s in SKILLS:
            self.assertIn("/" + s, readme, s)

    def test_no_em_dashes_and_no_personal_email(self):
        for path in every_text_file():
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            rel = os.path.relpath(path, ROOT)
            self.assertNotIn("\u2014", text, rel)
            self.assertIsNone(PERSONAL.search(text), rel)

    def test_json_files_parse(self):
        for path in every_text_file():
            if path.endswith(".json"):
                with open(path, encoding="utf-8") as fh:
                    json.load(fh)


if __name__ == "__main__":
    unittest.main()
