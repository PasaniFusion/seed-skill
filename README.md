# The Seed skill

11 Claude skills that take your startup from idea to funded: competitor research, investor matching, a business plan, a pitch deck and a closer that books your investor calls.

Free, MIT, no signup, no API key. The tools are plain Python that read free
public data (the App Store's own search and review feeds, SEC EDGAR) and do
the arithmetic. Everything they write lands in a `seed/` folder in your
project, so every skill picks up where the last one stopped.

One finds the weak points of your competitors, straight from their own
one-star reviews. Another researches the best investors for your idea, from
public sources, and ranks them by fit with the reasons and the links. Then one
turns your idea into a business plan, and another turns the plan into a pitch
deck.

And the craziest one is the Closer. It writes a personalised outreach email
to every investor on your list, keeps track of every conversation, sorts the
replies, and follows up until an investor call is booked, with the calendar
invite ready to send. So all you have to do is show up.

**Nothing leaves your inbox until you say yes.** The Closer drafts. Claude
sends through your own Gmail connector only after you approve the batch, with
a daily cap, an opt-out line in every email, and a thread that stops for good
on a "no".

## Install

Paste this into Claude:

```
https://github.com/Jakeschincariol/seed-skill

install skill
```

Or as a plugin, in Claude Code:

```
/plugin marketplace add Jakeschincariol/seed-skill
/plugin install seed-skill@seed-skill
```

Claude Code namespaces plugin skills, so installed as a plugin they show up as
`/seed-skill:seed-scout` and so on. Copy the folders instead if you want plain
`/seed-scout`:

```bash
git clone https://github.com/Jakeschincariol/seed-skill.git
cp -r seed-skill/seed-* ~/.claude/skills/
```

Project-local instead of global: copy the same folders into your repo's
`.claude/skills/`. No Claude Code at all? Paste any single `SKILL.md` at the
top of a chat and it runs as a mode. You lose the Python tools, but the method
works.

The tools need Python 3.8 or newer. Nothing to pip install. The investor
finder's SEC search asks you to identify yourself, as the SEC requires: put
your name and email in `seed/config.json` (`"sec_user_agent": "Your Name
you@example.com"`) or in the `SEC_USER_AGENT` environment variable.

To send email and book calls, connect Gmail and Google Calendar in Claude
(Customize, Connectors) and set their send tools to "Needs approval".

## The eleven

| command | job | what it does |
| --- | --- | --- |
| `/seed-scout` | Competitor Scout | Finds the weak points of your competitors: reads up to 500 of each rival app's latest App Store reviews and counts what the one- and two-star ones complain about. |
| `/seed-investors` | Investor Finder | Researches the best investors for your idea from public sources and SEC Form D filings, then ranks them by fit with the reasons and the links. |
| `/seed-plan` | Business Planner | Turns your idea into a business plan: the nine sections, with the unit economics worked out and every number cross-checked. |
| `/seed-deck` | Pitch Deck Designer | Turns the plan into a 10-slide pitch deck, one self-contained file you can present or print to PDF. |
| `/seed-closer` | The Closer | Sends personalised outreach to investors (only after your yes), manages the conversations, follows up and books the call. |
| `/seed-market` | Market Sizer | Sizes your market top-down and bottom-up, TAM, SAM and SOM, with a source on every input. |
| `/seed-model` | Financial Modeler | Builds the 36-month model: revenue, burn, runway, the month you break even and where the money goes. |
| `/seed-coach` | Pitch Coach | Drills you on the hard questions this investor will ask, tailored to your numbers and your competitors. |
| `/seed-terms` | Term Sheet Reader | Reads a SAFE or a term sheet in plain English, does the dilution math and flags the clauses to ask a lawyer about. |
| `/seed-dataroom` | Data Room Builder | Builds the data room investors ask for and tells you what is missing. |
| `/seed-updates` | Investor Updates | Writes the monthly update that keeps investors, and the ones who said "not now", warm. |

## How to use it

Everything lands in a `seed/` folder in your project, and each skill reads
what the last one wrote:

```
scout -> market -> model -> plan -> deck            (the story and the numbers)
investors -> closer -> coach                         (the raise: who, the outreach, the call)
terms -> dataroom                                    (when an investor says yes)
updates                                              (every month, before and after)
```

Say what you want in plain words ("find my competitors' weak points", "who
should I pitch", "write the deck", "follow up with everyone who hasn't
replied") and Claude picks the skill.

## Example: the reel

The startup in the reel is made up: **Leashly**, "a dog-walking app with flat
prices and a backup walker on every walk", raising a $1.5M seed. The
competitors and the market numbers are real.

1. **`/seed-scout`** read the 500 most recent App Store reviews of Rover and of
   Wag! on October 25, 2026. Rover (4.9 stars, 515,771 ratings): 106 of its 341
   one- and two-star reviews mention fees. Wag! (4.8 stars, 67,447 ratings): 81
   of its 324 mention cancellations. Those are the weak points: fees, and
   walkers who cancel at the last minute.
2. **`/seed-market`** sized it from APPA's 2026 report: $158 billion of US pet
   spending in 2025, and 71 million US homes (53%) with a dog.
3. **`/seed-model`** ran 36 months at $25 a walk and a 15% take rate, with the
   $1.5M raise (the example assumptions in `seed-model/`): $467,400 of revenue
   in year 1 and $2,993,520 in year 3, $2.23 of contribution per walk, LTV:CAC
   of 4.24x, peak burn $82,801 in month 5, break-even in month 29, and cash
   that never runs out (its low point is $252,553).
4. **`/seed-plan`** and **`/seed-deck`** turned that into the nine-section plan
   and the 10-slide deck that ends on "$1.5M seed to launch in 3 cities".
5. **`/seed-investors`** ranked the investors who back pet and local-services
   marketplaces at seed (the reel's names, like Maya Chen of Northlight
   Ventures, are fictional too).
6. **`/seed-closer`** drafted one email per investor, each with its own first
   line ("Saw you led two pet-care seed rounds..."). After the yes, it
   followed up on day 3 and day 7 of the ones that went quiet, sorted the
   replies, answered Maya's take-rate question from the plan, and when she
   wrote "Thursday 10am works", wrote the invite: Leashly x Northlight
   Ventures, Thursday November 5, 10:00 AM ET.
7. **`/seed-coach`** prepared the 20-minute call, and **`/seed-terms`** and
   **`/seed-dataroom`** are there for what comes after it.

## Fine print

**No promise of funding.** This is software that drafts, researches and does
arithmetic. Investors decide whether to invest, based on your business. A
better deck and a faster follow-up help; they do not guarantee a check.

**Nothing sends without your yes.** Only `/seed-closer` can lead to an email,
and only after you approve that batch in the chat. Set your Gmail connector's
send tool to "Needs approval" (Customize, Connectors, tool permissions), never
"Always allow", so Claude's own "Allow once / Deny" card is a second check.
Every email carries your real name and an opt-out line. A "no", an opt-out or
a bounce ends that thread for good. Default cap: 20 new emails a day.

**Public sources only.** The investor finder reads public pages (a firm's own
site, public profiles found through search, SEC EDGAR, the press) and keeps
the link for every fact. It never logs in anywhere, never scrapes behind a
login and never scrapes LinkedIn. Check a fact before you lean on it in an
email.

**Not legal advice.** `/seed-terms` explains the common clauses and does the
dilution math. Have a startup lawyer read anything before you sign it.

**Not investment advice.** The model and the market size are only as good as
the assumptions you give them. They are there to make your thinking visible to
you and to an investor, not to predict the future.

**The data is free and public.** The App Store's search and review feeds are
not an official API and can change or rate-limit. SEC EDGAR asks every
automated request to say who is asking.
