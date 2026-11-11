---
name: seed-closer
description: >-
  The Closer. Drafts personalised outreach emails to investors, manages the
  conversations and keeps following up until an investor call is booked.
  Draft-only: Claude never sends an email or an invite; the user reads every
  one in their own Gmail Drafts and presses send. Drafts one RFC 5322
  .eml per investor from seed/investors.json and a template (a real personal
  line, the sender's real name and an opt-out line, generic lines refused),
  shows the batch, records the user's yes word for word, enforces a daily cap
  of 20, then Claude saves each email with the Gmail connector's create_draft
  (never a send or reply tool). Schedules follow-ups on +3 and +7
  business days (3 touches at most, never after a reply), sorts replies into
  interested / question / not now / no / out of office, stops a thread for
  good on a no, an opt-out or a bounce, writes a valid .ics invite and shows
  the funnel. Reads seed/config.json and seed/investors.json, writes
  seed/pipeline.json, seed/outreach/ and seed/calls/. Use when the user says
  "email the investors", "send the outreach", "follow up with everyone who
  hasn't replied", "who do I follow up with today", "sort my replies", "book
  the call", "send her an invite", "how is the raise going", or after
  /seed-investors ranks the list.
argument-hint: "[draft | batch | due | inbox | book | status]"
---

# seed-closer

The Closer does the part of a raise that eats the founder's week: one
personal email per investor, the follow-ups nobody remembers to send, the
replies sorted, and the call on the calendar. It writes everything; it never
sends anything, and neither does Claude. After the user said yes to that
exact batch in the chat, Claude saves each email as a draft in the user's own
Gmail. The user reads every draft there, edits it if they like, and presses
send themselves. All the user has to do is say yes, send, show up and pitch.
Investors decide; nothing here promises a check.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/closer.py" draft --top 20          # one .eml per investor, status drafted
python3 "${CLAUDE_SKILL_DIR}/closer.py" batch                   # recipients, their personal lines, the first email in full
python3 "${CLAUDE_SKILL_DIR}/closer.py" approve --batch 3f9a1c2e --reply "yes"   # the user's reply, word for word
python3 "${CLAUDE_SKILL_DIR}/closer.py" outbox --json           # what still goes into Gmail Drafts: to, subject, body, thread
python3 "${CLAUDE_SKILL_DIR}/closer.py" log --id maya-chen --event gmail-draft --gmail-draft-id r-123 --thread-id 18c2f0a1
python3 "${CLAUDE_SKILL_DIR}/closer.py" log --id maya-chen --event sent --date 2026-10-27   # once the user sent it from Gmail
python3 "${CLAUDE_SKILL_DIR}/closer.py" due --today 2026-10-29  # who gets a follow-up today
python3 "${CLAUDE_SKILL_DIR}/closer.py" followup --due --extra "Here's our 60-second demo: https://..."
python3 "${CLAUDE_SKILL_DIR}/closer.py" inbox --file replies.json            # sort replies, then --write
python3 "${CLAUDE_SKILL_DIR}/closer.py" reply --id maya-chen --body-file answer.txt
python3 "${CLAUDE_SKILL_DIR}/closer.py" reply --id maya-chen --booking   # interested: the reply ends with founder.booking_link
python3 "${CLAUDE_SKILL_DIR}/closer.py" book --id maya-chen --start "2026-11-05 10:00" --tz America/New_York --link https://meet.google.com/abc-defg-hij
python3 "${CLAUDE_SKILL_DIR}/closer.py" status                  # the funnel
```

Every command takes `--dir` (default `./seed`) and `--today YYYY-MM-DD` (pin
the date). `--json` on batch, outbox, due, inbox and status.

## What it reads and writes

| file | what |
| --- | --- |
| `seed/config.json` | `startup` (name, one_liner, optional tagline, raise, stage), `founder` (your real name, the address you send from, company_address, optional booking_link: your own booking page such as `https://calendly.com/your-name/45min`), `outreach` (daily_cap 20, followup_days [3, 7], max_touches 3, business_days true, optional holidays) |
| `seed/investors.json` | from /seed-investors: id, name, firm, email, sources, fit, reasons, personal_line |
| `template.txt` | the intro and the two follow-ups (this folder; copy it to `seed/template.txt` to make your own) |
| `seed/outreach/<id>-<n>.eml` | each draft: a valid RFC 5322 message (CRLF, From, To, Subject, Date, Message-ID, plain text); follow-ups carry In-Reply-To |
| `seed/pipeline.json` | one row per investor: status, touches, next_due, labels, notes, the waiting draft (and its Gmail draft id once it is in Gmail Drafts), the Gmail thread id, the call, the history |
| `seed/calls/<id>.ics` | the invite: RFC 5545, CRLF, folded at 75 octets, UTC times, UID, SEQUENCE, ORGANIZER, ATTENDEE, the video link |

## The rules it enforces

- **A real personal line or no email.** Each intro needs `personal_line`: one
  sentence about this investor from their public record. Refused: empty,
  under 7 words, cut off with "...", a placeholder, a stock opener ("hope this
  finds you well", "big fan", "love what you're doing", "impressive
  portfolio", "came across your profile"), the same line used for two people,
  and a line that names nothing from their row (a deal, a post, a sector, a
  number). Rows without an email or a public source URL are refused too.
- **Your real name and the opt-out line.** `founder.name` must be a real name
  ("Your Name" is refused). Every intro and follow-up carries "Not a fit?
  Reply 'no' and I won't follow up." A batch whose .eml lost it is refused.
- **The yes.** `approve` takes the user's reply word for word and the batch id
  `batch` printed. It counts only a reply that starts with "yes" and has no
  condition in it: "sure", "ok", "yes but drop Marcus", "yes tomorrow",
  "yes?" and a count that does not match the batch are not a yes. If the
  drafts changed after the batch was shown, the id no longer matches and
  nothing is recorded. `log --event sent` works only on an approved email.
- **The daily cap.** 20 cold emails a day by default (intros and follow-ups,
  counting today's sends and every approved one not sent yet), 50 at most
  whatever the config says. Replies in a live conversation do not count.
- **Three touches.** The intro on day 0, follow-up 1 on +3 business days and
  follow-up 2 on +7 (weekends and `outreach.holidays` skipped), never sooner
  than the planned gap after the touch before, and never once they replied.
- **Stops.** A no, an opt-out or a bounce ends the thread for good: the
  waiting draft is void, nothing more is recorded, and `draft` refuses that
  address forever. "Not now" is a soft pass: no more follow-ups, and
  /seed-updates can keep them posted if they asked.
- **Out of office** is not a reply: the follow-up waits until the business day
  after the return date it finds ("until Monday, November 9"), and a follow-up
  already drafted is voided and drafted again then.

Statuses: drafted, approved, sent, replied, interested, booked, and the ends
passed, bounced, optout. An approved email sits in the user's Gmail Drafts
until the user sends it; only then is it logged as sent.

## Draft-only: the Gmail-connector loop

Claude never sends. The only Gmail tool that writes is `create_draft`, and the
only person who presses send is the user, in Gmail. In the Claude Gmail
connector checked on 2026-11-11 the tools are `create_draft` (leave it in
Drafts; `replyToMessageId` keeps it in a thread; it takes attachments),
`search_threads` and `get_thread` (read only), and `send_message` and `reply`,
which send at once: **never call `send_message` or `reply`**, whatever the
user's yes said. Another Gmail connector may name them differently; use only
its draft tool. Keep the send tools on **Needs approval** (in Claude Code, on
ask, never in allow) so a slip still stops at a card. Nothing goes out any
other way: no mail-merge tool, no SMTP, no third-party sender.

1. `closer.py batch`. Show the user what it prints, as it prints it: every
   recipient with their personal line, the first email in full, the count
   against the daily cap. Ask: "Save these N emails as drafts in your Gmail?
   Nothing is sent: you read each one and press send yourself. Reply yes or
   no." One batch per question.
2. `closer.py approve --batch <id> --reply "<their reply, word for word>"`.
   "Not recorded" means it was not a clear yes: ask again, never turn a reply
   into a yes yourself. To draft fewer, show a smaller batch (`--ids`, `--limit`).
3. Only after "Recorded your yes", save each email from the JSON it printed
   as a Gmail draft, one tool call per email: `create_draft` with that to,
   subject and body (plain text, no Markdown). A follow-up or a reply is
   drafted inside its thread: `get_thread` on the `thread_id`, then
   `create_draft` with `replyToMessageId` set to that thread's last message.
4. After each draft: `closer.py log --id <id> --event gmail-draft
   --gmail-draft-id <the draft id> --thread-id <its threadId>`. `outbox
   --json` then leaves it out, so nothing is drafted twice. Stop the loop if
   anything looks wrong.
5. Tell the user the drafts are waiting in Gmail Drafts (link the `viewUrl`s)
   and that they send them, edited or not. When one shows up in Gmail's Sent
   (`search_threads` with `in:sent to:<their address>`, or `get_thread` on its
   thread), `closer.py log --id <id> --event sent --date <the day it went>`;
   the follow-ups count from that day. A draft the user deleted or does not
   want: `log --id <id> --event denied` (back to drafted, it needs a new yes).
   Drafts still in Gmail count against the daily cap until they are sent or
   denied.
6. Never from a scheduled or background task. A schedule may run `due`,
   `followup --due` and read replies; drafting into Gmail always waits for the
   user's yes in the chat.

## Steps

1. Check `seed/config.json`: the user's real name, the address they send from,
   a postal address (anti-spam laws such as CAN-SPAM expect one). Read
   `seed/investors.json` from /seed-investors; ask before writing to anyone
   with a personal mailbox.
2. `closer.py draft --top 20`. Read back what it refused and why. Fix a
   refused personal line from the investor's sources, never by inventing a
   fact, then draft that id again.
3. Run the Gmail loop above for the batch: batch, the yes, Gmail drafts,
   log; the user sends.
4. Every business day: first log anything the user sent from Gmail Drafts
   since last time (step 5 of the loop), then `closer.py due`. For the ones
   due, `followup --due`
   (an optional `--extra` line for follow-up 1, `--ask` for the last one),
   then the same loop.
5. Read new replies with `search_threads` / `get_thread` (read only, for
   example `from:maya@northlight.example newer_than:14d`). Put them in a
   replies.json (`[{"from", "subject", "date", "text"}]`) and run `inbox`.
   Show the user each label and the suggested next step, then `inbox --write`.
   Labelling the threads in Gmail (Interested, Asked a question, Not now) is
   optional: ask first.
6. A question: draft the answer from `seed/plan.json` and `seed/model.json`
   only (never a number that is not in them), `reply --id ... --body-file`,
   then the loop (a Gmail draft in the thread, for the user to send). The
   .eml carries no attachment: link the deck, or the user attaches the PDF in
   Gmail before sending.
7. Interested, with `founder.booking_link` set (the usual way): send the
   booking link, not proposed times and not a Google Meet or other video
   link. `closer.py reply --id <id> --booking` (add `--body-file` for a line
   of your own, or the deck) writes a reply that ends with the link, then the
   Gmail-draft loop; the user sends it. The investor picks a time and the
   booking page (Calendly) sends the invite, with its own video link, itself:
   draft no invite and create no calendar event. To see when they booked,
   read Calendly (read only: `meetings-list_events` with `invitee_email`,
   then `meetings-get_event`) and record it with `closer.py book --id <id>
   --start "<its start>" --tz <its zone> --minutes <its length> --link <its
   video link> --already-invited`.
   Interested, with no booking link: ask the user for their booking page
   once and save it as `founder.booking_link`; only if they have none, find
   two free slots with the user's calendar (read only, for example
   `suggest_time` or `list_events`) and offer them in a reply (drafted for the
   user to send). When they agree on a time, `inbox --write` that reply, then
   `closer.py book`. Show the invite, ask "Save this invite to
   Maya as a Gmail draft? You send it yourself. Reply yes or no", and after
   the yes `create_draft` in her thread with `seed/calls/<id>.ics` attached.
   **Never add the investor as a guest with Google Calendar `create_event`**:
   that emails the invite at once. To hold the slot, create the event on the
   user's own calendar with no guests.
8. `closer.py status` for the funnel. Hand off: /seed-coach `agenda` for each
   booked call, /seed-updates `--to prospects` for the soft passes, and
   /seed-terms and /seed-dataroom when an investor asks for next steps.

## Example: the reel

Leashly is fictional, and so are the investors. `draft --top 6 --today
2026-10-26` writes six intros from the founder's own address; Maya Chen's
(Northlight Ventures, fit 96) reads:

```
To: Maya Chen <maya@northlight.example>
Subject: Leashly: dog walks without the surprise fees

Hi Maya,

Saw you led two pet-care seed rounds, so you know the 20% fee problem better than anyone.

Leashly is a dog-walking app with flat prices and a backup walker on every walk.

We're raising a $1.5M seed. Open to a 20-minute call next week?

Not a fit? Reply 'no' and I won't follow up.
```

After the user's "yes", Claude saves the six as Gmail drafts and the founder
reads and sends them from Gmail. The reel's 40 emails would go out over two
days at the daily cap of 20. With no reply, `due
--today 2026-10-29` lists follow-up 1 on Thursday, Oct 29 (+3 business days),
and follow-up 2 would come on Wednesday, Nov 4 (+7 business days; with
`business_days: false` it is Monday, Nov 2). Maya replied on Oct 30: "What's
your take rate, and how do you guarantee the backup walker?" `inbox` labels it
Asked a question and the follow-ups stop. Claude answered from the plan ("15%
flat, no owner fee. Every walk is booked with a second walker on standby
within 1 mile.") and asked "Would Thursday at 10 work for 20 minutes?". Her
"Thursday 10am works. Send an invite." is Interested, and

```
closer.py book --id maya-chen --start "2026-11-05 10:00" --tz America/New_York --link https://meet.google.com/abc-defg-hij
```

writes `seed/calls/maya-chen.ics`: "Leashly × Northlight Ventures · Intro
call", DTSTART 20261105T150000Z, DTEND 20261105T153000Z (10:00 to 10:30 AM
Eastern; the clocks went back on Nov 1, so it is UTC-05:00). The reel's
funnel, 40 sent, 12 replied, 5 interested, shows in `status` as drafted 40,
sent 40, replied 12 (30% of sent), interested 5, booked 1.

## What it never does

- Never sends an email or an invite, and never lets Claude send one: no
  `send_message`, no `reply`, no calendar guest. Every email waits in the
  user's Gmail Drafts for the user to send.
- Never drafts into Gmail without the user's yes for that batch; never "yes
  to everything from now on"; never from a background task.
- Never writes to anyone without a public source in their row, never guesses
  an email address, never collects a personal phone number or home address.
- Never emails a thread again after a no, an opt-out or a bounce.
- Never invents a fact in a personal line or a number in a reply.
- Never promises funding. The pack does the work; investors decide.
