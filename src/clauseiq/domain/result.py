"""A minimal, typed ``Result[T, E]`` for modelling expected failures.

Why this exists
---------------
Raising exceptions for *expected* failure paths (no search hits, low retrieval
confidence, a transient backend error) makes those paths invisible in type
signatures and easy to forget. ``Result`` makes the failure channel explicit:
``retrieve(...) -> Result[list[Chunk], RetrievalError]`` tells the caller, at
the type level, that retrieval can fail and *how*. Unexpected/programmer errors
still raise (see :mod:`clauseiq.domain.exceptions`).

The API is intentionally a small subset of Rust's ``Result`` — ``map``,
``map_err``, ``and_then``, ``unwrap``/``unwrap_or`` and friends — which is
enough to compose pipelines without nested ``try``/``except``.

Pattern matching is supported via ``__match_args__``::

    match await retrieve(q):
        case Ok(chunks):
            ...
        case Err(error):
            log.warning("retrieval_failed", code=error.code)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, NoReturn, TypeAlias, TypeVar, final

from clauseiq.domain.exceptions import UnwrapError

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


@final
@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """The success variant, wrapping a value of type ``T``."""

    value: T

    def is_ok(self) -> bool:
        """Return ``True`` — this is the success variant."""
        return True

    def is_err(self) -> bool:
        """Return ``False`` — this is not the error variant."""
        return False

    def ok(self) -> T:
        """Return the wrapped success value."""
        return self.value

    def err(self) -> None:
        """Return ``None`` — there is no error to expose."""
        return None

    def unwrap(self) -> T:
        """Return the success value."""
        return self.value

    def unwrap_or(self, _default: U, /) -> T:
        """Return the success value, ignoring ``_default``."""
        return self.value

    def unwrap_or_else(self, _fn: Callable[[object], T], /) -> T:
        """Return the success value, ignoring the fallback function."""
        return self.value

    def unwrap_err(self) -> NoReturn:
        """Raise :class:`UnwrapError` — there is no error to return."""
        raise UnwrapError("called unwrap_err on an Ok value", value=self.value)

    def expect(self, _message: str, /) -> T:
        """Return the success value (``_message`` only used by :class:`Err`)."""
        return self.value

    def map(self, fn: Callable[[T], U], /) -> Ok[U]:
        """Apply ``fn`` to the success value, returning a new :class:`Ok`."""
        return Ok(fn(self.value))

    def map_err(self, _fn: Callable[[object], F], /) -> Ok[T]:
        """Return self unchanged — there is no error to transform."""
        return self

    def and_then(self, fn: Callable[[T], Result[U, F]], /) -> Result[U, F]:
        """Chain a fallible operation onto the success value."""
        return fn(self.value)


@final
@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """The failure variant, wrapping an error of type ``E``."""

    error: E

    def is_ok(self) -> bool:
        """Return ``False`` — this is not the success variant."""
        return False

    def is_err(self) -> bool:
        """Return ``True`` — this is the error variant."""
        return True

    def ok(self) -> None:
        """Return ``None`` — there is no success value."""
        return None

    def err(self) -> E:
        """Return the wrapped error."""
        return self.error

    def unwrap(self) -> NoReturn:
        """Raise :class:`UnwrapError`, chaining the wrapped error as the cause."""
        cause = self.error if isinstance(self.error, Exception) else None
        raise UnwrapError("called unwrap on an Err value", cause=cause, error=self.error)

    def unwrap_or(self, default: U, /) -> U:
        """Return ``default`` since there is no success value."""
        return default

    def unwrap_or_else(self, fn: Callable[[E], U], /) -> U:
        """Compute a fallback from the wrapped error."""
        return fn(self.error)

    def unwrap_err(self) -> E:
        """Return the wrapped error."""
        return self.error

    def expect(self, message: str, /) -> NoReturn:
        """Raise :class:`UnwrapError` with a caller-supplied ``message``."""
        cause = self.error if isinstance(self.error, Exception) else None
        raise UnwrapError(message, cause=cause, error=self.error)

    def map(self, _fn: Callable[[object], U], /) -> Err[E]:
        """Return self unchanged — there is no success value to transform."""
        return self

    def map_err(self, fn: Callable[[E], F], /) -> Err[F]:
        """Apply ``fn`` to the wrapped error, returning a new :class:`Err`."""
        return Err(fn(self.error))

    def and_then(self, _fn: Callable[[object], Result[U, F]], /) -> Err[E]:
        """Return self unchanged — the chain short-circuits on error."""
        return self


Result: TypeAlias = Ok[T] | Err[E]
"""A value that is either :class:`Ok` (success) or :class:`Err` (failure)."""


def is_ok(result: Result[T, E]) -> bool:
    """Functional helper mirroring :meth:`Ok.is_ok` for use as a predicate."""
    return result.is_ok()


def is_err(result: Result[T, E]) -> bool:
    """Functional helper mirroring :meth:`Err.is_err` for use as a predicate."""
    return result.is_err()


__all__ = ["Err", "Ok", "Result", "is_err", "is_ok"]
