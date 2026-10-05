# Power Position Tool — Requirements Specification

**Required as-of date:** Thursday, 1 October 2026 (JST)  
**Input:** `trades.csv`  
**Status:** Pre-implementation baseline

## 1. Purpose and evidence boundaries

This document converts the supplied case statement and CSV into an implementation-ready requirements baseline. It deliberately distinguishes:

- **Case requirement** — explicitly stated in the assessment brief.
- **CSV fact** — directly observed in the supplied `trades.csv`.
- **Chosen assumption** — a decision required because the case deliberately leaves the definition open.
- **Derived result** — calculated from CSV facts under the chosen assumptions.
- **Future design constraint** — growth explicitly described by the case; not functionality that must necessarily be implemented for the current data.

No requirement below assumes cancellation, amendment, fees, P&L, valuation, currency conversion, loss factors, daylight-saving adjustments, half-hourly products, or live market data. None of those appear in the supplied case or CSV.

## 2. Business objective

### 2.1 Primary objective — case requirement

Build a position tool for the trading desk of an electricity retailer supplying customers in Japan. From the trade book, the tool must show how many MW and MWh the desk is long or short over the coming days, weeks, and months, separately by delivery area.

The result is used every morning by traders to decide whether to increase or decrease their positions. Therefore, the output must be readable in under one minute and each row must make both direction and magnitude immediately clear.

### 2.2 Engineering objective — case requirement

The current book is small, but the solution must be designed with the following stated growth in mind:

- trading in all nine Japanese areas;
- additional load profiles, including Peak;
- additional trade types, including OTC forwards;
- more than 100,000 trades;
- refreshes several times per day.

Adding an area, load profile, or trade type should require as little change as possible.

## 3. Scope

### 3.1 Required current scope

The tool must:

1. read the supplied `trades.csv`;
2. validate and type its records;
3. determine the signed delivery position produced by each trade;
4. net overlapping trades by delivery area and reporting period;
5. produce three forward-looking views:
   - next 7 days, one row per day;
   - next 4 weeks, one row per week;
   - next 12 months, one row per month;
6. report MW and MWh and state LONG, SHORT, or FLAT;
7. present the results in a form a trader can scan in under one minute;
8. use JST and treat 1 October 2026 as the as-of date.

### 3.2 Explicit future design scope

The architecture must admit future areas, profiles, and trade types without spreading product-specific conditionals through parsing, calculation, aggregation, and presentation.

The brief describes Peak as 08:00–20:00 Monday–Friday, including public holidays, for 12 hours per weekday. This is a future extensibility requirement; the supplied CSV contains only Base trades.

OTC forwards are an example of a future trade type. The brief does not define any OTC-specific position semantics, so those semantics must not be invented in the current implementation.

### 3.3 Out of scope unless added separately

The supplied requirements do not request:

- trade entry, editing, cancellation, or amendment;
- position persistence or a database;
- live/intraday ingestion;
- authentication or authorization;
- P&L, mark-to-market, valuation, cash flow, or hedging cost;
- use of `price_jpy_kwh` in the physical position calculation;
- reconciliation against another system;
- forecasting retail load;
- an execution or order-management capability;
- a REST API, web interface, or cloud deployment.

These may be discussed as future evolution, but should not be presented as current case requirements.

## 4. Source data profile

### 4.1 CSV schema — case requirement and CSV fact

| Field | Meaning from case | Supplied values / observed role |
|---|---|---|
| `trade_id` | Unique trade reference | T001–T012 |
| `trade_date` | Date the trade was agreed | ISO dates |
| `counterparty` | Party traded with | Five distinct names |
| `area` | Delivery area | Tokyo, Kansai |
| `trade_type` | Contract type | Futures only |
| `buy_sell` | Trade direction | Buy, Sell |
| `product` | Product name booked by trader | Calendar, quarter, month, week, weekend, fiscal-year descriptions |
| `load_profile` | Hours in which the trade delivers | Base only |
| `start_date` | First delivery day, inclusive | ISO date |
| `end_date` | Day after last delivery day, exclusive | ISO date |
| `volume_mw` | Flat volume delivered in every covered hour | Positive integer values in supplied file |
| `price_jpy_kwh` | Contract price | Positive decimal values in supplied file |

### 4.2 Supplied-book facts

- 12 records are present.
- Trade IDs are unique.
- 10 records are Tokyo and 2 are Kansai.
- Every record has `trade_type = Futures`.
- Every record has `load_profile = Base`.
- Both Buy and Sell trades are present.
- Delivery periods overlap.
- Delivery lengths include a two-day weekend, a week, months, quarters, a calendar year, and a fiscal year.
- The earliest delivery start is 1 January 2026; the latest delivery end is 1 April 2028.
- All supplied delivery and trade dates parse as ISO calendar dates.
- All supplied volumes and prices are positive.

### 4.3 Field usage

Position calculation is determined from:

- `area`;
- `buy_sell`;
- `load_profile`;
- `start_date`;
- `end_date`;
- `volume_mw`.

The following fields must be retained and validated, but do not affect the requested physical position for the supplied case:

- `trade_id`;
- `trade_date`;
- `counterparty`;
- `trade_type` (all current values have the same delivery-position treatment);
- `product`;
- `price_jpy_kwh`.

`product` is descriptive metadata. It must not be parsed to infer delivery dates or profile because the CSV already provides structured `start_date`, `end_date`, and `load_profile` fields.

## 5. Domain definitions and invariants

### 5.1 Time and delivery interval

- All dates and times are interpreted in Japan Standard Time (JST). **Case requirement.**
- `start_date` is inclusive and `end_date` is exclusive. **Case requirement.**
- Date-only delivery boundaries are assumed to occur at 00:00 JST. **Chosen assumption.**
- A valid trade must satisfy `start_date < end_date`. **Required consequence of the stated interval semantics.**
- A Base trade delivers its full `volume_mw` in every hour of every delivery day. **Case requirement.**

### 5.2 Direction and sign

**Chosen convention:**

- Buy = positive contribution = long;
- Sell = negative contribution = short.

For trade \(t\):

\[
signedMW_t = direction_t \times volumeMW_t
\]

where `direction` is +1 for Buy and −1 for Sell.

The input volume should be strictly positive because direction is represented independently. A negative or zero supplied volume should be rejected rather than creating a second sign convention. **Chosen validation rule, consistent with the supplied data model.**

### 5.3 Identity and categorical values

- `trade_id` is documented as unique; duplicate IDs must be rejected rather than silently deduplicated. **Case wording plus chosen failure behaviour.**
- `buy_sell` must be a supported direction.
- `load_profile` must be supported by a registered profile rule.
- `trade_type` must be recognized by the application configuration/domain model.
- `area` is a grouping dimension and must not require area-specific calculation branches.
- Required text fields must not be empty after parsing.

### 5.4 Numeric handling

- `volume_mw` and `price_jpy_kwh` must parse as numeric values.
- Decimal-safe numeric types should be used at the input/domain boundary to avoid avoidable binary-floating-point surprises.
- Output rounding must be presentation-only; aggregation should use unrounded values.
- The displayed precision must be documented and consistent.

## 6. Canonical position calculation

### 6.1 General calculation contract

For a trade \(t\) and report period \(p\):

\[
MWh_{t,p} = signedMW_t \times coveredHours(t,p)
\]

where `coveredHours` is the number of hours that:

1. lie in the intersection of the trade delivery interval and reporting interval; and
2. are covered by the trade's load profile.

For an area \(a\):

\[
NetMWh_{a,p} = \sum_{t: area_t=a} MWh_{t,p}
\]

Only the interval intersection contributes. A trade outside the report period contributes zero.

### 6.2 Current Base-only optimization

Because all supplied trades are Base and have date boundaries, the current implementation may calculate overlap in days and multiply by 24 instead of materializing one row per hour:

\[
coveredHours(t,p) = overlapDays(t,p) \times 24
\]

This is an implementation optimization, not a change to the conceptual covered-hour model. The profile abstraction must allow Peak or another future shape to provide its own covered-hour calculation.

### 6.3 MW reported over a period

The case asks for MW and MWh but does not define a single MW number when exposure changes within a row's period.

**Chosen assumption:** report:

\[
AverageMW_{a,p} = \frac{NetMWh_{a,p}}{hoursInReportingWindow_p}
\]

The column must be labelled **Average MW**, not merely MW, so it does not imply that the exposure is constant throughout the period. For the current daily Base-only rows, this equals the constant daily net MW. For a week or month containing a short-dated trade, it is a time-weighted average.

This metric does not replace the need for MWh. MWh is the additive period quantity and should be treated as the canonical weekly/monthly aggregate.

### 6.4 Position label

- `Net MWh > 0` → `LONG`
- `Net MWh < 0` → `SHORT`
- `Net MWh = 0` → `FLAT`

The label and signed numerical values must both be shown. Magnitudes may also be visually formatted, but colour must not be the only indicator.

## 7. Reporting windows — chosen assumptions

The brief deliberately leaves window starts, units, and week definition open. The following choices are part of the proposed product specification and must be configurable/testable rather than hidden in calculation code.

### 7.1 Daily view

- Seven calendar days beginning on the as-of date.
- For the assessment: 1 October through 7 October 2026 inclusive.
- Each reporting interval is `[day 00:00, next day 00:00)` JST.

Rationale: the tool is used each morning and the trader needs the current day's position for hedging.

### 7.2 Weekly view

- Calendar weeks run Monday through Sunday.
- The output contains the current calendar week plus the next three calendar weeks.
- Historical time before the as-of date is excluded from the current partial week.
- For the assessment, the four covered intervals are:
  - 1–4 October 2026 (current partial week);
  - 5–11 October 2026;
  - 12–18 October 2026;
  - 19–25 October 2026.
- Each row must display its actual covered start and end dates; a week number alone is insufficient.

### 7.3 Monthly view

- Current calendar month plus the following 11 calendar months.
- Historical time before the as-of date is excluded from the current partial month.
- For the assessment, 1 October is already the first day of the month, so the intervals are the full months October 2026 through September 2027.
- Each row must display the month and/or actual covered dates clearly.

### 7.4 Future as-of timestamps

The current assessment supplies an as-of date, not an intraday timestamp. The tool must not invent partial-day treatment. If future refreshes several times per day require an intraday as-of timestamp, the treatment of the current delivery hour/day must be agreed separately.

## 8. Required output contract

### 8.1 Minimum columns per row

Each view must provide at least:

- area;
- period label;
- covered start date;
- covered end date (clearly presented as inclusive to humans or exclusive in machine output, but not ambiguous);
- Average MW;
- Net MWh;
- position label: LONG, SHORT, or FLAT.

The view should also state globally:

- as-of date: 1 October 2026;
- timezone: JST;
- sign convention;
- reporting-window convention.

### 8.2 Area coverage

Results must be broken down by area. Under the proposed behaviour, every observed area should appear for every reporting period, including zero-exposure rows, so a trader can distinguish `FLAT` from missing output.

Future new area names should flow through as data, subject to validation/configuration, without calculation-code changes.

### 8.3 Presentation usability

- Keep the three views visually distinct.
- Sort periods chronologically.
- Use a stable area ordering.
- Align numeric columns and show units in headers.
- Make LONG/SHORT/FLAT explicit on every row.
- Do not rely only on signs or colours.
- Clearly identify partial periods.
- Avoid showing irrelevant columns such as counterparty and price in the summary views.

The specific presentation technology is not prescribed by the case.

## 9. Expected results for the supplied CSV

These are **derived acceptance fixtures**, not additional requirements from the brief. They follow the sign, window, and Average MW assumptions in this document. All MWh figures are exact; repeating Average MW values are shown rounded to two decimal places for readability.

### 9.1 Next 7 days

| Date | Area | Average MW | Net MWh | Position |
|---|---|---:|---:|---|
| 2026-10-01 | Tokyo | 30 | 720 | LONG |
| 2026-10-01 | Kansai | 12 | 288 | LONG |
| 2026-10-02 | Tokyo | 30 | 720 | LONG |
| 2026-10-02 | Kansai | 12 | 288 | LONG |
| 2026-10-03 | Tokyo | 30 | 720 | LONG |
| 2026-10-03 | Kansai | 12 | 288 | LONG |
| 2026-10-04 | Tokyo | 30 | 720 | LONG |
| 2026-10-04 | Kansai | 12 | 288 | LONG |
| 2026-10-05 | Tokyo | 30 | 720 | LONG |
| 2026-10-05 | Kansai | 6 | 144 | LONG |
| 2026-10-06 | Tokyo | 30 | 720 | LONG |
| 2026-10-06 | Kansai | 6 | 144 | LONG |
| 2026-10-07 | Tokyo | 30 | 720 | LONG |
| 2026-10-07 | Kansai | 6 | 144 | LONG |

### 9.2 Next 4 weeks

| Covered period | Area | Average MW | Net MWh | Position |
|---|---|---:|---:|---|
| 2026-10-01 to 2026-10-04 | Tokyo | 30 | 2,880 | LONG |
| 2026-10-01 to 2026-10-04 | Kansai | 12 | 1,152 | LONG |
| 2026-10-05 to 2026-10-11 | Tokyo | 27.71 | 4,656 | LONG |
| 2026-10-05 to 2026-10-11 | Kansai | 6 | 1,008 | LONG |
| 2026-10-12 to 2026-10-18 | Tokyo | 40 | 6,720 | LONG |
| 2026-10-12 to 2026-10-18 | Kansai | 12 | 2,016 | LONG |
| 2026-10-19 to 2026-10-25 | Tokyo | 30 | 5,040 | LONG |
| 2026-10-19 to 2026-10-25 | Kansai | 12 | 2,016 | LONG |

### 9.3 Next 12 months

| Month | Area | Average MW | Net MWh | Position |
|---|---|---:|---:|---|
| 2026-10 | Tokyo | 31.74 | 23,616 | LONG |
| 2026-10 | Kansai | 10.65 | 7,920 | LONG |
| 2026-11 | Tokyo | 45 | 32,400 | LONG |
| 2026-11 | Kansai | 12 | 8,640 | LONG |
| 2026-12 | Tokyo | 30 | 22,320 | LONG |
| 2026-12 | Kansai | 12 | 8,928 | LONG |
| 2027-01 | Tokyo | 25 | 18,600 | LONG |
| 2027-01 | Kansai | 0 | 0 | FLAT |
| 2027-02 | Tokyo | 25 | 16,800 | LONG |
| 2027-02 | Kansai | 0 | 0 | FLAT |
| 2027-03 | Tokyo | 25 | 18,600 | LONG |
| 2027-03 | Kansai | 0 | 0 | FLAT |
| 2027-04 | Tokyo | 10 | 7,200 | LONG |
| 2027-04 | Kansai | 0 | 0 | FLAT |
| 2027-05 | Tokyo | 10 | 7,440 | LONG |
| 2027-05 | Kansai | 0 | 0 | FLAT |
| 2027-06 | Tokyo | 10 | 7,200 | LONG |
| 2027-06 | Kansai | 0 | 0 | FLAT |
| 2027-07 | Tokyo | 15 | 11,160 | LONG |
| 2027-07 | Kansai | 0 | 0 | FLAT |
| 2027-08 | Tokyo | 15 | 11,160 | LONG |
| 2027-08 | Kansai | 0 | 0 | FLAT |
| 2027-09 | Tokyo | 15 | 10,800 | LONG |
| 2027-09 | Kansai | 0 | 0 | FLAT |

## 10. Dataset-specific boundary cases

The supplied book intentionally exercises these behaviours:

1. **Overlapping contracts and netting:** On 1 October Tokyo is `+20 +15 −5 = +30 MW`.
2. **Area isolation:** Tokyo trades must not affect Kansai totals.
3. **Mid-week position change:** Kansai changes from +12 MW to +6 MW when T012 starts on 5 October.
4. **Short weekend product:** Tokyo T005 reduces exposure by 8 MW only on 10 and 11 October.
5. **Exclusive end plus inclusive start:** T005 ends on 12 October and T004 starts on 12 October; T005 must not contribute on that date, while T004 must.
6. **Month boundary:** T003 stops before 1 November; T006 begins on 1 November.
7. **Year boundary:** the Cal-26/Q4-26/Dec-26 positions end before 1 January 2027 and T008 begins then.
8. **Quarter/fiscal-year overlap:** from April through June 2027, T009 +15 MW and T010 −5 MW net to +10 MW; after T010 ends, July onward returns to +15 MW.
9. **Varying exposure within a report period:** weekly and monthly MWh cannot be calculated as the MW observed at the beginning of the period multiplied by total hours.

## 11. Acceptance criteria

### AC-01: Deterministic input

Given the supplied file and as-of date, every valid record is loaded exactly once and repeated runs produce identical results.

### AC-02: Typed parsing

Dates, directions, numeric fields, areas, trade types, and load profiles are parsed into explicit types before entering calculation logic.

### AC-03: Direction

A Buy contributes positive MW/MWh; a Sell contributes negative MW/MWh.

### AC-04: Exclusive end boundary

A trade with `[2026-10-10, 2026-10-12)` contributes on 10 and 11 October and not on 12 October.

### AC-05: Base profile

A 10 MW Base trade covering one complete day contributes 10 MW to all 24 hours and 240 MWh.

### AC-06: Partial overlap

Only the intersection of a delivery interval, reporting interval, and profile-covered hours contributes.

### AC-07: Netting

Overlapping Buy and Sell trades in the same area are algebraically netted.

### AC-08: Area isolation

Trades contribute only to their own delivery area.

### AC-09: Daily view

The output contains exactly seven daily periods beginning 1 October 2026 and matches section 9.1.

### AC-10: Weekly view

The output contains the four documented weekly intervals and matches section 9.2.

### AC-11: Monthly view

The output contains October 2026 through September 2027 and matches section 9.3.

### AC-12: Direction label

Every row maps positive, negative, and zero positions to LONG, SHORT, and FLAT respectively.

### AC-13: Zero exposure visibility

An observed area with no exposure in a requested period is shown as 0 Average MW, 0 MWh, FLAT rather than omitted.

### AC-14: Actionable invalid-input failure

Invalid rows are not silently discarded. The failure identifies the row/trade where possible, field, offending value, and reason.

### AC-15: Duplicate identity

Duplicate `trade_id` values are rejected explicitly.

### AC-16: Product independence

Changing descriptive `product` text without changing structured delivery fields does not change calculated position.

### AC-17: Price independence

Changing a valid `price_jpy_kwh` does not change physical position results.

### AC-18: Extensible area

Adding a valid trade in another area produces another area grouping without modifying core position arithmetic.

### AC-19: Extensible profile boundary

Covered-hour behaviour is supplied through a load-profile abstraction/rule. Supporting Peak should not require changes to the netting and reporting equations.

### AC-20: Scale suitability

The algorithm must avoid scanning all trades independently for every generated hour. For the supplied Base data, interval-overlap aggregation should be proportional to the number of relevant trade/report-period intersections, followed by grouping. A benchmark may be added for 100,000 generated trades, but the case provides no runtime SLA and none should be fabricated.

## 12. Error-handling requirements

The program should fail clearly for:

- missing input file;
- missing or unexpected required headers;
- empty required fields;
- invalid date formats;
- `start_date >= end_date`;
- invalid or unsupported `buy_sell`;
- unsupported load profile;
- unsupported trade type, unless the design explicitly treats trade type as validated metadata;
- non-numeric, zero, or negative volume;
- invalid price;
- duplicate trade ID.

### Chosen processing policy

For this assessment, fail the run after collecting and reporting validation errors rather than silently producing a partial position from a corrupted book. A partial book could create a plausible but wrong hedge signal. If a future operational requirement prefers quarantining bad rows, it should be an explicit policy with rejected-record counts and a prominent incomplete-result warning.

Internal exceptions should not be exposed as the only user-facing explanation. The CLI/reporting boundary should translate them into concise, actionable messages and a non-zero exit status where applicable.

## 13. Non-functional requirements

### 13.1 Correctness

Correct interval boundaries, sign handling, area isolation, netting, and units are the highest priority because an incorrect position can lead to an incorrect hedge.

### 13.2 Determinism

`trade book + as-of value + reporting configuration` must fully determine the result. The core logic must not call the system clock directly. The as-of date must be injected/passed explicitly.

### 13.3 Testability

Core calculations must be runnable without the filesystem, CSV parser, UI, or current clock. File loading and presentation are boundary concerns.

### 13.4 Extensibility

- Areas behave as data dimensions.
- Load-profile hour coverage is independently extensible.
- Trade-type-specific behaviour, if later required, is independently extensible.
- Reporting-window generation is separate from trade-position calculation.
- Presentation does not contain calculation rules.

### 13.5 Scalability

The design should support more than 100,000 trades and repeated daily/intraday refreshes without changing the domain model. Avoid unnecessary full hourly expansion for Base products. Vectorized/tabular processing is acceptable, but correctness and clear domain boundaries take precedence over a library choice.

### 13.6 Observability

At minimum, a run should make available:

- input path;
- as-of date and timezone;
- records read and accepted;
- records rejected if applicable;
- areas processed;
- generated view row counts;
- completion/failure status.

Do not log unnecessary sensitive data or every trade by default.

### 13.7 Reproducibility and usability

The repository should contain a concise setup/run/test workflow, pinned or locked dependencies if dependencies are used, and a clean run from a fresh environment. Technology choices are not dictated by the case.

## 14. Architecture-driving boundaries

This section states responsibilities the architecture must isolate; it does not prescribe folder names or a framework.

1. **Input boundary:** read CSV rows and report file/format errors.
2. **Validation/mapping boundary:** convert external strings into valid typed domain values.
3. **Trade domain:** represent identity, area, type, direction, delivery interval, load profile, volume, and retained metadata.
4. **Load-profile rule:** determine covered hours within an interval.
5. **Reporting calendar:** generate the daily, weekly, and monthly intervals from an explicit as-of value.
6. **Position engine:** calculate signed contributions and aggregate by area and period.
7. **Result model:** carry unrounded Average MW, Net MWh, direction, area, and period metadata.
8. **Presentation boundary:** format three trader-readable views and apply display rounding.
9. **Application orchestration:** connect input, calculation, and output; own run-level errors and diagnostics.

### Dependency direction

Core trade/profile/position logic should not depend on CSV, command-line, dataframe, or display concerns. Boundary code may depend on core abstractions.

### Model choice constraint

The requirements do not mandate Pydantic, dataclasses, Pandas, Polars, a database, or a web framework. A defensible implementation may use validation models at the untrusted input boundary and immutable typed domain objects internally, but duplicate models should only be introduced where they create a real separation of concerns.

## 15. Testing requirements

### 15.1 Unit tests

Cover at least:

- Buy/Sell sign conversion;
- inclusive start and exclusive end;
- no overlap, full overlap, and partial overlap;
- Base covered-hour calculation;
- MWh calculation;
- netting and LONG/SHORT/FLAT classification;
- reporting-window generation;
- Average MW calculation;
- validation of every invariant;
- rounding only at presentation.

### 15.2 Integration tests

Cover:

- CSV → typed trades;
- supplied CSV → each of the three result sets in section 9;
- invalid CSV → actionable aggregate validation error;
- result models → rendered output.

### 15.3 End-to-end test

From a clean invocation with the supplied CSV and explicit as-of date, the application exits successfully and produces all three labelled views with the expected areas, period counts, units, and positions.

### 15.4 Performance test

Generate at least 100,000 representative trades and measure the position calculation. Record the environment and result rather than claiming compliance with an unstated SLA. The test should confirm the solution avoids pathological per-hour-by-per-trade nested work.

## 16. Assumptions requiring documentation in the submission

The README and/or output must disclose:

1. Buy-positive/Sell-negative sign convention.
2. 00:00 JST date boundaries.
3. `[start_date, end_date)` delivery semantics.
4. Daily window includes the as-of day.
5. Monday–Sunday weeks and current partial-week treatment.
6. Current month plus 11 months and partial-current-month treatment.
7. Net MWh as the additive period quantity.
8. Average MW definition.
9. Every supplied row is treated as an active trade because no status/version field exists.
10. Product names are descriptive and not parsed.
11. Price is validated/retained but unused for physical position.
12. Invalid input fails the run rather than being silently skipped.
13. Zero-exposure rows are shown for observed areas.

## 17. Clarifications not required before implementation

The case explicitly asks the candidate to choose window starts, units, and a week definition. Those should be decided and defended, not sent back as blockers.

The supplied current case can be implemented without clarification because it contains only active-looking Base Futures with complete structured delivery fields.

## 18. Questions for a design discussion, not current blockers

These are legitimate production questions but are not answered by the supplied materials and must not be silently built into the current solution:

1. When shaped products coexist, does the desk want Average MW only, or also min/max hourly MW and a profile/hourly view?
2. How are amended, cancelled, or versioned trades represented?
3. Do future OTC forwards contribute to physical position identically to Futures, and are there trade statuses to consider?
4. For several intraday refreshes, should delivered hours of the current day be excluded using an as-of timestamp?
5. Should area names be restricted to an authoritative list of nine areas, and how is that reference data maintained?
6. What output medium do traders prefer: terminal table, CSV/Excel export, dashboard, or API?
7. What runtime, refresh-latency, and availability targets apply in production?
8. Should invalid rows block the entire production refresh or be quarantined with a prominent incomplete-book warning?

## 19. Definition of done

The assessment implementation is complete when:

- the supplied CSV is read and validated;
- calculations conform to sections 5–7;
- all three outputs match section 9 before presentation rounding;
- every row states area, period, Average MW, Net MWh, and LONG/SHORT/FLAT;
- assumptions and limitations are documented;
- automated unit, integration, and end-to-end tests pass;
- invalid data fails clearly;
- core logic is independent of the filesystem, clock, and presentation;
- the design supports new areas without core code changes and provides clear extension points for load profiles and trade types;
- setup, run, and test instructions work in a fresh environment;
- the implementation remains proportionate to the assignment and does not add speculative infrastructure.

