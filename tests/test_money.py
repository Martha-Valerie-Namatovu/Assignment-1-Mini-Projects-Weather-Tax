"""Money value object: Decimal only, explicit rounding, operator overloading."""

from decimal import Decimal

import pytest
from hypothesis import given, strategies as st

from src.tax import Money


def test_float_is_refused():
    with pytest.raises(TypeError):
        Money(0.1)
    with pytest.raises(TypeError):
        Money(100) * 0.18


def test_exact_decimal_arithmetic_where_float_fails():
    assert 0.1 + 0.2 != 0.3                                   # the float problem
    assert Money("0.1") + Money("0.2") == Money("0.3")        # Money has none of it
    assert sum([Money("0.10")] * 10) == Money(1)


def test_round_half_up_not_bankers():
    assert round(2.5) == 2                                    # Python's float/default rounding
    assert Money("2.5").round() == Money(3)
    assert Money("100500.5").round() == Money(100501)
    assert Money("-2.5").round() == Money(-3)


def test_operators_and_repr():
    a, b = Money(1_000), Money("250.50")
    assert a + b == Money("1250.50")
    assert a - b == Money("749.50")
    assert a * Decimal("0.18") == Money(180) == Decimal("0.18") * a
    assert a / 4 == Money(250)
    assert a / b == Decimal(1000) / Decimal("250.50")
    assert b < a and a > b and a >= a
    assert repr(b) == "Money('250.50')"
    assert str(Money(1_234_567)) == "UGX 1,234,567"
    assert not Money.zero() and Money(1)


def test_invalid_combinations_raise():
    with pytest.raises(TypeError):
        Money(1) + 1
    with pytest.raises(TypeError):
        Money(1) * Money(2)
    with pytest.raises(ZeroDivisionError):
        Money(1) / 0
    with pytest.raises(ValueError):
        Money("abc")
    with pytest.raises(ValueError):
        Money("NaN")


def test_money_is_hashable_and_immutable():
    assert len({Money(5), Money("5.00")}) == 1
    with pytest.raises(AttributeError):
        Money(5).foo = 1


@given(st.decimals(min_value=-10**12, max_value=10**12, places=2),
       st.decimals(min_value=-10**12, max_value=10**12, places=2))
def test_addition_is_exact_and_commutative(x, y):
    assert Money(x) + Money(y) == Money(y) + Money(x) == Money(x + y)


@given(st.decimals(min_value=0, max_value=10**12, places=4))
def test_rounding_error_is_at_most_half_a_shilling(x):
    assert abs((Money(x).round() - Money(x)).amount) <= Decimal("0.5")
