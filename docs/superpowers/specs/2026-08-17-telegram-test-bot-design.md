# Milliy sertifikat test bot — design

**Date:** 2026-08-17
**Status:** implemented

Rebuild of an Uzbek national-certificate test bot (`@matematikapromaxbot`,
"Matematika promax") observed in a screen recording, with a modified scoring
model.

## Source behaviour

From the recording:

- `/start` asks for name and surname in Latin script, then greets the student
  and offers three inline buttons (how to answer, how to create, help video)
- Command menu: `/edit`, `/info`, `/ms`, `/testlarim`
- `/ms` opens a reply keyboard: Test tekshirish, Test yaratish, Mening
  natijalarim, Mening testlarim
- Students must join a channel before answering
- "Test tekshirish" opens a Mini App: a test-code prompt, then an answer sheet
  headed `Test №6 – 45 ta savol` with a subject dropdown
- Questions 1–35 are multiple choice (4 options, some 6); 36–45 are short
  answer with parts a) and b), entered through a four-tab maths keyboard that
  renders LaTeX live
- Submission shows "✅ Sizning natijangiz qabul qilindi!"; the bot then offers
  "📊 Natijani ko'rish", which initially replies "Natija hisoblanmoqda"
  because the original scores on a cohort basis

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Scope | Full clone: answer, author, results, my tests, channel gate, admin | Matches the source |
| Language | Uzbek (Latin) only | Matches the source |
| Stack | aiogram 3 + FastAPI, SQLAlchemy async | Best-documented Telegram path; one process serves bot and Mini App |
| Hosting | alwaysdata | User's choice |
| Bot mode | Webhook, sharing the ASGI app | alwaysdata runs one command on one port; no separate worker to keep alive |
| Dependencies | No numpy/scipy | alwaysdata free tier is 100 MB |
| Maths input | MathLive | The recording's keyboard is MathLive's own four-tab layout |

## Architecture

One FastAPI app:

- `POST /webhook/<secret>` — aiogram updates
- `/api/*` — Mini App JSON, authenticated by `initData` HMAC
- `/app/*` — Mini App static files

`app/scoring/*` has no knowledge of SQLAlchemy or Telegram. `app/services/*` is
the only layer that knows about all three, which keeps the model directly
unit-testable.

### Data model

`users`, `tests`, `attempts`, `settings`. Questions and cached score tables are
JSON columns: a test is authored, read and scored as a whole document, and
nothing queries inside it. This also keeps one codebase working on SQLite
locally and PostgreSQL in production.

## Scoring

**Requirement:** with only 50–100 real students, produce item difficulty in
three variants — a cohort that did poorly, one that did normally, one that did
very well — and give every real participant three results accordingly.

**Design:**

1. Seed item difficulties. Default profile before real data (MC ramping −1.5 →
   +1.2 logits, open block offset +0.8); re-estimated by JMLE from real
   responses once 20 students have submitted.
2. Simulate three cohorts of 10,000, θ ~ N(−1.2, 1), N(0, 1), N(+1.2, 1), with
   a per-scenario RNG seed so results are reproducible.
3. Calibrate each cohort separately by JMLE, then anchor so the *cohort's* mean
   ability is zero. The identical item consequently calibrates harder in the
   weak cohort and easier in the strong one — this is the "three types of
   question complexity". Measured on 55 items: +1.25 / 0.00 / −1.23 logits.
4. Precompute a raw-score → {θ, ball, percentile, grade} table per scenario.
   Legitimate because under the dichotomous Rasch model ability depends only on
   the raw score given the item set. Cached as JSON on the test row.
5. At submission, look the raw score up in all three tables.

Ball is `50 + 16·θ` clamped to 0–100; grade bands A+ ≥ 70 down to C ≥ 46, all
configurable.

**Consequence:** results are instant. The reference population is synthetic, so
nothing waits for a cohort — the "Natija hisoblanmoqda" state only appears
during the one-off recalibration after the 20th real submission, which rescores
everyone who already submitted.

**Stated limitation:** simulation does not create information. Recovered
difficulties equal the seeded ones plus the anchoring shift, up to sampling
noise. The value is a stable raw → ball → percentile mapping at N=10,000
instead of N=50, plus cohort-strength bracketing. Documented in the module
docstring so it is not mistaken for real calibration data.

**Numerical notes:**

- Raw-score grouping collapses 10,000 × 55 to 56 groups; all three tables build
  in ~0.2 s.
- JMLE over-disperses difficulty on short tests (measured regression slope 1.19
  at 8 items, 1.07 at 20, 1.03 at 45). The standard `(L−1)/L` correction is
  applied, leaving residual slope within 4% at 8 items and under 1% at 45.
- Extreme scores use the conventional 0.3 raw-score adjustment.

## Answer normalisation

The sheet tells students not to write units. They do anyway, so answers are
canonicalised: LaTeX is reduced (`\frac{50}{3}` → `((50)/(3))`, `\cdot` → `*`,
`^{...}` → `**(...)`), unit words are stripped, then both sides are evaluated
numerically when possible and compared with a 1e-6 relative tolerance, falling
back to canonical string equality. Evaluation uses a whitelisted AST walker, not
`eval`.

## Error handling

- Webhook always returns 200; a handler exception is logged, never retried into
  a loop
- The channel gate fails open when membership cannot be read, so a
  misconfiguration does not lock everybody out
- Invalid or stale `initData` is a 401
- Duplicate submission, closed test and unknown code are surfaced as Uzbek
  messages in the Mini App
- The Mini App reads answers out of the DOM at submit time rather than trusting
  MathLive's `input` events, so a library change cannot silently drop answers

## Testing

81 tests: Rasch difficulty recovery against known values, ordering and centring
properties, the three-scenario invariants (weak > normal > strong for both
difficulty and ball), answer normalisation tables, `initData` forgery attempts,
and the full create → answer → score API flow.
