"""Custom exception hierarchy. Catch ``TaxError`` to handle any tax failure."""

from __future__ import annotations

from datetime import date


class TaxError(Exception):
    """Base class for every error raised by the tax engine."""


class InvalidIncomeError(TaxError, ValueError):
    """An amount is negative, missing or otherwise impossible (e.g. negative gross pay)."""


class NoScheduleForDateError(TaxError, LookupError):
    """No rate schedule is in force on the requested date."""

    def __init__(self, tax: str, on: date) -> None:
        super().__init__(f"No {tax} schedule is in force on {on.isoformat()}")
        self.tax = tax
        self.on = on


class UnsupportedContextError(TaxError, TypeError):
    """A tax was given a context it cannot compute (e.g. VAT given a payslip)."""
