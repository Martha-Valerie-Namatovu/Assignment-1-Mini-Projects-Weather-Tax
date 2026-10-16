"""``Money``: an immutable amount of Uganda shillings backed by ``decimal.Decimal``.

Rounding rules (explicit, in one place):

* Arithmetic is exact. ``Money`` keeps full ``Decimal`` precision through a
  calculation, so intermediate rounding never accumulates.
* ``Money.round()`` rounds to the whole shilling with ``ROUND_HALF_UP``
  (0.5 goes up). The UGX has no coins below one shilling in circulation, and
  half-up is how tax tables and payslips are normally rounded. Banker's rounding
  (Python's default for ``round``) would turn 2.5 into 2.
* Every ``Tax.calculate`` rounds its final amount exactly once, at the end.

Floats are refused at construction: ``Money(0.1)`` raises ``TypeError``,
because the float already carries a binary rounding error
(``Decimal(0.1)`` is 0.1000000000000000055511151231257827...).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import total_ordering
from typing import Union

Number = Union[int, Decimal]
SHILLING = Decimal("1")


def to_decimal(value: object) -> Decimal:
    """Convert an int, str or Decimal to ``Decimal``. Floats and bools are rejected."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"Use int, str or Decimal for money and rates, not {type(value).__name__} ({value!r})")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(value.replace(",", "").strip() if isinstance(value, str) else value)
        except InvalidOperation as exc:
            raise ValueError(f"Not a valid amount: {value!r}") from exc
    else:
        raise TypeError(f"Cannot convert {type(value).__name__} to Decimal")
    if not result.is_finite():
        raise ValueError(f"Amount must be finite, got {value!r}")
    return result


@total_ordering
class Money:
    """An amount of UGX. Immutable and hashable, so it is safe as a dict key or default.

    Supported operators: ``+``/``-`` with Money (and ``sum()``), ``*`` and ``/``
    by an int or Decimal, ``Money / Money`` giving a Decimal ratio, unary ``-``,
    ``abs``, comparisons and ``bool``.
    """

    __slots__ = ("_amount",)
    currency = "UGX"

    def __init__(self, amount: Number | str | "Money" = 0) -> None:
        self._amount = amount.amount if isinstance(amount, Money) else to_decimal(amount)

    @property
    def amount(self) -> Decimal:
        """The underlying exact Decimal."""
        return self._amount

    @classmethod
    def zero(cls) -> "Money":
        return cls(0)

    # -- rounding -----------------------------------------------------------------
    def round(self, quantum: Decimal = SHILLING) -> "Money":
        """Round half-up to ``quantum`` (default: one shilling)."""
        return Money(self._amount.quantize(quantum, rounding=ROUND_HALF_UP))

    # -- arithmetic ---------------------------------------------------------------
    def _other(self, other: object) -> Decimal:
        if isinstance(other, Money):
            return other._amount
        raise TypeError(f"Can only combine Money with Money, not {type(other).__name__}")

    def __add__(self, other: "Money") -> "Money":
        return Money(self._amount + self._other(other))

    def __radd__(self, other: object) -> "Money":
        if other == 0:  # lets sum() start from the int 0
            return self
        return Money(self._other(other) + self._amount)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self._amount - self._other(other))

    def __mul__(self, factor: Number) -> "Money":
        if isinstance(factor, Money):
            raise TypeError("Money * Money has no meaning (UGX²); multiply by a rate instead")
        return Money(self._amount * to_decimal(factor))

    __rmul__ = __mul__

    def __truediv__(self, other: Number | "Money") -> "Money | Decimal":
        if isinstance(other, Money):
            if other._amount == 0:
                raise ZeroDivisionError("division by zero Money")
            return self._amount / other._amount
        divisor = to_decimal(other)
        if divisor == 0:
            raise ZeroDivisionError("division of Money by zero")
        return Money(self._amount / divisor)

    def __neg__(self) -> "Money":
        return Money(-self._amount)

    def __abs__(self) -> "Money":
        return Money(abs(self._amount))

    # -- comparison ---------------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        if isinstance(other, Money):
            return self._amount == other._amount
        return NotImplemented

    def __lt__(self, other: "Money") -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._amount < other._amount

    def __hash__(self) -> int:
        return hash((self.currency, self._amount))

    def __bool__(self) -> bool:
        return self._amount != 0

    # -- display ------------------------------------------------------------------
    def __repr__(self) -> str:
        return f"Money('{self._amount}')"

    def __str__(self) -> str:
        sign = "-" if self._amount < 0 else ""
        whole = abs(self._amount).quantize(SHILLING, rounding=ROUND_HALF_UP)
        return f"{sign}UGX {whole:,}"

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)

