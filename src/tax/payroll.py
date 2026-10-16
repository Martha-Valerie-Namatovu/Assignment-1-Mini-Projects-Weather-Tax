"""Payroll pipeline: LST -> PAYE -> NSSF -> net pay, composed from the individual taxes.

Order of deductions, and why:

1. **Local Service Tax first.** The Income Tax Act allows LST paid to be
   deducted in computing chargeable income, so PAYE cannot be computed until the
   month's LST instalment is known.
2. **PAYE second**, on gross pay + taxable allowances − LST.
3. **NSSF last**, on gross wages. In Uganda the employee's 5% is *not*
   deductible for PAYE (unlike, say, Kenya's pension relief), so it does not feed
   into step 2 and its position only affects presentation. Employer 10% is a cost
   to the employer, not a payslip deduction.
4. **Net pay** = gross + allowances − LST − PAYE − employee NSSF.

The pipeline *has* its taxes (composition) rather than *being* one: a payslip
is not a tax, and swapping a component (e.g. a different LST schedule) needs
no subclass.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .context import EmploymentContext
from .lst import LocalServiceTax
from .money import Money
from .nssf import NSSF
from .paye import PAYE


@dataclass(frozen=True)
class Payslip:
    """All amounts in whole shillings."""

    employee: str
    gross_pay: Money
    allowances: Money
    lst: Money
    paye: Money
    nssf_employee: Money
    nssf_employer: Money

    @property
    def total_deductions(self) -> Money:
        return self.lst + self.paye + self.nssf_employee

    @property
    def net_pay(self) -> Money:
        return self.gross_pay + self.allowances - self.total_deductions

    @property
    def employer_cost(self) -> Money:
        return self.gross_pay + self.allowances + self.nssf_employer

    def as_row(self) -> dict[str, int]:
        """Plain ints for a pandas DataFrame (display only; no further arithmetic)."""
        fields = {"Gross": self.gross_pay, "Allowances": self.allowances, "LST": self.lst,
                  "PAYE": self.paye, "NSSF (5%)": self.nssf_employee, "Net pay": self.net_pay,
                  "Employer NSSF (10%)": self.nssf_employer, "Employer cost": self.employer_cost}
        return {"Employee": self.employee, **{k: int(v.amount) for k, v in fields.items()}}

    def __str__(self) -> str:
        rows = [("Gross pay", self.gross_pay), ("Allowances", self.allowances),
                ("Local Service Tax", -self.lst), ("PAYE", -self.paye),
                ("NSSF employee 5%", -self.nssf_employee), ("Net pay", self.net_pay),
                ("(Employer NSSF 10%)", self.nssf_employer)]
        return f"Payslip: {self.employee}\n" + "\n".join(f"  {k:<22}{v:>18}" for k, v in rows)


class PayrollPipeline:
    """Runs the deductions in order for one employee-month."""

    def __init__(self, paye: PAYE | None = None, nssf: NSSF | None = None,
                 lst: LocalServiceTax | None = None) -> None:
        self.paye = paye or PAYE()
        self.nssf = nssf or NSSF()
        self.lst = lst or LocalServiceTax(enabled=False)

    def run(self, ctx: EmploymentContext, employee: str = "employee") -> Payslip:
        lst = self.lst.calculate(ctx).amount
        paye_ctx = replace(ctx, lst_deduction=lst)
        paye = self.paye.calculate(paye_ctx).amount
        nssf = self.nssf.calculate(ctx)
        return Payslip(employee, ctx.gross_pay, ctx.allowances, lst, paye, nssf.amount,
                       self.nssf.employer_contribution(ctx))
