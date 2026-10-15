"""Load raw events from JSON arrays or JSON-lines files."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from fapt_guard.acquisition.base import EventSource, RawEvent


def load_json_events(path: str | Path) -> list[RawEvent]:
    p = Path(path)
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        data = json.loads(text)
    elif text.startswith("{") and "\n" not in text:
        data = [json.loads(text)]
    else:
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(data, dict):
        data = data.get("events", [data])
    return [dict(e) for e in data]


class JsonFileSource(EventSource):
    name = "json_file"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def events(self) -> Iterator[RawEvent]:
        yield from load_json_events(self.path)
