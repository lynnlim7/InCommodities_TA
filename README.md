# Power Position Tool

A lightweight position-reporting tool for the trading desk of a Japanese electricity retailer. It reads a trade book, validates it as a complete snapshot, and calculates the desk's forward net power position by delivery area and load profile.

The tool provides three forward-looking views from a fixed reporting date:

- next 7 days — one position per day;
- next 4 weeks — one position per calendar-week bucket;
- next 12 months — one position per calendar-month bucket.

The calculation core is intentionally independent of CSV parsing and Streamlit. External data is validated and normalized before it enters the domain, while configurable reference data and load-profile parameters are kept in YAML.

## Quick start

The project uses `uv` for dependency management and a `Makefile` as the developer/interviewer interface.

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

The tool answers the operational question: **for each configured area and load profile, how long or short is the desk over each upcoming reporting period?**

A positive position is long and a negative position is short. Buy trades contribute positively and Sell trades negatively.

Trade volumes are supplied in MW, so positions are reported in **MW**. For reporting buckets longer than the exact delivery of a trade, the result is a time-weighted average signed MW over the delivery hours applicable to that load profile:

```text
                 Σ(signed trade MW × applicable overlap hours)
Net position =  ───────────────────────────────────────────────
                    profile hours in the reporting period
```

MW-hours are therefore used implicitly as the weighting numerator, but the reported position remains MW. The tool does not present cumulative MWh as the desk position.

## Assumptions and business rules

| # | Rule / assumption |
|---|---|
| 1 | **Sign convention.** Buy is positive/long; Sell is negative/short. |
| 2 | **Timezone.** All delivery dates, reporting boundaries, and profile hours are interpreted in Japan Standard Time (JST / `Asia/Tokyo`). |
| 3 | **Date representation.** The supplied data is date-level and Japan has no daylight-saving time, so the core uses `date` rather than timezone-aware `datetime`. |
| 4 | **Delivery intervals are half-open.** `[start_date, end_date)` includes the start date and excludes the end date. For example, an October trade represented as `2026-10-01` to `2026-11-01` delivers through 31 October. |
| 5 | **Daily view.** The next 7 days start on the `as_of` date. |
| 6 | **Weekly convention.** Weeks are Monday-Sunday JST calendar weeks. The first bucket is clipped to the `as_of` date so the view remains forward-looking; subsequent buckets are full Monday-Sunday weeks. |
| 7 | **Monthly convention.** Months are calendar months. The first bucket is clipped to the `as_of` date when necessary; subsequent buckets are full calendar months. |
| 8 | **Load profiles remain separate.** Base and Peak represent different delivery shapes and are not collapsed into one number. Positions are therefore keyed by area, load profile, and reporting period. |
| 9 | **Base delivery.** A continuous/Base-style profile delivers 24 hours per applicable Japanese calendar day. |
| 10 | **Peak delivery.** The current Peak configuration is 08:00-20:00 on configured Monday-Friday delivery days. The hourly-window behaviour itself supports any configured day of the week. |
| 11 | **Product labels are descriptive.** The engine does not parse strings such as `Oct-26 Base` to derive delivery. Structured `start_date`, `end_date`, and `load_profile` fields are authoritative. |
| 12 | **Every supplied row is treated as active.** No amendment, cancellation, or version semantics are inferred because the input does not provide them. |
| 13 | **Price is input metadata, not a position driver.** It is validated at the CSV boundary but is not used to calculate physical MW exposure. |
| 14 | **Invalid input fails the run.** The application does not calculate from a partial trade book because a plausible-looking position with missing exposure could lead to an incorrect hedge. |
| 15 | **Configured reference data is authoritative.** A trade referencing an unsupported area or load profile fails rather than disappearing from the report. Trade types are also configuration/reference data and do not currently alter the position formula. |
| 16 | **Zero positions are explicit.** The calculation builds deterministic rows for configured area/profile/period combinations so zero exposure can be distinguished from missing calculation output. |

No Japanese public-holiday adjustment is inferred for Peak delivery because the supplied requirements do not define holiday treatment.

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
                   ├─ interval intersection
                   ├─ profile-aware delivery hours
                   ├─ signed MW weighting
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
| `core/profiles.py` | Load-profile behaviour such as continuous delivery and configured hourly windows. |
| `core/periods.py` | Generates daily, weekly, and monthly forward reporting periods. |
| `core/calculations.py` | Pure position aggregation over normalized trades and reporting periods. |
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
- time-weighted position arithmetic;
- domain invariants.

This avoids turning YAML into a business-rules programming language.

### 4. Load profiles are the deliberate extension point

The position engine does not contain branches such as `if profile == "Peak"`. Instead it asks the configured profile behaviour for applicable delivery hours within an interval.

Adding another profile that can be represented by an existing behaviour is configuration-only. A fundamentally different delivery shape requires a new typed profile implementation, while the central position aggregation remains unchanged.

### 5. Area and trade type are configured reference data

Areas and trade types are strings rather than hard-coded enums because the brief expects the supported universe to grow. YAML therefore defines what is currently supported without requiring changes to the core domain model.

An unsupported area fails explicitly instead of being silently omitted. This is important because silently dropping a trade can produce a plausible but incorrect flat position.

Trade type is currently validated/reference metadata. It is deliberately not part of the aggregation key because the current business requirement is the desk's net physical position, not a breakdown by source trade type. Future trade types with different source representations should normalize into the same domain `Trade` semantics where possible.

### 6. Time-weighted MW rather than summing MW across time

MW is a rate of power, not a cumulative quantity. A 10 MW trade covering half of a monthly bucket and a 5 MW trade covering the other half should not be reported as 15 MW for the month.

The calculation therefore weights each signed MW exposure by its applicable delivery hours and divides by the profile hours in the reporting period.

For example, for October Base:

```text
Buy 10 MW: 1 Oct → 15 Oct = 336 hours
Buy  5 MW: 15 Oct → 1 Nov = 408 hours
October Base hours             = 744 hours

position = (10 × 336 + 5 × 408) / 744
         ≈ 7.258 MW
```

The half-open interval convention means the two trades meet at 15 October without overlapping.

### 7. Simple O(T × P) aggregation is intentional

For each trade, the engine checks its overlap with each requested reporting period. With the required views there are only 23 periods (`7 + 4 + 12`), so 100,000 trades imply roughly 2.3 million trade/period overlap checks before the small amount of profile-hour arithmetic.

This is preferable for the tool to expanding long-dated trades into hourly rows, which would increase memory use dramatically and obscure the business logic.

A more sophisticated interval index, vectorized implementation, or pre-aggregation layer can replace the calculation implementation later if measured production requirements justify it. The domain and presentation contracts do not need to change first.

### 8. `Decimal` is used for trade quantities

CSV numeric values are parsed to `Decimal` and position arithmetic remains in `Decimal`. This avoids introducing binary floating-point artefacts into quantities used to report trading exposure.

The trade-off is lower arithmetic throughput than native floats, which is acceptable for the current calculation size and keeps the implementation explicit.

### 9. Streamlit is a thin presentation layer

The dashboard is not another business-logic layer. Its role is to compose configuration, load the trade book, request the three reporting views, and present `Position` results in a form a trader can scan quickly.

Keeping the calculation outside Streamlit makes the core independently testable and allows the presentation layer to be replaced without rewriting position logic.

## Error handling

The application distinguishes source failures from invalid records.

- `TradeSourceError` represents an unusable source, such as a missing file, directory path, unreadable encoding, or invalid CSV structure/header.
- `RowError` represents one actionable row-level validation problem and records the CSV line, trade ID when available, field, value, and reason.
- `TradeBookValidationError` aggregates row errors so the user can correct the book in one pass.
- Domain reference errors such as `UnsupportedAreaError` and `UnsupportedProfileError` prevent unsupported trades from being silently omitted from the reported position.

Duplicate IDs are detected from the raw trade ID before successful row parsing. This means a duplicate can still be reported even if another field on the same row is invalid.

The guiding policy is **fail the complete run rather than calculate a partial book**.

## Testing strategy

The test suite is intentionally weighted toward unit tests because the highest-risk behaviour is deterministic business logic rather than framework integration.

The main unit-test areas are:

- Buy/Sell sign semantics;
- half-open interval overlap and intersection;
- daily, weekly, and monthly period boundaries;
- continuous and hourly-window profile hours;
- full-period Buy and Sell positions;
- partial-period time weighting;
- adjacent trades;
- overlapping Buy/Sell exposure;
- trades outside a reporting period;
- separation of areas and load profiles;
- unsupported reference data;
- CSV structure, row validation, duplicate IDs, and direction parsing;
- YAML-to-profile configuration translation.

A lightweight integration test verifies the important application path:

```text
CSV
 → CsvTradeRepository
 → TradeBook
 → calculate_positions
 → expected Position
```

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
| Increase scale beyond the simple overlap algorithm | Replace/optimize the calculation implementation while preserving domain and dashboard contracts. |


## Limitations and deliberate omissions

The following are outside the current brief and are intentionally not inferred:

- no amendment, cancellation, or trade-version lifecycle because the CSV has no such fields;
- no Japanese holiday calendar for Peak delivery;
- no intraday `as_of` timestamp or partial-day exposure treatment;
- no P&L or valuation calculation;
- no persistence or live market-data ingestion;
- no authentication or authorization;
- no exchange-specific contract-size or futures normalization until such a source is defined;
- no hourly expansion of long-dated trades;
- no row quarantine/partial-book calculation;

These would require explicit business or operational requirements rather than assumptions in the position engine.



