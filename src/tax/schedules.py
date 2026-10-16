"""Rate schedules as data, selected by date.

Rates change with each Finance Act, so they are not hard-coded inside the tax
classes. A ``ProgressiveSchedule`` is a list of ``Band`` objects; the fixed
amounts quoted in URA tables (10,000; 25,000; ...) are *derived* by summing the
lower bands, never typed in, so the table and the code cannot disagree. A
``ScheduleRegistry`` picks the schedule in force on a date and raises
``NoScheduleForDateError`` outside every known period.

Sources (verify before relying on them for a real payroll):

* PAYE up to 30 June 2026: Income Tax Act Cap 340, Third Schedule Part I, as
  amended by the Income Tax (Amendment) Act 2012 (resident threshold
  UGX 235,000/month). URA, "PAYE rates", https://ura.go.ug (accessed 14 Oct 2026).
* PAYE from 1 July 2026: Income Tax (Amendment) Act 2026 (Bill passed 23 Apr
  2026, assented 20 Aug 2026, effective 1 Jul 2026): resident threshold raised to
  UGX 335,000/month with bands of 20%, 25% and 30%. These are the bands in the
  assignment brief. Reported by AfroTools, "Uganda PAYE tax 2026/27"
  (https://afrotools.com/fr/blog/uganda-paye-tax-2026-27/, accessed 14 Oct 2026).
  The non-resident schedule for 2026/27 was not published in the sources we
  found, so it is ASSUMED unchanged from 2025/26.
* 10% surcharge on monthly chargeable income above UGX 10,000,000: same Schedule,
  both periods, residents and non-residents.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .context import TaxLine
from .errors import InvalidIncomeError, NoScheduleForDateError
from .money import Money, to_decimal


@dataclass(frozen=True)
class Band:
    """Income in ``(lower, upper]`` is taxed at ``rate``. ``upper=None`` means no ceiling."""

    lower: Money
    upper: Money | None
    rate: Decimal

    def __post_init__(self) -> None:
        if self.upper is not None and self.upper <= self.lower:
            raise ValueError("Band upper limit must exceed its lower limit")
        if not Decimal(0) <= self.rate <= Decimal(1):
            raise ValueError("Band rate must be between 0 and 1")

    def taxable_part(self, income: Money) -> Money:
        """How much of ``income`` falls inside this band."""
        if income <= self.lower:
            return Money.zero()
        top = income if self.upper is None or income < self.upper else self.upper
        return top - self.lower


def bands(*rows: tuple[int, int | None, str]) -> tuple[Band, ...]:
    """Build bands from ``(lower, upper, rate)`` rows with rate as a string, e.g. ``"0.20"``."""
    return tuple(Band(Money(lo), None if hi is None else Money(hi), to_decimal(rate)) for lo, hi, rate in rows)


@dataclass(frozen=True)
class ProgressiveSchedule:
    """Marginal-rate bands plus an optional surcharge on income above a threshold."""

    name: str
    bands: tuple[Band, ...]
    surcharge_threshold: Money | None = None
    surcharge_rate: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if not self.bands or self.bands[0].lower != Money.zero():
            raise ValueError("Bands must start at zero")
        for prev, nxt in zip(self.bands, self.bands[1:]):
            if prev.upper != nxt.lower:
                raise ValueError(f"Bands must be contiguous: {prev.upper!r} then {nxt.lower!r}")
        if self.bands[-1].upper is not None:
            raise ValueError("The last band must have no upper limit")

    def tax_on(self, income: Money) -> tuple[Money, tuple[TaxLine, ...]]:
        """Exact (unrounded) tax on ``income`` and the per-band breakdown."""
        if income < Money.zero():
            raise InvalidIncomeError(f"Chargeable income cannot be negative: {income!r}")
        lines = []
        total = Money.zero()
        for band in self.bands:
            part = band.taxable_part(income)
            if not part:
                continue
            tax = part * band.rate
            upper = f"{band.upper.amount:,.0f}" if band.upper else "∞"
            lines.append(TaxLine(f"{band.rate:.0%} of {part.amount:,.0f} in ({band.lower.amount:,.0f}, {upper}]", tax))
            total += tax
        if self.surcharge_threshold is not None and income > self.surcharge_threshold:
            excess = income - self.surcharge_threshold
            tax = excess * self.surcharge_rate
            lines.append(TaxLine(f"surcharge {self.surcharge_rate:.0%} of {excess.amount:,.0f} "
                                 f"over {self.surcharge_threshold.amount:,.0f}", tax))
            total += tax
        return total, tuple(lines)

    def fixed_amount_at(self, threshold: Money) -> Money:
        """Tax on income exactly at ``threshold``: the 'fixed amount' column of a URA table."""
        return self.tax_on(threshold)[0]


@dataclass(frozen=True)
class SchedulePeriod:
    """Resident and non-resident schedules in force from ``start`` to ``end`` inclusive."""

    start: date
    end: date | None
    resident: ProgressiveSchedule
    non_resident: ProgressiveSchedule

    def covers(self, on: date) -> bool:
        return self.start <= on and (self.end is None or on <= self.end)


class ScheduleRegistry:
    """Date-indexed collection of schedule periods for one tax."""

    def __init__(self, tax: str, periods: list[SchedulePeriod]) -> None:
        ordered = sorted(periods, key=lambda p: p.start)
        for a, b in zip(ordered, ordered[1:]):
            if a.end is None or a.end >= b.start:
                raise ValueError(f"{tax} schedule periods overlap: {a.start} and {b.start}")
        self.tax = tax
        self.periods = ordered

    def period_for(self, on: date) -> SchedulePeriod:
        for period in self.periods:
            if period.covers(on):
                return period
        raise NoScheduleForDateError(self.tax, on)

    def for_date(self, on: date, resident: bool = True) -> ProgressiveSchedule:
        period = self.period_for(on)
        return period.resident if resident else period.non_resident

    def __repr__(self) -> str:
        spans = ", ".join(f"{p.start}..{p.end or 'open'}" for p in self.periods)
        return f"ScheduleRegistry({self.tax!r}: {spans})"


SURCHARGE_THRESHOLD = Money(10_000_000)
SURCHARGE_RATE = Decimal("0.10")

PAYE_RESIDENT_2012 = ProgressiveSchedule(
    "PAYE resident, FY2012/13-FY2025/26",
    bands((0, 235_000, "0"), (235_000, 335_000, "0.10"), (335_000, 410_000, "0.20"), (410_000, None, "0.30")),
    SURCHARGE_THRESHOLD, SURCHARGE_RATE)

PAYE_NON_RESIDENT_2012 = ProgressiveSchedule(
    "PAYE non-resident, FY2012/13 onwards",
    bands((0, 335_000, "0.10"), (335_000, 410_000, "0.20"), (410_000, None, "0.30")),
    SURCHARGE_THRESHOLD, SURCHARGE_RATE)

PAYE_RESIDENT_2026 = ProgressiveSchedule(
    "PAYE resident, FY2026/27 (Income Tax (Amendment) Act 2026)",
    bands((0, 335_000, "0"), (335_000, 410_000, "0.20"), (410_000, 485_000, "0.25"), (485_000, None, "0.30")),
    SURCHARGE_THRESHOLD, SURCHARGE_RATE)

PAYE_SCHEDULES = ScheduleRegistry("PAYE", [
    SchedulePeriod(date(2012, 7, 1), date(2026, 6, 30), PAYE_RESIDENT_2012, PAYE_NON_RESIDENT_2012),
    SchedulePeriod(date(2026, 7, 1), None, PAYE_RESIDENT_2026, PAYE_NON_RESIDENT_2012),
])


@dataclass(frozen=True)
class FlatRate:
    """A single rate in force over a date range (VAT, corporate tax)."""

    start: date
    end: date | None
    rate: Decimal


class FlatRateTable:
    """Date-indexed flat rates, with the same error behaviour as ``ScheduleRegistry``."""

    def __init__(self, tax: str, rates: list[FlatRate]) -> None:
        self.tax = tax
        self.rates = sorted(rates, key=lambda r: r.start)

    def rate_on(self, on: date) -> Decimal:
        for r in self.rates:
            if r.start <= on and (r.end is None or on <= r.end):
                return r.rate
        raise NoScheduleForDateError(self.tax, on)


# VAT Act Cap 349: standard rate 18% since 1 July 2005 (raised from 17%).
VAT_RATES = FlatRateTable("VAT", [FlatRate(date(2005, 7, 1), None, Decimal("0.18"))])
# Income Tax Act Cap 340, s.4 and Second Schedule: resident companies 30% since the Act took effect.
CIT_RATES = FlatRateTable("Corporate income tax", [FlatRate(date(1997, 7, 1), None, Decimal("0.30"))])
