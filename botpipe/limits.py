"""Validated execution limits owned by one run, independent of client defaults."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunLimits:
    max_operations: int = 1000
    timeout: float = 3600.0

    def __post_init__(self):
        if type(self.max_operations) is not int or self.max_operations < 1:
            raise ValueError("max_operations must be a positive integer")
        try:
            valid_timeout = (
                type(self.timeout) in (int, float)
                and math.isfinite(self.timeout)
                and self.timeout > 0
            )
        except OverflowError:
            valid_timeout = False
        if not valid_timeout:
            raise ValueError("timeout must be a finite positive number")
        object.__setattr__(self, "timeout", float(self.timeout))

    @classmethod
    def from_record(cls, record):
        return cls(record["max_operations"], record["timeout"])
