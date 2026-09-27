from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from typing import Any, ClassVar


class Row:
    """Data-only mixin that serializes a row dataclass's own values."""

    __dataclass_fields__: ClassVar[dict[str, Any]]

    def to_dict(self, fields: Iterable[str] | None = None, *, prefix: str = "") -> dict[str, Any]:
        """Return all declared fields, or exactly the named ones, keyed with an optional prefix."""
        declared = [field.name for field in dataclasses.fields(self)]
        names = declared if fields is None else list(fields)
        unknown = [name for name in names if name not in declared]
        if unknown:
            raise ValueError(f"{type(self).__name__} has no fields {unknown}")
        return {f"{prefix}{name}": getattr(self, name) for name in names}
