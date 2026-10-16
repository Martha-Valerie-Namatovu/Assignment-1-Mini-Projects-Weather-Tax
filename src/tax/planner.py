"""Extension B: ``TaxPlanner`` compares ways of extracting a company's profit.

An owner-manager of a resident company has pre-tax profit ``P`` for the month.
They can take it as:

* **Salary**: the company pays gross salary ``S`` plus employer NSSF (10%), and
  both are deductible, so ``S = P / 1.10`` leaves no corporate profit. The owner
  pays PAYE and employee NSSF (5%) on ``S``.
* **Dividend**: the company pays corporate tax (30%) on ``P``, then distributes
  the rest. The dividend suffers 15% withholding tax, which is a final tax for
  resident individuals.

Simplifications, stated so the comparison is not over-read: corporate tax is
applied to one month's profit pro rata (in reality it is annual, with
provisional instalments); NSSF is counted as a cost, though it is the owner's
own retirement saving; LST is ignored; the salary must be "reasonable" for the
work done or URA may recharacterise it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .cit import CorporateIncomeTax
from .context import CorporateContext, EmploymentContext
from .errors import InvalidIncomeError
from .money import Money
from .nssf import NSSF
from .paye import PAYE
from .withholding import PaymentType, WithholdingContext, WithholdingTax


@dataclass(frozen=True)
class Outcome:
    """Where the profit went under one scenario. Shares sum to the profit (± rounding)."""

    scenario: str
    profit: Money
    to_owner: Money
    taxes: dict[str, Money]

    @property
    def total_tax(self) -> Money:
        return sum(self.taxes.values(), Money.zero())

    @property
    def effective_rate(self) -> Decimal:
        """Share of profit lost to tax and NSSF, as an exact Decimal."""
        return self.total_tax / self.profit if self.profit else Decimal(0)


class Scenario(ABC):
    """A strategy for paying profit out. Subclasses implement ``evaluate``."""

    name: str = "scenario"

    @abstractmethod
    def evaluate(self, profit: Money, on: date) -> Outcome:
        """Split ``profit`` between taxes and the owner."""


class SalaryScenario(Scenario):
    name = "Salary"

    def __init__(self, paye: PAYE | None = None, nssf: NSSF | None = None) -> None:
        self.paye = paye or PAYE()
        self.nssf = nssf or NSSF()

    def evaluate(self, profit: Money, on: date) -> Outcome:
        gross = (profit / (1 + self.nssf.employer_rate)).round()
        ctx = EmploymentContext(on=on, gross_pay=gross)
        paye = self.paye.calculate(ctx).amount
        employee_nssf = self.nssf.calculate(ctx).amount
        employer_nssf = profit - gross  # whatever is left funds the employer share (absorbs rounding)
        return Outcome(self.name, profit, gross - paye - employee_nssf,
                       {"PAYE": paye, "NSSF employee": employee_nssf, "NSSF employer": employer_nssf})


class DividendScenario(Scenario):
    name = "Dividend"

    def __init__(self, cit: CorporateIncomeTax | None = None, wht: WithholdingTax | None = None,
                 listed: bool = False) -> None:
        self.cit = cit or CorporateIncomeTax()
        self.wht = wht or WithholdingTax()
        self.listed = listed

    def evaluate(self, profit: Money, on: date) -> Outcome:
        cit = self.cit.calculate(CorporateContext(on=on, revenue=profit)).amount
        dividend = profit - cit
        kind = PaymentType.DIVIDEND_LISTED if self.listed else PaymentType.DIVIDEND
        wht = self.wht.calculate(WithholdingContext(on=on, payment=dividend, payment_type=kind)).amount
        return Outcome(self.name, profit, dividend - wht, {"Corporate tax": cit, "WHT on dividend": wht})


@dataclass(frozen=True)
class Comparison:
    a: Outcome
    b: Outcome

    @property
    def better(self) -> Outcome:
        return self.a if self.a.to_owner >= self.b.to_owner else self.b

    @property
    def difference(self) -> Money:
        """How much more the owner keeps under ``a`` than under ``b`` (negative: ``b`` is better)."""
        return self.a.to_owner - self.b.to_owner

    def __str__(self) -> str:
        return (f"{self.a.scenario}: owner keeps {self.a.to_owner} (tax {self.a.effective_rate:.1%}); "
                f"{self.b.scenario}: owner keeps {self.b.to_owner} (tax {self.b.effective_rate:.1%}). "
                f"{self.better.scenario} is better by {abs(self.difference)}.")


class TaxPlanner:
    """Compare two scenarios for the same profit and date."""

    def __init__(self, a: Scenario | None = None, b: Scenario | None = None) -> None:
        self.a = a or SalaryScenario()
        self.b = b or DividendScenario()

    def compare(self, profit: Money, on: date) -> Comparison:
        if profit <= Money.zero():
            raise InvalidIncomeError("Profit to distribute must be positive")
        return Comparison(self.a.evaluate(profit, on), self.b.evaluate(profit, on))

    def breakeven(self, on: date, low: Money = Money(100_000), high: Money = Money(100_000_000),
                  tolerance: Money = Money(1_000)) -> Money | None:
        """Profit at which the two scenarios leave the owner the same amount (bisection).

        Returns ``None`` if the better scenario is the same at both ends of the range.
        """
        def gap(p: Money) -> Money:
            return self.compare(p, on).difference

        if (gap(low) > Money.zero()) == (gap(high) > Money.zero()):
            return None
        while high - low > tolerance:
            mid = ((low + high) / 2).round()
            if (gap(mid) > Money.zero()) == (gap(low) > Money.zero()):
                low = mid
            else:
                high = mid
        return high
