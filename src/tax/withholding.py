"""Extension A: withholding tax and rental income tax for individuals.

Rates: PwC Uganda, "Taxes on personal income" and "Withholding taxes"
(https://taxsummaries.pwc.com/uganda, reviewed Jan 2026) and URA, "Rental
Income Tax" (https://ura.go.ug/?p=40935). Verify before use.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .base import Tax
from .context import TaxContext, TaxLine, TaxResult, _require_non_negative
from .errors import TaxError
from .money import Money


class PaymentType(Enum):
    DIVIDEND = "dividend"
    DIVIDEND_LISTED = "dividend from a listed company"
    INTEREST = "interest"
    GOODS_AND_SERVICES = "goods and services (designated agent)"
    PROFESSIONAL_FEES = "professional fees"
    ROYALTIES = "royalties"
    MANAGEMENT_FEES = "management fees"


@dataclass(frozen=True)
class WithholdingContext(TaxContext):
    """One payment from which the payer must withhold tax."""

    payment: Money = Money.zero()
    payment_type: PaymentType = PaymentType.GOODS_AND_SERVICES
    payee_resident: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_non_negative(payment=self.payment)


@dataclass(frozen=True)
class WithholdingRule:
    rate: Decimal
    threshold: Money = Money.zero()   # payments below this are not subject to WHT


D = Decimal
DEFAULT_WHT_RULES: dict[tuple[PaymentType, bool], WithholdingRule] = {
    (PaymentType.DIVIDEND, True): WithholdingRule(D("0.15")),
    (PaymentType.DIVIDEND_LISTED, True): WithholdingRule(D("0.10")),
    (PaymentType.DIVIDEND, False): WithholdingRule(D("0.15")),
    (PaymentType.DIVIDEND_LISTED, False): WithholdingRule(D("0.15")),
    (PaymentType.INTEREST, True): WithholdingRule(D("0.15")),
    (PaymentType.INTEREST, False): WithholdingRule(D("0.15")),
    (PaymentType.GOODS_AND_SERVICES, True): WithholdingRule(D("0.06"), Money(1_000_000)),
    (PaymentType.PROFESSIONAL_FEES, True): WithholdingRule(D("0.06")),
    (PaymentType.PROFESSIONAL_FEES, False): WithholdingRule(D("0.15")),
    (PaymentType.ROYALTIES, False): WithholdingRule(D("0.15")),
    (PaymentType.MANAGEMENT_FEES, False): WithholdingRule(D("0.15")),
}


class WithholdingTax(Tax):
    """Tax withheld at source on a single payment."""

    name = "Withholding tax"

    def __init__(self, rules: dict[tuple[PaymentType, bool], WithholdingRule] | None = None) -> None:
        self.rules = dict(DEFAULT_WHT_RULES if rules is None else rules)

    def rule_for(self, payment_type: PaymentType, resident: bool) -> WithholdingRule:
        try:
            return self.rules[(payment_type, resident)]
        except KeyError:
            who = "resident" if resident else "non-resident"
            raise TaxError(f"No withholding rule for {payment_type.value} paid to a {who}") from None

    def calculate(self, ctx: TaxContext) -> TaxResult:
        pay = self._expect(ctx, WithholdingContext)
        rule = self.rule_for(pay.payment_type, pay.payee_resident)
        if pay.payment < rule.threshold:
            return TaxResult(self.name, pay.payment, Money.zero(),
                             notes=(f"below the {rule.threshold} threshold: no WHT",))
        due = (pay.payment * rule.rate).round()
        return TaxResult(self.name, pay.payment, due,
                         (TaxLine(f"{rule.rate:.0%} of {pay.payment_type.value}", due),))


@dataclass(frozen=True)
class RentalContext(TaxContext):
    """An individual landlord's gross rent for one year of income."""

    gross_rent: Money = Money.zero()

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_non_negative(gross_rent=self.gross_rent)


class RentalIncomeTax(Tax):
    """Individuals: 12% of gross annual rent above UGX 2,820,000, no expense deductions."""

    name = "Rental income tax (individual)"

    def __init__(self, rate: Decimal = D("0.12"), threshold: Money = Money(2_820_000)) -> None:
        self.rate = rate
        self.threshold = threshold

    def calculate(self, ctx: TaxContext) -> TaxResult:
        rent = self._expect(ctx, RentalContext)
        excess = rent.gross_rent - self.threshold
        base = excess if excess > Money.zero() else Money.zero()
        due = (base * self.rate).round()
        return TaxResult(self.name, base, due,
                         (TaxLine(f"{self.rate:.0%} of rent above {self.threshold}", due),))
