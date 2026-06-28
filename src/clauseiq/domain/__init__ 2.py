"""Pure domain layer for ClauseIQ.

This package contains only business types and interfaces. It has **no**
third-party dependencies and imports nothing from the application,
infrastructure, or interface layers. Everything here is deterministic and
trivially unit-testable, which is why the test suite targets >85% coverage on
this package specifically.
"""

from __future__ import annotations
