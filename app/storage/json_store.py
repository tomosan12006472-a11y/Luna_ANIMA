from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable

from .._shared_utils import (
    JsonStoreReadError,
    read_json_with_retry,
    write_json_atomic,
)


class JsonStore:
    def __init__(
        self,
        path: Path,
        *,
        default_factory: Callable[[], Any],
        label: str,
        lock: Any | None = None,
        validator: Callable[[Any], Any] | None = None,
    ) -> None:
        self.path = path
        self.default_factory = default_factory
        self.label = label
        self.lock = lock
        self.validator = validator

    def _guard(self) -> Any:
        return self.lock if self.lock is not None else nullcontext()

    def _default(self) -> Any:
        return self.default_factory()

    def _validate(self, data: Any, *, strict: bool) -> Any:
        if self.validator is None:
            return data
        try:
            return self.validator(data)
        except Exception as exc:
            if strict:
                raise JsonStoreReadError(f"{self.label} is invalid") from exc
            return self._default()

    def _read_unlocked(self, *, strict: bool) -> Any:
        if not self.path.exists():
            return self._default()
        try:
            data = read_json_with_retry(self.path, label=self.label)
        except JsonStoreReadError:
            if strict:
                raise
            return self._default()
        except Exception as exc:
            if strict:
                raise JsonStoreReadError(f"{self.label} is temporarily unreadable") from exc
            return self._default()
        return self._validate(data, strict=strict)

    def _write_unlocked(self, data: Any) -> None:
        write_json_atomic(self.path, data)

    def read(self, *, strict: bool = False) -> Any:
        with self._guard():
            return self._read_unlocked(strict=strict)

    def write(self, data: Any) -> None:
        with self._guard():
            self._write_unlocked(data)

    def update(self, fn: Callable[[Any], Any], *, strict: bool = True) -> Any:
        with self._guard():
            current = self._read_unlocked(strict=strict)
            updated = fn(current)
            self._write_unlocked(updated)
            return updated
