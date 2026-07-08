"""Service-layer primitives shared by domain modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ServiceResult(Generic[T]):
    ok: bool
    value: T | None = None
    error: str = ""

    @classmethod
    def success(cls, value: T | None = None) -> "ServiceResult[T]":
        return cls(ok=True, value=value)

    @classmethod
    def failure(cls, error: str) -> "ServiceResult[T]":
        return cls(ok=False, error=error)
