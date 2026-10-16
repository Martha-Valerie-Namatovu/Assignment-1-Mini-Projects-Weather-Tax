"""Value Added Tax for one return period (VAT Act Cap 349)."""

from __future__ import annotations

from .base import Tax
from .context import SupplyType, TaxContext, TaxLine, TaxResult, VATContext
from .money import Money
from .schedules import VAT_RATES, FlatRateTable


class VAT(Tax):
    """Net VAT payable = output VAT − creditable input VAT.

    * Standard-rated sales carry output VAT at the standard rate (18%).
    * Zero-rated sales carry 0% output VAT but are *taxable* supplies, so input
      VAT on the purchases used to make them is still creditable.
    * Exempt sales carry no VAT and are *not* taxable supplies, so input VAT is
      not creditable on them. When a business makes both, input VAT is
      apportioned by the share of taxable supplies in total supplies (VAT Act s.28).
    * Only purchases charged at the standard rate carry input VAT.

    A negative result is a credit the business can carry forward or claim as a refund.
    """

    name = "VAT"

    def __init__(self, rates: FlatRateTable = VAT_RATES) -> None:
        self.rates = rates

    def calculate(self, ctx: TaxContext) -> TaxResult:
        period = self._expect(ctx, VATContext)
        rate = self.rates.rate_on(period.on)

        def total(invoices, supply):
            return sum((i.net for i in invoices if i.supply is supply), Money.zero())

        standard, zero, exempt = (total(period.sales, s) for s in SupplyType)
        taxable = standard + zero
        all_supplies = taxable + exempt
        output_vat = standard * rate
        input_vat = total(period.purchases, SupplyType.STANDARD) * rate

        if not exempt:
            share = None
            creditable = input_vat
        elif not all_supplies:
            share, creditable = None, Money.zero()
        else:
            share = taxable / all_supplies
            creditable = input_vat * share

        net = (output_vat - creditable).round()
        lines = [
            TaxLine(f"output VAT {rate:.0%} on standard-rated sales of {standard}", output_vat.round()),
            TaxLine(f"zero-rated sales {zero} at 0%", Money.zero()),
            TaxLine(f"exempt sales {exempt} (no VAT)", Money.zero()),
            TaxLine("input VAT on standard-rated purchases", input_vat.round()),
        ]
        notes = []
        if share is not None:
            lines.append(TaxLine(f"creditable input VAT ({share:.1%} taxable share)", creditable.round()))
            notes.append("Input VAT apportioned because the period includes exempt supplies.")
        lines.append(TaxLine("net VAT payable (negative = credit)", net))
        if net < Money.zero():
            notes.append("Credit position: carry forward or claim a refund.")
        return TaxResult(self.name, standard, net, tuple(lines), tuple(notes))

    def output_vat(self, ctx: VATContext) -> Money:
        """Output VAT alone, rounded."""
        rate = self.rates.rate_on(ctx.on)
        return (sum((i.net for i in ctx.sales if i.supply is SupplyType.STANDARD), Money.zero()) * rate).round()
