"""Corporate income tax for resident companies (Income Tax Act Cap 340)."""

from __future__ import annotations

from .base import Tax
from .context import CorporateContext, TaxContext, TaxLine, TaxResult
from .money import Money
from .schedules import CIT_RATES, FlatRateTable


class CorporateIncomeTax(Tax):
    """Chargeable income = revenue − allowable deductions − losses brought forward; tax = rate × chargeable.

    A negative chargeable income is not taxed; it becomes a loss carried forward,
    reported in the notes, not hidden.
    """

    name = "Corporate income tax"

    def __init__(self, rates: FlatRateTable = CIT_RATES) -> None:
        self.rates = rates

    def calculate(self, ctx: TaxContext) -> TaxResult:
        co = self._expect(ctx, CorporateContext)
        rate = self.rates.rate_on(co.on)
        chargeable = co.revenue - co.total_deductions - co.losses_brought_forward
        lines = [TaxLine("revenue", co.revenue)]
        lines += [TaxLine(f"less {name}", -amount) for name, amount in co.deductions.items()]
        if co.losses_brought_forward:
            lines.append(TaxLine("less losses brought forward", -co.losses_brought_forward))
        notes = []
        if chargeable < Money.zero():
            notes.append(f"Assessed loss of {abs(chargeable)} carried forward to next year.")
            base = Money.zero()
        else:
            base = chargeable
        due = (base * rate).round()
        lines.append(TaxLine(f"tax at {rate:.0%} of chargeable income {base}", due))
        return TaxResult(self.name, base, due, tuple(lines), tuple(notes))
