"""The expected results from requirements.md S9, transcribed as test data.

S9 calls these "derived acceptance fixtures": they follow from the sign convention, the
reporting windows, and the Average MW definition chosen in the specification. They are
the strongest correctness evidence available, because they exercise netting, area
isolation, both interval boundaries, and exposure that changes inside a reporting period
all at once (S10).

Net MWh figures are exact integers. Average MW is given to two decimal places because
some values repeat, so it is compared after rounding while Net MWh is compared exactly.

Shared between the core acceptance test (M3) and the end-to-end CSV test (M5) so that
both assert against one transcription of the specification.
"""

from __future__ import annotations

# (period label, area, Average MW to 2dp, exact Net MWh, position)
Row = tuple[str, str, str, int, str]

SECTION_9_1_DAILY: tuple[Row, ...] = (
    ("2026-10-01", "Tokyo", "30.00", 720, "LONG"),
    ("2026-10-01", "Kansai", "12.00", 288, "LONG"),
    ("2026-10-02", "Tokyo", "30.00", 720, "LONG"),
    ("2026-10-02", "Kansai", "12.00", 288, "LONG"),
    ("2026-10-03", "Tokyo", "30.00", 720, "LONG"),
    ("2026-10-03", "Kansai", "12.00", 288, "LONG"),
    ("2026-10-04", "Tokyo", "30.00", 720, "LONG"),
    ("2026-10-04", "Kansai", "12.00", 288, "LONG"),
    ("2026-10-05", "Tokyo", "30.00", 720, "LONG"),
    ("2026-10-05", "Kansai", "6.00", 144, "LONG"),
    ("2026-10-06", "Tokyo", "30.00", 720, "LONG"),
    ("2026-10-06", "Kansai", "6.00", 144, "LONG"),
    ("2026-10-07", "Tokyo", "30.00", 720, "LONG"),
    ("2026-10-07", "Kansai", "6.00", 144, "LONG"),
)

SECTION_9_2_WEEKLY: tuple[Row, ...] = (
    ("2026-10-01 to 2026-10-04", "Tokyo", "30.00", 2_880, "LONG"),
    ("2026-10-01 to 2026-10-04", "Kansai", "12.00", 1_152, "LONG"),
    ("2026-10-05 to 2026-10-11", "Tokyo", "27.71", 4_656, "LONG"),
    ("2026-10-05 to 2026-10-11", "Kansai", "6.00", 1_008, "LONG"),
    ("2026-10-12 to 2026-10-18", "Tokyo", "40.00", 6_720, "LONG"),
    ("2026-10-12 to 2026-10-18", "Kansai", "12.00", 2_016, "LONG"),
    ("2026-10-19 to 2026-10-25", "Tokyo", "30.00", 5_040, "LONG"),
    ("2026-10-19 to 2026-10-25", "Kansai", "12.00", 2_016, "LONG"),
)

SECTION_9_3_MONTHLY: tuple[Row, ...] = (
    ("2026-10", "Tokyo", "31.74", 23_616, "LONG"),
    ("2026-10", "Kansai", "10.65", 7_920, "LONG"),
    ("2026-11", "Tokyo", "45.00", 32_400, "LONG"),
    ("2026-11", "Kansai", "12.00", 8_640, "LONG"),
    ("2026-12", "Tokyo", "30.00", 22_320, "LONG"),
    ("2026-12", "Kansai", "12.00", 8_928, "LONG"),
    ("2027-01", "Tokyo", "25.00", 18_600, "LONG"),
    ("2027-01", "Kansai", "0.00", 0, "FLAT"),
    ("2027-02", "Tokyo", "25.00", 16_800, "LONG"),
    ("2027-02", "Kansai", "0.00", 0, "FLAT"),
    ("2027-03", "Tokyo", "25.00", 18_600, "LONG"),
    ("2027-03", "Kansai", "0.00", 0, "FLAT"),
    ("2027-04", "Tokyo", "10.00", 7_200, "LONG"),
    ("2027-04", "Kansai", "0.00", 0, "FLAT"),
    ("2027-05", "Tokyo", "10.00", 7_440, "LONG"),
    ("2027-05", "Kansai", "0.00", 0, "FLAT"),
    ("2027-06", "Tokyo", "10.00", 7_200, "LONG"),
    ("2027-06", "Kansai", "0.00", 0, "FLAT"),
    ("2027-07", "Tokyo", "15.00", 11_160, "LONG"),
    ("2027-07", "Kansai", "0.00", 0, "FLAT"),
    ("2027-08", "Tokyo", "15.00", 11_160, "LONG"),
    ("2027-08", "Kansai", "0.00", 0, "FLAT"),
    ("2027-09", "Tokyo", "15.00", 10_800, "LONG"),
    ("2027-09", "Kansai", "0.00", 0, "FLAT"),
)
