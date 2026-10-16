"""The abstract ``Tax`` interface every tax implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from .context import TaxContext, TaxResult
from .errors import UnsupportedContextError

C = TypeVar("C", bound=TaxContext)


class Tax(ABC):
    """A tax that turns a context into a result.

    Subclasses set ``name`` and implement ``calculate``. Callers can treat any
    tax polymorphically, e.g. ``[t.calculate(ctx) for t in taxes]``.
    """

    name: str = "Tax"

    @abstractmethod
    def calculate(self, ctx: TaxContext) -> TaxResult:
        """Compute the tax due for ``ctx``. Never returns silently on bad input: raises ``TaxError``."""

    def _expect(self, ctx: TaxContext, kind: type[C]) -> C:
        """Return ``ctx`` typed as ``kind``, or raise ``UnsupportedContextError``."""
        if not isinstance(ctx, kind):
            raise UnsupportedContextError(f"{self.name} needs a {kind.__name__}, got {type(ctx).__name__}")
        return ctx

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"
