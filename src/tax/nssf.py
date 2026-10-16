"""National Social Security Fund contributions (NSSF Act Cap 230, s.11)."""

from __future__ import annotations

from decimal import Decimal

from .base import Tax
from .context import EmploymentContext, TaxContext, TaxLine, TaxResult
from .money import Money


class NSSF(Tax):
    """Employee 5% and employer 10% of gross monthly wages.

    ``TaxResult.amount`` is the employee's share (what comes off the payslip).
    The employer's share is a cost to the employer, shown as a breakdown line and
    available from ``employer_contribution``. Allowances count as wages unless
    ``include_allowances`` is False.
    """

    name = "NSSF"

    def __init__(self, employee_rate: Decimal = Decimal("0.05"), employer_rate: Decimal = Decimal("0.10"),
                 include_allowances: bool = True) -> None:
        if not (Decimal(0) <= employee_rate <= 1 and Decimal(0) <= employer_rate <= 1):
            raise ValueError("NSSF rates must be between 0 and 1")
        self.employee_rate = employee_rate
        self.employer_rate = employer_rate
        self.include_allowances = include_allowances

    def wages(self, ctx: EmploymentContext) -> Money:
        return ctx.total_emoluments if self.include_allowances else ctx.gross_pay

    def employer_contribution(self, ctx: EmploymentContext) -> Money:
        return (self.wages(ctx) * self.employer_rate).round()

    def calculate(self, ctx: TaxContext) -> TaxResult:
        emp = self._expect(ctx, EmploymentContext)
        wages = self.wages(emp)
        employee = (wages * self.employee_rate).round()
        lines = (TaxLine(f"employee {self.employee_rate:.0%} of wages", employee),
                 TaxLine(f"employer {self.employer_rate:.0%} of wages (employer cost, not deducted)",
                         self.employer_contribution(emp)))
        return TaxResult(self.name, wages, employee, lines)
