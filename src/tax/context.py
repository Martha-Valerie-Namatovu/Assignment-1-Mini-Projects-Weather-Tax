"""Inputs (contexts) and outputs (results) shared by every tax.

``TaxContext`` holds what every tax needs: the date the tax relates to, which
selects the rate schedule in force. Each tax family extends it with its own
fields. A small, honest inheritance tree: an ``EmploymentContext`` *is a*
``TaxContext`` with pay details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Mapping

from .errors import InvalidIncomeError
from .money import Money


def _require_non_negative(**amounts: Money) -> None:
    for name, value in amounts.items():
        if not isinstance(value, Money):
            raise InvalidIncomeError(f"{name} must be Money, got {type(value).__name__}")
        if value < Money.zero():
            raise InvalidIncomeError(f"{name} must not be negative, got {value!r}")


@dataclass(frozen=True)
class TaxContext:
    """Base context: the date the computation refers to (e.g. the payroll month)."""

    on: date

    def __post_init__(self) -> None:
        if not isinstance(self.on, date):
            raise TypeError("on must be a datetime.date")


@dataclass(frozen=True)
class EmploymentContext(TaxContext):
    """One employee for one month."""

    gross_pay: Money = Money.zero()
    allowances: Money = Money.zero()          # taxable cash allowances (transport, housing, ...)
    resident: bool = True
    lst_deduction: Money = Money.zero()       # Local Service Tax paid this month, deductible for PAYE

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_non_negative(gross_pay=self.gross_pay, allowances=self.allowances,
                              lst_deduction=self.lst_deduction)

    @property
    def total_emoluments(self) -> Money:
        return self.gross_pay + self.allowances


class SupplyType(Enum):
    """VAT treatment of a supply under the VAT Act, Cap 349."""

    STANDARD = "standard-rated"   # 18%
    ZERO = "zero-rated"           # 0%, input VAT still recoverable (e.g. exports)
    EXEMPT = "exempt"             # outside VAT, input VAT not recoverable (e.g. unprocessed food, education)


@dataclass(frozen=True)
class Invoice:
    """A sale or purchase invoice. ``net`` excludes VAT."""

    number: str
    net: Money
    supply: SupplyType
    is_sale: bool = True

    def __post_init__(self) -> None:
        _require_non_negative(net=self.net)
        if not isinstance(self.supply, SupplyType):
            raise TypeError("supply must be a SupplyType")


@dataclass(frozen=True)
class VATContext(TaxContext):
    """One VAT period's invoices."""

    invoices: tuple[Invoice, ...] = ()

    @property
    def sales(self) -> tuple[Invoice, ...]:
        return tuple(i for i in self.invoices if i.is_sale)

    @property
    def purchases(self) -> tuple[Invoice, ...]:
        return tuple(i for i in self.invoices if not i.is_sale)


@dataclass(frozen=True)
class CorporateContext(TaxContext):
    """One company's year of income."""

    revenue: Money = Money.zero()
    deductions: Mapping[str, Money] = field(default_factory=dict)   # allowable deductions by name
    losses_brought_forward: Money = Money.zero()

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_non_negative(revenue=self.revenue, losses_brought_forward=self.losses_brought_forward,
                              **{f"deduction '{k}'": v for k, v in self.deductions.items()})

    @property
    def total_deductions(self) -> Money:
        return sum(self.deductions.values(), Money.zero())


@dataclass(frozen=True)
class TaxLine:
    """One line of a breakdown, e.g. ('20% of 75,000 over 335,000', Money('15000'))."""

    description: str
    amount: Money


@dataclass(frozen=True)
class TaxResult:
    """What every ``Tax.calculate`` returns.

    Attributes:
        tax: Name of the tax.
        base: The amount the tax was charged on (chargeable income, VAT base, ...).
        amount: Tax due, rounded to the shilling. Negative only for a VAT refund position.
        lines: Breakdown that explains how ``amount`` was reached.
        notes: Anything the reader should know (assumptions, losses carried forward, ...).
    """

    tax: str
    base: Money
    amount: Money
    lines: tuple[TaxLine, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def effective_rate(self) -> Decimal:
        """amount / base as an exact Decimal (0 when the base is zero)."""
        return self.amount / self.base if self.base else Decimal(0)

    def explain(self) -> str:
        rows = [f"{self.tax}: base {self.base}, due {self.amount}"]
        rows += [f"  {line.description:<55} {line.amount:>16}" for line in self.lines]
        rows += [f"  note: {n}" for n in self.notes]
        return "\n".join(rows)
