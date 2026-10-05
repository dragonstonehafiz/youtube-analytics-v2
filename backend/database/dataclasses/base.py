from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar, TypeVar

R = TypeVar("R", bound="Row")


class Row:
    """Data-only mixin that converts a row dataclass to and from plain dictionaries."""

    __dataclass_fields__: ClassVar[dict[str, Any]]

    @classmethod
    def from_dict(cls: type[R], data: Mapping[str, Any]) -> R:
        """Build a row from a mapping of field names; absent fields stay None, unknown keys raise."""
        declared = {field.name for field in dataclasses.fields(cls)}
        unknown = [name for name in data if name not in declared]
        if unknown:
            raise ValueError(f"{cls.__name__} has no fields {unknown}")
        return cls(**data)

    def to_dict(self, fields: Iterable[str] | None = None, *, prefix: str = "") -> dict[str, Any]:
        """Return all declared fields, or exactly the named ones, keyed with an optional prefix."""
        declared = [field.name for field in dataclasses.fields(self)]
        names = declared if fields is None else list(fields)
        unknown = [name for name in names if name not in declared]
        if unknown:
            raise ValueError(f"{type(self).__name__} has no fields {unknown}")
        return {f"{prefix}{name}": getattr(self, name) for name in names}
