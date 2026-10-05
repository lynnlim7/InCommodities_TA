# Power Position Tool

A position tool for the trading desk of a Japanese electricity retailer. It reads the
trade book and shows how many MW and MWh the desk is long or short over the coming days,
weeks, and months, broken down by delivery area.

```bash
uv sync
uv run power-position --as-of 2026-10-01
```

## Overview

```
POWER POSITION   as of 2026-10-01 (Asia/Tokyo)
Source src/app/data/trades.csv   Trades 12   Areas Tokyo, Kansai
Sign Buy = positive = long, Sell = negative = short   Days 00:00-00:00 JST, end date exclusive

Where the book stands
┏━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Area   ┃        Next 7 days ┃        Next 4 weeks ┃       Next 12 months ┃
┡━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ Tokyo  │ +5,040 MWh  LONG ▲ │ +19,296 MWh  LONG ▲ │ +187,296 MWh  LONG ▲ │
│ Kansai │ +1,584 MWh  LONG ▲ │  +6,192 MWh  LONG ▲ │  +25,488 MWh  LONG ▲ │
└────────┴────────────────────┴─────────────────────┴──────────────────────┘
Changes of direction
  Kansai turns FLAT from LONG at 2027-01 (monthly)
```

The report is built to be read in under a minute. The headline answers the two questions a
trader asks first — where am I long or short over each horizon, and does any position
change direction inside one — and the three detail tables follow for the row worth
checking. `--layout matrix` pivots areas into columns for a desk trading all nine areas;
`--format json` emits the machine contract.

## Assumptions

The brief deliberately leaves several definitions open. These are the choices made, and
they are printed on every run as well as recorded here.

| # | Assumption |
|---|---|
| 1 | **Sign convention.** Buy is positive and long; Sell is negative and short. |
| 2 | **Day boundaries** fall at 00:00 JST. Japan has no daylight saving, so a delivery day is always 24 hours and no timezone arithmetic is performed. |
| 3 | **Delivery interval** is `[start_date, end_date)` — start inclusive, end exclusive, as the CSV documents. |
| 4 | **Daily view** includes the as-of day, because the tool is read each morning and the trader needs today's position in order to hedge it. |
| 5 | **Weeks run Monday to Sunday.** The current week is clipped at the as-of date, so already-delivered days are excluded; such rows are marked `*`. |
| 6 | **Monthly view** is the current month plus the following 11, with the current month clipped at the as-of date. For 1 October the month is already complete, so it is not marked partial. |
| 7 | **Net MWh is the canonical quantity.** It is additive across periods and is what the LONG/SHORT/FLAT label is derived from. |
| 8 | **Average MW** = Net MWh ÷ the period's wall-clock hours. It is a *time-weighted average*, not a constant exposure, which is why the column is never labelled just "MW". |
| 9 | **Every supplied row is an active trade.** The CSV has no status or version field, so no amendment or cancellation semantics are inferred. |
| 10 | **Product names are descriptive and never parsed.** Delivery comes only from `start_date`, `end_date`, and `load_profile`. A row labelled `Cal-30 Peak` with Base dates is treated as Base. |
| 11 | **Price is validated and retained but unused** in the physical position. |
| 12 | **Invalid input fails the run.** No partial position is produced. A partial book still looks like a complete position, and a position quietly missing trades can imply the wrong hedge. |
| 13 | **Zero-exposure rows are shown** for every area observed in the book, so FLAT is distinguishable from missing output. |

Two further choices worth stating: a volume of zero or less is rejected rather than treated
as a short (direction already carries the sign), and a price of zero or less is rejected as
invalid.

## Architecture

Four layers, with the dependency arrow only ever pointing inward.

```
 trades.csv ─▶ infrastructure/ ──┐                 ┌─▶ interfaces/console  (long | matrix)
                                  │                 │─▶ interfaces/json_out (machine)
            ┌─────────────────────▼──────────────┐  │
            │  services/position_service.py      │──┤
            │  build_views(repository, as_of)    │  │
            └─────────────────────┬──────────────┘  │
                                  │                 │
 ┌──────────── core/  no I/O, no clock, no framework ▼────────────────────┐
 │ interval · direction · position · profiles · trade                     │
 │ periods (reporting windows) · engine · results                         │
 └────────────────────────────────────────────────────────────────────────┘
```

| Layer | Responsibility |
|---|---|
| `core/` | The domain and the calculation. Pure, deterministic, no dependencies outside itself. |
| `infrastructure/` | Reading the trade book; reporting what could not be read. |
| `services/` | What a run *is*: load a book, then calculate the views. |
| `interfaces/` | The CLI and the two renderers. |

`tests/unit/test_architecture.py` enforces this rather than documenting it: it AST-parses
every `core/` module and fails if one imports an outer layer, a parsing or presentation
library, or reads the system clock.

## Key design decisions

### Decision 1 — one engine, O(n·m), written to be read

**Choice:** for each reporting period and each area, sum the signed MWh each trade delivers
in that period. The whole engine is ~40 lines and maps line-for-line onto the specified
formula `MWh = signedMW × coveredHours(trade, period)`.

**Reason:** a reviewer can confirm it is correct by reading it. Work is proportional to
trade/period intersections, never to delivery hours, so nothing is ever expanded to one row
per hour.

**Alternative:** collapse trades into constant-MW segments by accumulating `+MW` at each
start and `−MW` at each end, then integrate each segment against each period — `O(n + b log
b + s·m)`.

**Trade-off:** the segment approach is asymptotically better but introduces a
breakpoint/running-sum concept every future reader must re-derive. Measured at 100,000
trades across 9 areas the simple loop takes **~1.0 s** and scales linearly (8.9 / 9.2 /
10.2 µs per trade at 10k / 50k / 100k), so the complexity buys nothing at the sizes the
brief names. It is the documented next step if that ever stops being true.

### Decision 2 — `Decimal` through the domain, rounding only at the edge

**Choice:** parse volumes and prices to `Decimal` at the input boundary, aggregate in
`Decimal`, keep results unrounded, and round only in `interfaces/format.py`.

**Reason:** covered hours are integral, so `signed_mw × hours` is exact and Net MWh is
exact. An incorrect position can imply an incorrect hedge, so correctness outranks speed.

**Alternative:** `float64`, or a vectorised dataframe pipeline.

**Trade-off:** `Decimal` is roughly ten times slower than `float`, and this engine performs
the arithmetic n×m times rather than over a reduced set. The measurement above shows the
cost is affordable. `pandas` was removed from the dependencies for the same reason it was
never needed: a dataframe in an engine signature would put a parsing library inside the
core.

### Decision 3 — load profile as the one real abstraction

**Choice:** a `LoadProfile` protocol with a single method, `covered_hours(interval)`.
`BaseProfile` returns `days × 24`.

**Reason:** this is the only extension point the brief explicitly demands. A profile knows
nothing about direction, netting, areas, or reporting windows, so adding Peak means adding
one class and one registry entry — the netting and reporting arithmetic is untouched.
`test_profiles.py` proves it by declaring a new profile *inside the test module* and running
a full view through it.

**Trade-off:** intervals carry `date` boundaries, not `datetime`, because every boundary in
scope is 00:00 JST. An intraday as-of timestamp would widen this to `datetime` — a change
confined to profiles and window generators.

### Decision 4 — area and trade type are data, not code

**Choice:** area is a pure grouping dimension with no branch anywhere. `config.py` lists the
nine areas for display order only; an unlisted area is still valid and still calculated, and
sorts after the known ones. `trade_type` is validated metadata with no position effect.

**Reason:** a new area must not require a code change. Whether area names should be
restricted to an authoritative list is an open question, so configuration raises it rather
than code presuming it.

### Decision 5 — long format is the contract, matrix is the scanning aid

**Choice:** the console defaults to one row per area and period, which is the specified
column contract; `--layout matrix` pivots areas into columns. JSON is always long format.

**Reason:** at nine areas the long view is 63 rows per table, which defeats the one-minute
goal; the matrix is 7. But the matrix drops the written position label for width, so it
carries a glyph legend and points at the views that carry the full contract.

## Error handling

Failures are split by what the operator has to do about them.

| Exit | Meaning |
|---|---|
| `0` | Success. |
| `2` | The file was readable but its records are invalid (also Click's usage-error code). |
| `3` | The source itself is unusable: missing, a directory, empty, or wrong columns. |
| `1` | Unexpected. |

Every problem in a file is collected and reported in one pass, so it can be fixed in one
edit. Each report names the line, the trade, the field, the offending value, and the reason.

```
$ uv run power-position --as-of 2026-10-01 --input broken.csv
The trade book is not valid, so no position was produced.
broken.csv: 5 problem(s) in 3 of 3 row(s)
  line 2 (trade T001): volume_mw=-5 -- Input should be greater than 0
  line 3 (trade T002): area='' -- String should have at least 1 character
  line 3 (trade T002): load_profile=Peak -- unsupported load_profile 'Peak'; registered profiles are: Base
  line 3 (trade T002): end_date=2026-10-01 -- end_date must be after start_date 2026-11-01; ...
  line 4 (trade T001): trade_id=T001 -- duplicate trade_id, already used on line 2; ...
$ echo $?
2
```

Duplicate detection runs off the raw `trade_id` column rather than off successfully parsed
trades, so a duplicate still surfaces when the earlier row also failed for another reason.
Internal exceptions are never the only explanation shown; results go to stdout and
diagnostics to stderr, so a run can be piped into another tool.

## Performance and complexity

`O(n·m)` — n trades by m reporting periods (23 by default). Trades are bucketed by area
once, and trades disjoint from the whole reported window are discarded once up front.

| Trades | Time | Per trade |
|---|---|---|
| 10,000 | 0.09 s | 8.9 µs |
| 50,000 | 0.46 s | 9.2 µs |
| 100,000 | 1.02 s | 10.2 µs |

Nine areas, 23 periods, `Decimal` throughout; Python 3.13 on Apple Silicon. The brief states
no runtime target and none is claimed here — the figures are recorded so the complexity
claim can be checked.

## Limitations

Not built, because the brief does not ask for it and inventing it would mean answering
questions it deliberately leaves open:

- **No OTC-specific semantics.** A new trade type can be registered, but no position
  behaviour is attached, because none is defined.
- **No intraday as-of timestamp.** Partial-day treatment of the current delivery day is
  undefined and is not guessed at.
- **No Peak profile shipped.** The extension point exists and is tested; the supplied book
  is Base only.
- **No row quarantining.** The run fails on invalid input. Quarantining with a prominent
  incomplete-book warning is a reasonable operational policy but must be an explicit choice.
- **No persistence, authentication, P&L, valuation, or live ingestion.**

Open questions for a design discussion: whether shaped products need min/max hourly MW
alongside Average MW; how amended, cancelled, or versioned trades are represented; whether
area names should be restricted to an authoritative list and how that reference data is
maintained; and what refresh, latency, and availability targets apply in production.

## Getting started

1. Install dependencies. The project uses `uv`; exact versions are in `uv.lock`.

   ```bash
   uv sync
   ```

2. Run the application. `--as-of` is required: the core never reads the clock, so a run
   recorded in a terminal transcript can always be reproduced. Pass `--as-of today` to opt
   in to the system date explicitly.

   ```bash
   uv run power-position --as-of 2026-10-01
   uv run power-position --as-of 2026-10-01 --layout matrix
   uv run power-position --as-of 2026-10-01 --format json
   uv run power-position --help
   ```

3. Run the tests.

   ```bash
   uv run pytest                      # all
   uv run pytest -m unit              # core only: no filesystem, no clock
   uv run pytest -m "integration or e2e"
   ```

4. Code quality checks.

   ```bash
   uv run ruff check .
   uv run mypy
   ```

### Known environment issue

This checkout lives in iCloud-synced `~/Documents`. iCloud sets the macOS `UF_HIDDEN` flag
on files inside `.venv`, and CPython 3.13's `site.addpackage` skips hidden `.pth` files, so
uv's editable install can silently fail to put `src` on `sys.path`. The test suite is immune
because pytest is configured with `pythonpath = ["src"]`. If `uv run power-position` reports
`No module named 'app'`:

```bash
chflags nohidden .venv/lib/python3.13/site-packages/*.pth
```

The flag is re-applied each time uv reinstalls the project, so this may need repeating.

The same conditions can leave `.venv/bin/ruff` wedged in an unkillable I/O wait, where even
`ruff --version` hangs. A fresh copy outside the virtualenv works:

```bash
uvx ruff@0.14.14 check src tests --no-cache
```

The durable fixes for both are to exclude `.venv` from iCloud sync or to move the checkout
out of `~/Documents`.
