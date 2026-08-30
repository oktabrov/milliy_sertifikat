# Milliy sertifikat test bot

A Telegram bot and Mini App for running Uzbek national-certificate style tests:
students enter a test code, fill in an answer sheet (35 multiple-choice
questions plus a short-answer block with a maths keyboard), and get a result
scored with a **Rasch (RASH) model against three simulated cohorts**.

Interface language is Uzbek (Latin).

---

## What it does

**Bot**

| Command / button | Behaviour |
|---|---|
| `/start` | Asks for name and surname in Latin script, then greets the student |
| `/edit` | Change the stored name |
| `/info` | How the bot works and how results are calculated |
| `/ms` | Milliy sertifikat section: **Test tekshirish**, **Test yaratish**, **Mening natijalarim**, **Mening testlarim** |
| `/testlarim` | Tests you authored, with participant counts and close/reopen buttons |
| `/natijalarim` | Your results |
| `/stats`, `/broadcast` | Admin only |
| `/special` | Admin only — lists every admin-only command |

### Administrators

| Command | |
|---|---|
| `/id` | anyone can look up their own Telegram id |
| `/adminlar` | list admins and where each came from |
| `/admin_qoshish 123456789` | add an admin |
| `/admin_ochirish 123456789` | remove one |

To promote someone: they send `/id` to the bot, give you the number, you run
`/admin_qoshish <number>`. They are notified straight away. Forwarding one of
their messages and replying `/admin_qoshish` also works, unless their privacy
settings hide the original sender.

Admins come from three places and `/adminlar` labels each:

- **owner** — the built-in id, permanent, so the bot can never be left with no
  administrator
- **env** — `ADMIN_IDS` in `.env`, the deploy-time record; removing one means
  editing that file
- **runtime** — added with `/admin_qoshish`, removable the same way

### Intro video

The **"Botda test ishlash va yaratish(+video)"** button is managed by admins
inside the bot — no `.env` edit, no restart:

| Command | |
|---|---|
| `/video` | shows how to add one |
| `/video` (reply to a video) | store that video; pressing the button sends it into the chat |
| `/video https://…` | point the button at a link instead; it opens directly |
| `/video_ochirish` | remove the video again |

A link set this way wins over a stored video, and whatever was set last wins
over `.env`: `HELP_VIDEO_URL` / `HELP_VIDEO_FILE_ID` are only fallbacks for
when nothing has been configured at runtime. With no video anywhere, the
button replies "📹 Video hozircha qo'shilmagan."

### Required channels

Students can be made to join one or more channels before answering. Admins
manage the list from inside the bot — no `.env` edit, no restart:

| Command | |
|---|---|
| `/kanallar` | list the channels, each with a 🗑 button |
| `/kanal_qoshish @kanal` | add one (accepts `@name`, `t.me/name`, or a `-100…` id) |
| `/kanal_ochirish @kanal` | remove one |
| `/kanal_tozalash` | remove all — no gate |

Zero, one, or many channels are all valid. Adding is **validated against
Telegram first**: the channel must exist and the bot must be an administrator
in it. That check matters because the gate deliberately fails open — a channel
the bot cannot query is treated as joined, so an unverified entry would look
like a restriction while letting everyone through.

`REQUIRED_CHANNELS` in `.env` only seeds the list the first time. After that
the stored value wins, *including when it is empty* — clearing the list means
"no gate", not "fall back to the environment".

**Every** required channel must be joined, not just one, and the check runs in
two places:

- the bot's dispatcher middleware, for commands and buttons
- **the Mini App API**, on every `/api/*` call

The second is not redundant. Tapping a Mini App button opens a web page whose
requests go straight to `/api/*` — the bot's dispatcher never sees them — so a
gate enforced only in handlers would let an unsubscribed user answer tests
through the menu button.

The check **fails closed**: a channel that cannot be verified counts as not
joined, after one retry to absorb a transient error. Failing open would mean a
bot quietly removed as channel admin stops enforcing anything at all.

Admins are gated like everyone else, so the owner sees what a student sees. Only
the channel commands are exempt, so a mistyped channel can always be undone.
`ADMIN_IDS` adds to a built-in owner id rather than replacing it, so the bot can
never end up with no administrator.

**Mini App** (`/app/answer`, `/app/create`)

- Test-code prompt, then the answer sheet: `Test №6 – 45 ta savol`
- Fixed paper shape: **35 closed questions with four options each, questions
  33–35 with six (A–F), then 10 short-answer questions** — the builder asks
  only for a title, subjects and an optional code
- Multiple-choice options are tap to select, tap again to clear
- Short-answer questions with parts **a)** and **b)**, using
  [MathLive](https://mathlive.io) for the four-tab maths keyboard
  (`123` / `∞≠∈` / `abc` / `αβγ`) — answers are stored as LaTeX
- A test builder for teachers that produces a shareable test code

### Several accepted answers per question

Students write the same value in different ways — `3/4`, `0.75`, `\frac{3}{4}`.
Normalisation catches the numeric cases, but not text or algebraic variants
(`ortadi` vs `oshadi`), so the author decides.

When building a test, each open part starts with one answer field and a
**"+ Yana javob qo'shish"** button. Add as many accepted forms as you like, up
to 20 per part; at least one is required, and extra rows can be removed. Blank
and duplicate entries are dropped on save.

A student's answer counts as correct if it matches **any** accepted form. The
answer sheet is unchanged — the student still sees exactly one field per part,
and the key is never sent to the browser.

Stored as:

```json
{"number": 36, "type": "open", "parts": {"a": ["3/4", "0.75"], "b": ["2"]}}
```

A bare string is still read as a single accepted answer, so keys authored
before this feature keep working.

---

## Scoring: three cohorts, three results

A real sitting has 50–100 students, which is far too few to calibrate 45–55
items or quote a percentile honestly. So every student is scored against three
**synthetic reference cohorts of 10,000** virtual participants:

| Scenario | Uzbek label | Ability distribution |
|---|---|---|
| `weak` | Zaif guruh | N(−1.2, 1) — most did poorly |
| `normal` | O'rtacha guruh | N(0.0, 1) — most did about average |
| `strong` | Kuchli guruh | N(+1.2, 1) — most did very well |

Each cohort is calibrated separately with JMLE, anchored so the *cohort's* mean
ability sits at zero. That anchoring is what produces question complexity "in
three types" — the same item comes out harder in a weak field and easier in a
strong one, because difficulty is only ever identified relative to the people
who sat the test. Measured on a 45-item paper:

```
weak    mean item difficulty  +1.25 logits   (items look harder)
normal  mean item difficulty   0.00 logits
strong  mean item difficulty  -1.23 logits   (items look easier)
```

A student scoring 30 of 55 therefore sees:

```
Stsenariy        Ball   Foiz    Daraja
Zaif guruh        74     91.4%    A+
O'rtacha guruh    54     59.2%    C+
Kuchli guruh      34     18.4%    —
```

The three numbers bracket where the student would land depending on how strong
the national field turns out to be.

**What the simulation does and does not buy you.** It does not discover
difficulty it was not given: recovered difficulties equal the seeded ones plus
the anchoring shift, up to sampling noise. What it provides is a smooth, stable
raw-score → ball → percentile mapping computed at N=10,000 instead of N=50, and
the cohort-strength bracketing above. Once `MIN_REAL_SUBMISSIONS` (default 20)
students have actually sat a test, item difficulties are re-estimated from
their real responses, the tables are rebuilt, and every earlier attempt is
rescored.

Implementation notes:

- Pure Python, no numpy or scipy — alwaysdata's free tier gives 100 MB of disk
- Under the dichotomous Rasch model everyone with the same raw score gets the
  same ability, so a 10,000 × 55 matrix collapses to 56 raw-score groups and
  JMLE iterates over those. All three tables build in ~0.2 s.
- JMLE over-disperses item difficulty on short tests (measured slope 1.19 at 8
  items, 1.03 at 45); the standard `(L−1)/L` correction is applied.

---

## Running it locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env      # then put your BOT_TOKEN in it
```

There is no database to install. Storage is three JSON files under `DATA_DIR`.

Set `USE_POLLING=true` in `.env` and start the app:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

The bot long-polls and the Mini App is served from the same process at
`http://127.0.0.1:8080/app/answer`.

The Mini App buttons need an HTTPS origin — Telegram refuses `web_app` buttons
over plain HTTP. For local testing against real Telegram, expose the port and
set `WEBHOOK_BASE` to the tunnel URL:

```bash
cloudflared tunnel --url http://localhost:8080
```

### Tests

```bash
.venv/bin/python -m pytest
```

179 tests covering the Rasch engine (difficulty recovery against known values),
the three-scenario tables, answer normalisation, `initData` verification
including forgery attempts, the JSON store's durability and concurrency
guarantees, multiple accepted answers, configuration precedence, and the full
create → answer → score API flow.

---

## Deploying

See [DEPLOY-alwaysdata.md](DEPLOY-alwaysdata.md). In production the bot runs in
**webhook** mode inside the same ASGI app that serves the Mini App, so there is
one process, one port and one certificate.

---

## Layout

```
app/
  main.py                  ASGI app: webhook + API + static
  config.py                environment settings
  store/
    models.py              User, Test, Attempt dataclasses
    json_store.py          atomic, lock-guarded JSON persistence
  bot/                     handlers, keyboards, Uzbek strings
  api/                     initData auth, test + submission endpoints
  scoring/
    rasch.py               1-PL model, JMLE, ability estimation
    scenarios.py           the three synthetic cohorts
    grader.py              answer normalisation and grading
  services/                where storage meets the model
  web/                     Mini App
tests/
```

`app/scoring/*` knows nothing about storage or Telegram, which is what makes it
directly testable.

## Storage

Three JSON files under `DATA_DIR`: `users.json`, `tests.json`, `attempts.json`.
No database, no ORM, no driver — which is also why the production virtualenv is
19 MB rather than 96 MB.

### Why pydantic is still here

It is not used for storage, and configuration is parsed by hand in
`app/config.py`. It stays because **aiogram requires it** —
`pydantic<2.14,>=2.4.1` — and every Telegram type is a pydantic model, so it
cannot go without replacing the Telegram library itself. That is 6.1 MB of the
19 MB and it is not removable.

Since pydantic is present regardless, FastAPI reuses it for request validation,
which makes FastAPI's own marginal cost about 900 KB.

The obvious hazard with JSON files is losing a write: two students submit in the
same second, both read the attempt list, both append, both save, and one result
disappears silently. Two things prevent it:

- **Atomic writes.** Each save goes to a temporary file in the same directory,
  is fsynced, then moved into place with `os.replace`. A crash mid-write leaves
  the previous file intact, never a truncated one.
- **A serialising lock.** Every mutation holds an `asyncio.Lock` across the
  whole read-modify-write cycle, so the interleaving above cannot occur. There
  is a test that fires 50 simultaneous submissions and asserts all 50 survive a
  reload, and another that double-taps submit and asserts exactly one attempt is
  created.

**Run a single worker.** The lock serialises within one event loop; two worker
processes would each hold their own copy of the data and clobber each other. The
deployment command in DEPLOY-alwaysdata.md starts one.

Back up by copying the directory — `data/` is gitignored, since it holds real
student answers.

---

## Security notes

- `.env` is gitignored; the bot token must never be committed
- Every Mini App API call verifies Telegram's `initData` HMAC — a forged or
  stale payload is rejected, which is the only thing stopping someone
  submitting answers as another student
- Answer keys are never sent to the answer sheet
- Open answers are evaluated with a whitelisted AST walker, never `eval`
