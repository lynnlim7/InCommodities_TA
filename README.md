# Power Position Tool

A lightweight position-reporting tool for the trading desk of a Japanese electricity retailer. It reads a trade book, validates it as a complete snapshot, and calculates the desk's forward net power position by delivery area, netting every load profile into the hours it actually delivers.

The tool provides three forward-looking views from a fixed reporting date:

- next 7 days — one position per day;
- next 4 weeks — one position per calendar-week bucket;
- next 12 months — one position per calendar-month bucket.

The calculation core is intentionally independent of CSV parsing and Streamlit. External data is validated and normalized before it enters the domain, while configurable reference data and load-profile parameters are kept in YAML.

## Quick start

The project uses `uv` for dependency management and a `Makefile` as the developer interface.

### Run the application
From the repository root:
`make setup`
`make run`

`make setup` installs the locked dependencies from `uv.lock` and `make run` starts the Streamlit dashboard.

### Verify the implementation 
Run the complete test suite with: 
`make check`

### Available commands

| Command | Purpose |
|---|---|
| `make setup` | Install the locked project dependencies. |
| `make run` | Start the Streamlit dashboard. |
| `make test` | Run the full pytest suite. |
| `make lint` | Run Ruff checks. |
| `make typecheck` | Run mypy. |
| `make check` | Run tests, linting, and type checking. |
| `make help` | Show the available targets. |

The assessment reporting date is **1 October 2026**. The application should use this date as the default `as_of` date for the required views rather than deriving business results implicitly from the machine clock.

## Business interpretation

The tool answers the operational question: **for each configured area, how many MW and MWh is the desk long or short over each upcoming reporting period, and is it long or short in every hour of it?**

A positive position is long and a negative position is short. Buy trades contribute positively and Sell trades negatively.

Every trade is first placed on its area's **hourly net position curve**: the desk's signed net MW in every delivery hour of the reporting horizon. A trade adds its signed MW to each hour its load profile delivers between its start and end dates, so Base and Peak trades net in the hours they share. Every reported number is then read off that curve:

```text
Net MWh      =  Σ net MW over the hours in the reporting period

                       net MWh
Net MW       =  ─────────────────────
                 hours in the period

```

- **Net MWh** is the signed energy actually delivered into the period. It is cumulative, so it answers "how much energy is the desk committed to", and it is additive across trades: the per-trade MWh in the drill-down sum to the reported period total.
- **Net MW** expresses that same energy as the period's average rate of power. It keeps periods of different lengths comparable and makes a trade covering a whole period report its own contractual MW.


Because MWh is the numerator of MW, the two readings always agree on direction and can never drift apart. They answer different questions, not different calculations. A 10 MW buy covering only 1 → 15 October commits the desk to 10 × 336 = 3,360 MWh outright, while for the month as a whole it reads as 3,360 / 744 ≈ 4.52 MW, diluted over the October hours it does not cover.

## Assumptions and business rules

| # | Rule / assumption |
|---|---|
| 1 | **Sign convention.** Buy is positive/long; Sell is negative/short, in both reported units. |
| 2 | **Timezone.** All delivery dates, reporting boundaries, and profile hours are interpreted in Japan Standard Time (JST / `Asia/Tokyo`). |
| 3 | **Date representation.** The supplied data is date-level and Japan has no daylight-saving time, so the core uses `date` rather than timezone-aware `datetime`. |
| 4 | **Delivery intervals are half-open.** `[start_date, end_date)` includes the start date and excludes the end date. For example, an October trade represented as `2026-10-01` to `2026-11-01` delivers through 31 October. |
| 5 | **Daily view.** The next 7 days start on the `as_of` date. |
| 6 | **Weekly convention.** Weeks are Monday-Sunday JST calendar weeks. The first bucket is clipped to the `as_of` date so the view remains forward-looking; subsequent buckets are full Monday-Sunday weeks. |
| 7 | **Monthly convention.** Months are calendar months. The first bucket is clipped to the `as_of` date when necessary; subsequent buckets are full calendar months. |
| 8 | **Load profiles net into shared hours.** Base and Peak are different delivery shapes, so each trade lands only on the hours its profile delivers, and trades on different profiles net hour by hour. Positions are keyed by area and reporting period, so a Base long and an equal Peak short net to flat in Peak hours rather than being reported as two unrelated numbers. |
| 9 | **Base delivery.** A continuous/Base-style profile delivers 24 hours per applicable Japanese calendar day. |
| 10 | **Peak delivery.** The current Peak configuration is 08:00-20:00 on configured Monday-Friday delivery days, including public holidays as the brief specifies. The hourly-window behaviour itself supports any configured day of the week. |
| 11 | **Product labels are descriptive.** The engine does not parse strings such as `Oct-26 Base` to derive delivery. Structured `start_date`, `end_date`, and `load_profile` fields are authoritative. |
| 12 | **Every supplied row is treated as active.** No amendment, cancellation, or version semantics are inferred because the input does not provide them. |
| 13 | **Price is input metadata, not a position driver.** It is validated at the CSV boundary but is not used to calculate physical MW exposure. |
| 14 | **Invalid input fails the run.** The application does not calculate from a partial trade book because a plausible-looking position with missing exposure could lead to an incorrect hedge. |
| 15 | **Configured reference data is authoritative.** A trade referencing an unsupported area, trade type or load profile fails rather than disappearing from the report. Trade types are validated against `trade_types.yaml` but do not alter the position formula. |
| 16 | **Zero positions are explicit.** The calculation builds deterministic rows for every configured area and period combination so zero exposure can be distinguished from missing calculation output. A block with no hours in a period (Peak on a Saturday) is shown as a dash rather than as flat. |
| 17 | **Reporting units.** Each period reports net MW and net MWh from one signed MW-hour total. MWh is the energy delivered into that period only; it is not a running cumulative total across periods, so the periods of one view never double-count a long-dated trade. |
| 18 | **Displayed precision.** MW is shown at two decimal places and MWh at whole units. Energy totals run into the thousands, where a fractional part is not actionable. Rounding is half-up and applies to presentation only; the stored values stay exact `Decimal`. |
| 19 | **Curve resolution.** The curve is hourly. Every current profile is a whole-hour shape on JST calendar days, so an hour is the finest resolution any trade can change. |
| 20 | **Direction.** A row is LONG (green), SHORT (red) or FLAT from the sign of its net position, read before rounding. |

No Japanese public-holiday calendar is needed for Peak delivery: the brief defines Peak as Monday to Friday including public holidays.

## Architecture

The tool separates external representation, configurable variation, business behaviour, and presentation.

```text
                         config/
          ┌────────────────┼─────────────────┐
          │                │                 │
     areas.yaml      trade_types.yaml  load_profiles.yaml
          │                │                 │
          └────────── Pydantic schemas ──────┘
                           │
                           └──── profile configuration
                                      │
                                      ▼
                                ProfileRegistry
                                      │
                                      │
trades.csv                            │
    │                                 │
    ▼                                 │
infrastructure/CsvTradeRepository     │
    │                                 │
    ├─ CSV/header validation          │
    ├─ aggregate row errors           │
    ├─ CsvTradeRow (Pydantic)         │
    └─ normalize to domain Trade      │
    │                                 │
    ▼                                 │
 TradeBook ───────────────────────────┤
    │                                 │
    └──────────────┐                  │
                   ▼                  ▼
              core/calculations.py
                   │
                   ├─ core/curve.py: hourly net MW curve per area
                   │    (daily steps → running sum → profile hours)
                   ├─ net MWh and net MW per period
                   └─ deterministic aggregation
                   │
                   ▼
             tuple[Position, ...]
                   │
                   ▼
             dashboard/app.py
                Streamlit
```

### Responsibilities

| Module | Responsibility |
|---|---|
| `core/models.py` | Stable domain concepts: trade direction, delivery periods, normalized trades, trade books, reporting periods, and positions. |
| `core/profiles.py` | Load-profile behaviour: which hours a profile delivers on a day and in an interval, for continuous delivery and configured hourly windows. |
| `core/curve.py` | Builds the hourly net MW curve per area and summarises it over any period and set of hours. |
| `core/periods.py` | Generates daily, weekly, and monthly forward reporting periods. |
| `core/calculations.py` | Reads each area's position for each reporting period off its curve: net MWh and net MW. Also explains a position trade by trade. |
| `config/schema.py` | Pydantic contracts for areas, trade types, and load-profile YAML. |
| `config/loader.py` | Generic YAML loading and schema validation. |
| `config/profiles.py` | Converts validated profile configuration into domain profile behaviour. |
| `infrastructure/schemas.py` | External CSV row contract and parsing into typed values. |
| `infrastructure/csv_repository.py` | Reads CSV, validates the complete book, and returns a normalized `TradeBook`. |
| `infrastructure/errors.py` | Actionable source and row-validation errors. |
| `dashboard/app.py` | Application composition and Streamlit presentation; it should not duplicate business calculations. |

The dependency direction is intentionally simple: outer adapters/configuration may depend on the core, while the core does not depend on CSV, YAML, Pydantic, or Streamlit.

## Key design decisions

### 1. Structured trade fields drive the calculation

The engine uses normalized fields such as `area`, `buy_sell`, `load_profile`, `start_date`, `end_date`, and `volume_mw`. It does not infer business behaviour by parsing the human-readable `product` string.

This keeps calculation behaviour stable if product naming conventions change and avoids maintaining two competing representations of delivery semantics.

### 2. CSV validation is an application boundary

`CsvTradeRepository` owns the CSV-specific workflow:

```text
CSV strings
    → CsvTradeRow validation
    → aggregate validation errors
    → domain Trade
    → TradeBook
```

Pydantic is used for untrusted external data; the core receives typed domain objects rather than CSV/Pydantic models. Direction is parsed into the domain `BuySell` enum at this boundary so invalid values such as `B`, `buy`, or `Purchase` are reported with the rest of the row errors instead of failing later during calculation.

The repository reports all row-validation problems in one pass and rejects the book if any exist.

### 3. Configuration describes variation; Python implements behaviour

YAML is used for reference data and parameters expected to vary:

- supported areas;
- supported trade types;
- available load profiles;
- profile type;
- profile hours and applicable days.

Typed Python owns behaviour that should be explicit and tested:

- Buy/Sell sign semantics;
- half-open interval intersection;
- reporting-period generation;
- delivery-hour calculation;
- the hourly net position curve and the arithmetic read off it;
- domain invariants.

This avoids turning YAML into a business-rules programming language.

### 4. Load profiles are the deliberate extension point

The position engine does not contain branches such as `if profile == "Peak"`. Instead it asks the configured profile behaviour which hours it delivers on each day, and places the trade on exactly those hours of the curve.

Adding another profile that can be represented by an existing behaviour is configuration-only. A fundamentally different delivery shape requires a new typed profile implementation, while the central position aggregation remains unchanged.

### 5. Area and trade type are configured reference data

Areas and trade types are strings rather than hard-coded enums because the brief expects the supported universe to grow. YAML therefore defines what is currently supported without requiring changes to the core domain model.

An unsupported area fails explicitly instead of being silently omitted. This is important because silently dropping a trade can produce a plausible but incorrect flat position.

Trade type is validated reference data: a trade whose type is not in `trade_types.yaml` (for example a `Swap`) fails the run with `UnsupportedTradeTypeError`, exactly like an unsupported area. It is deliberately not part of the aggregation key because the current business requirement is the desk's net physical position, not a breakdown by source trade type. Future trade types with different source representations should normalize into the same domain `Trade` semantics where possible.

### 6. Both MW and MWh are reported, from one signed MW-hour total

MW is a rate of power, not a cumulative quantity. A 10 MW trade covering half of a monthly bucket and a 5 MW trade covering the other half must not be reported as 15 MW for the month. MWh is the cumulative quantity, and those same two trades genuinely do add up in energy terms.

The desk needs both: MW to compare periods of different lengths and to size a hedge, MWh to see the energy the book is actually committed to. Reporting only one of them would answer half of the morning question.

The engine therefore sums the hourly curve over each period. That sum *is* the net MWh; dividing it by the hours in the period gives the net MW. There is no second calculation to keep in step, which is why the units cannot contradict each other.

For example, for October Base:

```text
Buy 10 MW: 1 Oct → 15 Oct = 336 hours
Buy  5 MW: 15 Oct → 1 Nov = 408 hours
October hours                  = 744 hours

net MWh  = 10 × 336 + 5 × 408
         = 5,400 MWh

net MW   = 5,400 / 744
         ≈ 7.258 MW
```

The half-open interval convention means the two trades meet at 15 October without overlapping.

The drill-down follows the same rule. Contractual MW cannot be summed down a column, so each contributing trade is shown with the hours that weighted it and its signed MWh — and those MWh reconcile exactly to the period total above them.

### 7. Positions are read off one hourly net curve per area

An average over a period answers "how much", but not "in which hours". Two cases made that matter:

- **Shape inside a period.** Buy 10 MW for a week and sell 20 MW for its weekend: the week averages +4.29 MW, but the desk is 10 MW short in every weekend hour. Only an hourly view can see that, so each period also carries its shortest and longest hour for any view that needs to surface it.
- **Profiles that share hours.** Long 10 MW Base and short 10 MW Peak is flat in Peak hours and +10 MW in every other hour. Reported as two separate per-profile positions it reads +10 and −10.

So every trade is placed once on an hourly curve per area, and every period is a read of that curve. The curve is built in two linear passes rather than by expanding each trade into its own hourly rows:

```text
1. per (area, profile): +MW on the day a trade starts, −MW on the day it ends
   running sum            → that profile's net MW on every day
2. per day: add that MW to the hours the profile delivers that day
```

The cost is proportional to trades plus hours, not trades times hours. A one-year horizon is 8,760 hours per area, so all nine Japanese areas are under 80,000 values however many trades or how long-dated. 100,000 synthetic trades across nine areas and three profiles calculate in about 0.3 seconds, and any new horizon or bucket shape is just another read of the same curve.

### 8. `Decimal` is used for trade quantities

CSV numeric values are parsed to `Decimal` and position arithmetic remains in `Decimal`. This avoids introducing binary floating-point artefacts into quantities used to report trading exposure.

The trade-off is lower arithmetic throughput than native floats, which is acceptable for the current calculation size and keeps the implementation explicit.

### 9. Streamlit is a thin presentation layer

The dashboard is not another business-logic layer. Its role is to compose configuration, load the trade book, request the three reporting views, and present `Position` results in a form a trader can scan quickly. It reads both units off the calculated `Position` and only formats them; it never derives one unit from the other.

The dashboard is laid out for a morning read in under a minute. Each row shows the delivery period, the Net Position (MW) with a word for its direction (LONG, SHORT or FLAT) and a matching row colour, and the Net Position (MWh) beside it. Areas sit side by side so the same delivery period can be compared across areas on one line.

Keeping the calculation outside Streamlit makes the core independently testable and allows the presentation layer to be replaced without rewriting position logic.

## Error handling

The application distinguishes source failures from invalid records.

- `TradeSourceError` represents an unusable source, such as a missing file, directory path, unreadable encoding, or invalid CSV structure/header.
- `RowError` represents one actionable row-level validation problem and records the CSV line, trade ID when available, field, value, and reason.
- `TradeBookValidationError` aggregates row errors so the user can correct the book in one pass.
- Domain reference errors `UnsupportedAreaError`, `UnsupportedTradeTypeError` and `UnsupportedProfileError` prevent unsupported trades from being silently omitted from, or silently included in, the reported position.

Duplicate IDs are detected from the raw trade ID before successful row parsing. This means a duplicate can still be reported even if another field on the same row is invalid.

The guiding policy is **fail the complete run rather than calculate a partial book**.

## Testing strategy

The test suite is intentionally weighted toward unit tests because the highest-risk behaviour is deterministic business logic rather than framework integration.

The main unit-test areas are:

- Buy/Sell sign semantics;
- half-open interval overlap and intersection;
- daily, weekly, and monthly period boundaries;
- continuous and hourly-window profile hours, and that a profile's daily hours agree with its interval hours;
- the hourly curve: each profile on exactly its hours, trades stepping on and off at their boundaries, clipping to the horizon;
- full-period Buy and Sell positions in both MW and MWh;
- the MWh-to-MW relationship, so the two reported units stay pinned together;
- partial-period time weighting, where the two units deliberately diverge;
- adjacent trades, whose MW cannot be summed but whose MWh must;
- per-trade MWh contributions reconciling to the reported period total;
- overlapping Buy/Sell exposure;
- trades outside a reporting period;
- separation of areas, and netting of Base and Peak trades into shared hours;
- the shortest and longest hour of a period, which expose short hours inside a period that averages long;
- overlapping views (days, weeks, months) reconciling as reads of one curve;
- unsupported reference data;
- CSV structure, row validation, duplicate IDs, and direction parsing;
- YAML-to-profile configuration translation;
- signed MW and whole-MWh display formatting, including rounding at zero;
- long/short/flat classification from the unrounded net position.

A lightweight integration test verifies the important application path:

```text
CSV
 → CsvTradeRepository
 → TradeBook
 → calculate_positions
 → expected Position
```

A second integration test runs the shipped trade book and configuration through the snapshot and checks the hand-calculated Tokyo October position: +23,616 MWh and +31.74 MW, with hours ranging from +22 to +40 MW.

## Extensibility

The architecture is designed so common growth paths have a narrow change surface.

| Change | Expected impact |
|---|---|
| Add another Japanese area | Add it to `areas.yaml`; no calculation branch required. |
| Add another supported trade type with the same normalized semantics | Add reference configuration and normalize the source representation if necessary; aggregation is unchanged. |
| Add a profile using an existing profile behaviour | Configuration-only. |
| Add a fundamentally new delivery shape | Add a new typed profile implementation and configuration mapping; aggregation remains unchanged. |
| Change reporting horizon | Change/generate reporting periods; trade and profile semantics remain unchanged. |
| Replace CSV with API/database/ETRM ingestion | Add/replace an outer adapter that produces the same normalized domain `TradeBook`. |
| Increase scale further | Curves are independent per area, so they can be built in parallel or kept and updated incrementally as trades arrive, without changing the domain or dashboard contracts. |


## Limitations and deliberate omissions

The following are outside the current brief and are intentionally not inferred:

- no amendment, cancellation, or trade-version lifecycle because the CSV has no such fields;
- no Japanese holiday calendar, since the brief defines Peak as including public holidays;
- no intraday `as_of` timestamp or partial-day exposure treatment;
- no P&L or valuation calculation;
- no running cumulative MWh across reporting periods; each period reports the energy delivered into itself, so a view's rows are not summed vertically;
- no persistence or live market-data ingestion;
- no authentication or authorization;
- no exchange-specific contract-size or futures normalization until such a source is defined;
- no sub-hourly (e.g. 30-minute) curve resolution until a product needs it;
- no row quarantine/partial-book calculation;

These would require explicit business or operational requirements rather than assumptions in the position engine.



