# Power Position Tool

A lightweight position-reporting tool for the trading desk of a Japanese electricity retailer. 

The application reads a trade book, validates the input, and calculates the forward net power positions by delivery area. It supports different load profiles and presents the results through a Streamlit dashboard designed for a quick morning view of the desk's exposure. 

The tool provides three forward-looking views from a fixed reporting date:

- next 7 days — one position per day;
- next 4 weeks — one position per calendar-week bucket;
- next 12 months — one position per calendar-month bucket.

Positions are reported in both MW and MWh, with positive values representing a long position and negative values representing a short position. 

## Quick start

### Prerequisites
- Python 3.13
- `uv`
- `make`

### Setup
Clone the repository and install the locked dependecies:
 ```bash
git clone <repository-url>
cd <repository>
make setup
 ```

Start the Streamlit dashboard:
```bash
make run
```

The application will be available at the local URL displayed by Streamlit.

### Verification
Run the complete test suite with: 
```bash
make check
```

## Business interpretation

The tool answers the operational question: **for each configured area, how many MW and MWh is the desk long or short over each upcoming reporting period, and is it long or short in every hour of it?**

Trades are converted into their applicable delivery hours according to their structured delivery dates and load profile. 

Trades with different delivery profiles net against one another only during the hours in which their delivery overlaps.

```text
Net MWh      =  Σ net MW over the hours in the reporting period

                       net MWh
Net MW       =  ─────────────────────
                 hours in the period

```

- **Net MWh** represents the total signed energy exposure within the period.
- **Net MW** expresses that exposure as an average rate of power across the reporting period, making periods of different lengths easier to compare.

The dashboard also provides trade level details so that reported positions can be reconciled to their contributing trades.

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
| 14 | **Fail closed on the file, isolate bad rows.** A structural or calculation failure stops the run. A bad row is quarantined, never silently ignored: it is listed with its reason, and every position it could have moved is explicitly marked incomplete. One malformed trade does not blind the desk. |
| 15 | **Configured reference data is authoritative.** A trade referencing an unsupported area, trade type or load profile is quarantined and reported rather than disappearing from the report. Trade types are validated against `trade_types.yaml` but do not alter the position formula. |
| 16 | **Zero positions are explicit.** The calculation builds deterministic rows for every configured area and period combination so zero exposure can be distinguished from missing calculation output. A block with no hours in a period (Peak on a Saturday) is shown as a dash rather than as flat. |
| 17 | **Reporting units.** Each period reports net MW and net MWh from one signed MW-hour total. MWh is the energy delivered into that period only; it is not a running cumulative total across periods, so the periods of one view never double-count a long-dated trade. |
| 18 | **Displayed precision.** MW is shown at two decimal places and MWh at whole units. Energy totals run into the thousands, where a fractional part is not actionable. Rounding is half-up and applies to presentation only; the stored values stay exact `Decimal`. |
| 19 | **Curve resolution.** The curve is hourly. Every current profile is a whole-hour shape on JST calendar days, so an hour is the finest resolution any trade can change. |
| 20 | **Direction.** A row is LONG (green), SHORT (red) or FLAT from the sign of its net position, read before rounding. |


## Architecture

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
adapters/CsvTradeRepository           │
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
                   ├─ core/curves.py: hourly net MW curve per area
                   │    (daily steps → running sum → profile hours)
                   ├─ net MWh and net MW per period
                   └─ deterministic aggregation
                   │
                   ▼
             tuple[Position, ...]
                   │
                   ▼
             dashboard/main.py
                Streamlit
```
The main design principle is that external representations should not determine business behaviour. 

CSV parsing and validation sits at the application boundary. The calculation core operates on normalized domain objects.

Configuration is used for reference data and parameters expected to vary, while calculation rules remain explicit, typed and tested in Python.


## Key design decisions

### Structured trade fields drive the calculation

The engine uses normalized fields such as `area`, `buy_sell`, `load_profile`, `start_date`, `end_date`, and `volume_mw`. It does not infer business behaviour by parsing the human-readable `product` string.

This keeps calculation behaviour stable if product naming conventions change and avoids maintaining two competing representations of delivery semantics.

### CSV validation is an application boundary

`CsvTradeRepository` owns the CSV-specific workflow:

```text
CSV strings
    → CsvTradeRow validation + reference-data checks
    → good rows → domain Trade → TradeBook
    → bad rows  → quarantine (line, trade, field, value, reason)
```

Pydantic is used for untrusted external data; the core receives typed domain objects rather than CSV/Pydantic models. Direction is parsed into the domain `BuySell` enum at this boundary so invalid values such as `B`, `buy`, or `Purchase` are reported with the rest of the row errors instead of failing later during calculation.

The repository reports every problem in one pass. A bad row is quarantined and the rest of the book still loads; only a broken file stops the run.

### Configuration and extensibility
Reference data and configurable profile parameters are separated from calculation behaviour. 

The current design allows common extensionssuch as additional Japanese delivery areas or profiles using existing delivery behaviour to be introduced without changing the central aggregation logic.

New source systems can similarly be introduced by normalizing their data into the same domain representation.

### Error handling

Input problems are separated into two broad categories:

Structural or calculation failures stop the run when the resulting position cannot be considered reliable.

Row-level validation failures are isolated so that one malformed trade does not prevent the remainder of the book from being inspected.

Quarantined rows are surfaced to the user, and affected reporting periods are identified as incomplete rather than presenting potentially misleading positions as fully reliable.

### Testing strategy

The test suite is focuses primarly on deterministic behaviour:

- Buy/Sell sign conventions;
- delivery interval boundaries;
- daily, weekly and monthly period generation;
- load-profile delivery behaviour;
- overlapping trades and profiles;
- MW/MWh calculations;
- partial period exposures 
- separation between delivery areas;
- validation and error handling

Lightweight integration path also verifies that an input trade book can be loaded, normalized and converted into the expected position output.

### Extensibility

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





