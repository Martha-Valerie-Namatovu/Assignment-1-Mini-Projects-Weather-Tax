"""Local Service Tax (Local Governments Act Cap 243, s.80, as amended 2008).

LST is an annual amount set by monthly income band and collected by the
employer in equal instalments over the first four months of the financial
year (July-October). It is optional in the pipeline (``enabled``) because
not every employer or district applies it the same way, and its bands are
configurable.

Default bands: Local Governments (Amendment) Act 2008, Seventh Schedule, as
summarised in the KCCA "Local Service Tax FAQs" (https://kcca.go.ug/uDocs/Local_Service_Tax_FAQs.pdf).
Verify the bands with the relevant local government before use.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Tax
from .context import EmploymentContext, TaxContext, TaxLine, TaxResult
from .money import Money


@dataclass(frozen=True)
class LSTBand:
    """Monthly income above ``above`` (and up to the next band) pays ``annual`` per year."""

    above: Money
    annual: Money


DEFAULT_LST_BANDS: tuple[LSTBand, ...] = tuple(LSTBand(Money(a), Money(t)) for a, t in [
    (0, 0), (100_000, 5_000), (200_000, 10_000), (300_000, 20_000), (400_000, 30_000),
    (500_000, 40_000), (600_000, 60_000), (700_000, 70_000), (800_000, 80_000),
    (900_000, 90_000), (1_000_000, 100_000),
])


class LocalServiceTax(Tax):
    """Monthly LST instalment for one employee."""

    name = "Local Service Tax"

    def __init__(self, enabled: bool = True, bands: tuple[LSTBand, ...] = DEFAULT_LST_BANDS,
                 collection_months: tuple[int, ...] = (7, 8, 9, 10)) -> None:
        if not bands or bands[0].above != Money.zero():
            raise ValueError("LST bands must start at zero")
        if any(b.above <= a.above for a, b in zip(bands, bands[1:])):
            raise ValueError("LST bands must be strictly increasing")
        if not collection_months or not all(1 <= m <= 12 for m in collection_months):
            raise ValueError("collection_months must be calendar months 1-12")
        self.enabled = enabled
        self.bands = bands
        self.collection_months = tuple(collection_months)

    def annual_amount(self, monthly_income: Money) -> Money:
        """Annual LST for a monthly income: the band whose lower limit the income exceeds."""
        due = Money.zero()
        for band in self.bands:
            if monthly_income > band.above:
                due = band.annual
        return due

    def calculate(self, ctx: TaxContext) -> TaxResult:
        emp = self._expect(ctx, EmploymentContext)
        income = emp.total_emoluments
        if not self.enabled:
            return TaxResult(self.name, income, Money.zero(), notes=("LST disabled",))
        annual = self.annual_amount(income)
        if emp.on.month not in self.collection_months:
            return TaxResult(self.name, income, Money.zero(),
                             notes=(f"annual LST {annual} is collected only in months {self.collection_months}",))
        instalment = (annual / len(self.collection_months)).round()
        return TaxResult(self.name, income, instalment,
                         (TaxLine(f"1/{len(self.collection_months)} of annual {annual}", instalment),))
