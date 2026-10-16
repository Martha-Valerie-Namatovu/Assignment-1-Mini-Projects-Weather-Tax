"""Tax engine: band-edge boundary tests, properties (hypothesis), and each module."""

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st

from src.tax import (NSSF, PAYE, PAYE_RESIDENT_2012, PAYE_RESIDENT_2026, PAYE_SCHEDULES, VAT,
                     CorporateContext, CorporateIncomeTax, EmploymentContext, InvalidIncomeError, Invoice,
                     LocalServiceTax, Money, NoScheduleForDateError, PaymentType, PayrollPipeline,
                     RentalContext, RentalIncomeTax, SupplyType, TaxError, TaxPlanner,
                     UnsupportedContextError, VATContext, WithholdingContext, WithholdingTax)

FY2026 = date(2026, 10, 1)   # 2026/27 schedule (the brief's baseline)
FY2025 = date(2026, 3, 1)    # 2025/26 schedule


def paye(income, on=FY2026, resident=True, **kw):
    return PAYE().calculate(EmploymentContext(on=on, gross_pay=Money(income), resident=resident, **kw))


# ---------------------------------------------------------------- PAYE band edges (brief's baseline)
@pytest.mark.parametrize("income, exact", [
    (0, "0"),
    (335_000, "0"),                        # top of the nil band
    (335_001, "0.20"),                     # first shilling taxed at 20%
    (410_000, "15000"),                    # 20% × 75,000
    (485_000, "33750"),                    # 15,000 + 25% × 75,000
    (10_000_000, "2888250"),               # 33,750 + 30% × 9,515,000
    (10_000_001, "2888250.40"),            # + 30% and the 10% surcharge on the extra shilling
])
def test_paye_2026_band_edges_exact(income, exact):
    tax, _ = PAYE_RESIDENT_2026.tax_on(Money(income))
    assert tax == Money(exact)


@pytest.mark.parametrize("income, due", [
    (335_000, 0), (335_001, 0), (410_000, 15_000), (485_000, 33_750),
    (10_000_000, 2_888_250), (10_000_001, 2_888_250), (10_000_002, 2_888_251),
])
def test_paye_2026_band_edges_rounded(income, due):
    assert paye(income).amount == Money(due)


def test_fixed_amounts_in_brief_are_derived_not_typed():
    assert PAYE_RESIDENT_2026.fixed_amount_at(Money(410_000)) == Money(15_000)
    assert PAYE_RESIDENT_2026.fixed_amount_at(Money(485_000)) == Money(33_750)


@pytest.mark.parametrize("income, due", [
    (235_000, 0), (235_001, 0), (335_000, 10_000), (410_000, 25_000), (1_000_000, 202_000),
    (10_000_000, 2_902_000),
])
def test_paye_2025_26_schedule(income, due):
    assert paye(income, on=FY2025).amount == Money(due)


@pytest.mark.parametrize("income, due", [(335_000, 33_500), (410_000, 48_500), (1_000_000, 225_500)])
def test_paye_non_resident_has_no_nil_band(income, due):
    assert paye(income, resident=False).amount == Money(due)


def test_schedule_switches_on_1_july_2026():
    assert PAYE_SCHEDULES.for_date(date(2026, 6, 30)) is PAYE_RESIDENT_2012
    assert PAYE_SCHEDULES.for_date(date(2026, 7, 1)) is PAYE_RESIDENT_2026


def test_no_schedule_before_2012_raises():
    with pytest.raises(NoScheduleForDateError):
        paye(1_000_000, on=date(2010, 1, 31))


def test_allowances_are_taxed_and_lst_is_deducted():
    base = paye(1_000_000).amount
    assert paye(800_000, allowances=Money(200_000)).amount == base
    assert paye(1_000_000, lst_deduction=Money(25_000)).amount == (base - Money(25_000) * Decimal("0.30")).round()


def test_negative_income_rejected():
    with pytest.raises(InvalidIncomeError):
        EmploymentContext(on=FY2026, gross_pay=Money(-1))
    with pytest.raises(TaxError):              # InvalidIncomeError is a TaxError
        PAYE_RESIDENT_2026.tax_on(Money(-5))


def test_wrong_context_type_is_an_error():
    with pytest.raises(UnsupportedContextError):
        PAYE().calculate(VATContext(on=FY2026))


# ---------------------------------------------------------------- properties (hypothesis)
incomes = st.integers(min_value=0, max_value=60_000_000)
dates = st.sampled_from([FY2025, FY2026])


@given(incomes, dates, st.booleans())
def test_paye_never_negative_and_never_exceeds_income(income, on, resident):
    due = paye(income, on=on, resident=resident).amount
    assert Money.zero() <= due <= Money(income)


@given(incomes, incomes, dates, st.booleans())
def test_paye_is_monotonic_in_income(a, b, on, resident):
    lo, hi = sorted((a, b))
    assert paye(lo, on=on, resident=resident).amount <= paye(hi, on=on, resident=resident).amount


@settings(max_examples=200)
@given(st.decimals(min_value=0, max_value=50_000_000, places=2), dates)
def test_paye_exact_tax_properties_hold_with_cents(income, on):
    tax, _ = PAYE_SCHEDULES.for_date(on).tax_on(Money(income))
    assert Money.zero() <= tax <= Money(income)


# ---------------------------------------------------------------- NSSF, LST, payroll
def test_nssf_employee_and_employer_shares():
    ctx = EmploymentContext(on=FY2026, gross_pay=Money(1_000_000), allowances=Money(200_000))
    nssf = NSSF()
    assert nssf.calculate(ctx).amount == Money(60_000)
    assert nssf.employer_contribution(ctx) == Money(120_000)
    assert NSSF(include_allowances=False).calculate(ctx).amount == Money(50_000)


@pytest.mark.parametrize("monthly, annual", [(100_000, 0), (100_001, 5_000), (550_000, 40_000),
                                             (1_000_000, 90_000), (1_000_001, 100_000)])
def test_lst_annual_bands(monthly, annual):
    assert LocalServiceTax().annual_amount(Money(monthly)) == Money(annual)


def test_lst_only_collected_july_to_october():
    lst = LocalServiceTax()
    ctx = lambda m: EmploymentContext(on=date(2026, m, 1), gross_pay=Money(2_000_000))
    assert lst.calculate(ctx(8)).amount == Money(25_000)
    assert lst.calculate(ctx(11)).amount == Money.zero()
    assert LocalServiceTax(enabled=False).calculate(ctx(8)).amount == Money.zero()


def test_payroll_pipeline_hand_calculation():
    # Gross 2,500,000 + allowances 300,000 in August 2026 (an LST month):
    #   LST    = 100,000 / 4                                  =    25,000
    #   PAYE   = 33,750 + 30% × (2,775,000 − 485,000)         =   720,750
    #   NSSF   = 5% × 2,800,000                               =   140,000
    #   Net    = 2,800,000 − 25,000 − 720,750 − 140,000       = 1,914,250
    ctx = EmploymentContext(on=date(2026, 8, 1), gross_pay=Money(2_500_000), allowances=Money(300_000))
    slip = PayrollPipeline(lst=LocalServiceTax()).run(ctx, "Test")
    assert (slip.lst, slip.paye, slip.nssf_employee) == (Money(25_000), Money(720_750), Money(140_000))
    assert slip.net_pay == Money(1_914_250)
    assert slip.employer_cost == Money(3_080_000)


# ---------------------------------------------------------------- VAT
def inv(n, amount, supply, sale=True):
    return Invoice(n, Money(amount), supply, sale)


def test_vat_standard_zero_and_purchases():
    ctx = VATContext(on=FY2026, invoices=(
        inv("S1", 10_000_000, SupplyType.STANDARD), inv("S2", 5_000_000, SupplyType.ZERO),
        inv("P1", 4_000_000, SupplyType.STANDARD, sale=False), inv("P2", 1_000_000, SupplyType.EXEMPT, sale=False)))
    # output 18% × 10m = 1.8m; input 18% × 4m = 720k, fully creditable (no exempt sales)
    assert VAT().calculate(ctx).amount == Money(1_080_000)


def test_vat_apportions_input_when_exempt_sales_exist():
    ctx = VATContext(on=FY2026, invoices=(
        inv("S1", 6_000_000, SupplyType.STANDARD), inv("S2", 4_000_000, SupplyType.EXEMPT),
        inv("P1", 5_000_000, SupplyType.STANDARD, sale=False)))
    # output 1,080,000; input 900,000 × 60% taxable share = 540,000
    assert VAT().calculate(ctx).amount == Money(540_000)


def test_vat_exporter_gets_a_credit():
    ctx = VATContext(on=FY2026, invoices=(inv("E1", 20_000_000, SupplyType.ZERO),
                                          inv("P1", 8_000_000, SupplyType.STANDARD, sale=False)))
    result = VAT().calculate(ctx)
    assert result.amount == Money(-1_440_000)
    assert any("refund" in n for n in result.notes)


def test_vat_empty_period_is_zero_and_negative_invoice_rejected():
    assert VAT().calculate(VATContext(on=FY2026)).amount == Money.zero()
    with pytest.raises(InvalidIncomeError):
        inv("X", -1, SupplyType.STANDARD)


# ---------------------------------------------------------------- corporate income tax
def test_cit_on_chargeable_income():
    ctx = CorporateContext(on=FY2026, revenue=Money(500_000_000),
                           deductions={"cost of sales": Money(300_000_000), "salaries": Money(80_000_000)})
    result = CorporateIncomeTax().calculate(ctx)
    assert result.base == Money(120_000_000)
    assert result.amount == Money(36_000_000)


def test_cit_loss_is_not_taxed_and_is_reported():
    ctx = CorporateContext(on=FY2026, revenue=Money(10_000_000), deductions={"costs": Money(12_000_000)})
    result = CorporateIncomeTax().calculate(ctx)
    assert result.amount == Money.zero()
    assert "carried forward" in result.notes[0]


def test_cit_losses_brought_forward_reduce_base():
    ctx = CorporateContext(on=FY2026, revenue=Money(100), losses_brought_forward=Money(40))
    assert CorporateIncomeTax().calculate(ctx).base == Money(60)


# ---------------------------------------------------------------- extensions
def test_withholding_threshold_and_rates():
    wht = WithholdingTax()
    goods = lambda amt: WithholdingContext(on=FY2026, payment=Money(amt))
    assert wht.calculate(goods(999_999)).amount == Money.zero()
    assert wht.calculate(goods(1_000_000)).amount == Money(60_000)
    div = WithholdingContext(on=FY2026, payment=Money(1_000_000), payment_type=PaymentType.DIVIDEND)
    assert wht.calculate(div).amount == Money(150_000)
    with pytest.raises(TaxError):
        wht.calculate(WithholdingContext(on=FY2026, payment=Money(1), payee_resident=False))


def test_rental_income_tax_threshold():
    tax = RentalIncomeTax()
    assert tax.calculate(RentalContext(on=FY2026, gross_rent=Money(2_820_000))).amount == Money.zero()
    assert tax.calculate(RentalContext(on=FY2026, gross_rent=Money(12_000_000))).amount == Money(1_101_600)


def test_planner_outcomes_account_for_all_profit():
    comparison = TaxPlanner().compare(Money(5_000_000), FY2026)
    for outcome in (comparison.a, comparison.b):
        assert outcome.to_owner + outcome.total_tax == outcome.profit
    # Dividend route: 5m − 30% CIT = 3.5m; − 15% WHT = 2,975,000
    assert comparison.b.to_owner == Money(2_975_000)
    with pytest.raises(InvalidIncomeError):
        TaxPlanner().compare(Money.zero(), FY2026)
