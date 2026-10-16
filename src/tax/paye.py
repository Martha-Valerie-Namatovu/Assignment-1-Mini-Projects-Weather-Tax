"""Pay As You Earn on monthly employment income."""

from __future__ import annotations

from .base import Tax
from .context import EmploymentContext, TaxContext, TaxLine, TaxResult
from .errors import InvalidIncomeError
from .money import Money
from .schedules import PAYE_SCHEDULES, ScheduleRegistry


class PAYE(Tax):
    """PAYE for one employee-month.

    Chargeable income = gross pay + taxable allowances − Local Service Tax paid
    in the month. The schedule (resident or non-resident) is chosen from the
    registry by ``ctx.on`` and ``ctx.resident``.
    """

    name = "PAYE"

    def __init__(self, schedules: ScheduleRegistry = PAYE_SCHEDULES) -> None:
        self.schedules = schedules

    def chargeable_income(self, ctx: EmploymentContext) -> Money:
        income = ctx.total_emoluments - ctx.lst_deduction
        if income < Money.zero():
            raise InvalidIncomeError("Local Service Tax deduction exceeds the month's emoluments")
        return income

    def calculate(self, ctx: TaxContext) -> TaxResult:
        emp = self._expect(ctx, EmploymentContext)
        schedule = self.schedules.for_date(emp.on, emp.resident)
        income = self.chargeable_income(emp)
        exact, lines = schedule.tax_on(income)
        due = exact.round()
        notes = [schedule.name]
        if emp.lst_deduction:
            notes.append(f"LST of {emp.lst_deduction} deducted before PAYE")
        if due != exact:
            lines += (TaxLine(f"exact {exact.amount:,} rounded half-up to the shilling", due - exact),)
        return TaxResult(self.name, income, due, lines, tuple(notes))
