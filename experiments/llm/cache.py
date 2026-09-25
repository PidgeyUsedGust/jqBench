"""Atomic cache for fresh OpenRouter responses; archived v1 caches are not writable."""

import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

FORMAT = "jqbench-openrouter-2"
_locks = {}
_guard = threading.Lock()


class JsonCache:
    def __init__(self, path):
        self.path = Path(path).resolve()
        with _guard:
            self.lock = _locks.setdefault(self.path, threading.RLock())
        with self.lock:
            self._read()

    def get_or_create(self, request, create):
        # Serialize the full lookup/call/write transaction across instances sharing a file.
        with self.lock:
            data = self._read()
            key = request_key(request)
            if key in data:
                return deepcopy(data[key])
            response = create()
            data[key] = deepcopy(response)
            self._write(data)
            return response

    def _read(self):
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if (
            not isinstance(payload, dict)
            or payload.get("format") != FORMAT
            or not isinstance(payload.get("responses"), dict)
        ):
            raise ValueError(
                f"{self.path} is not a fresh-run {FORMAT} cache; use a new cache path"
            )
        return payload["responses"]

    def _write(self, responses):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(
                    {"format": FORMAT, "responses": responses},
                    handle,
                    ensure_ascii=False,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def request_key(request):
    return json.dumps(
        {"provider": "openrouter", "request": request},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
