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

Optional channel-subscription gate: set `REQUIRED_CHANNELS` and students must
join before answering.

**Mini App** (`/app/answer`, `/app/create`)

- Test-code prompt, then the answer sheet: `Test №6 – 45 ta savol`
- Multiple choice with 2–6 options per question, tap to select, tap again to clear
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

111 tests covering the Rasch engine (difficulty recovery against known values),
the three-scenario tables, answer normalisation, `initData` verification
including forgery attempts, the JSON store's durability and concurrency
guarantees, multiple accepted answers, and the full create → answer → score API
flow.

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
