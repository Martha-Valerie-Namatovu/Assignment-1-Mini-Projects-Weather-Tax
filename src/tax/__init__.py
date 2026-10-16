"""Mini-project 2: an extensible Uganda tax engine built on ``Decimal`` money."""

from .base import Tax
from .cit import CorporateIncomeTax
from .context import (CorporateContext, EmploymentContext, Invoice, SupplyType, TaxContext, TaxLine,
                      TaxResult, VATContext)
from .errors import InvalidIncomeError, NoScheduleForDateError, TaxError, UnsupportedContextError
from .lst import LocalServiceTax
from .money import Money
from .nssf import NSSF
from .paye import PAYE
from .payroll import PayrollPipeline, Payslip
from .planner import DividendScenario, SalaryScenario, Scenario, TaxPlanner
from .schedules import (PAYE_RESIDENT_2012, PAYE_RESIDENT_2026, PAYE_SCHEDULES, Band, ProgressiveSchedule,
                        ScheduleRegistry, SchedulePeriod)
from .vat import VAT
from .withholding import PaymentType, RentalContext, RentalIncomeTax, WithholdingContext, WithholdingTax

__all__ = [name for name in dir() if not name.startswith("_")]
