"""Data-acquisition interfaces.

Every telemetry source (file replay, Sysmon forwarder, synthetic stream, future
live collectors) implements :class:`EventSource` and yields *raw* event dicts.
Raw events are converted into the common :class:`~fapt_guard.schemas.Evidence`
schema by :mod:`fapt_guard.preprocessing.normalizer`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from typing import Any

RawEvent = dict[str, Any]


class EventSource(ABC):
    """A source of raw security / forensic events."""

    name: str = "source"

    @abstractmethod
    def events(self) -> Iterator[RawEvent]:
        """Yield raw events in arrival order."""

    def batch(self) -> list[RawEvent]:
        return list(self.events())


class ListSource(EventSource):
    """In-memory source (tests, API ingestion, benchmark scenarios)."""

    name = "list"

    def __init__(self, events: Iterable[RawEvent]):
        self._events = list(events)

    def events(self) -> Iterator[RawEvent]:
        yield from self._events


class EvidenceAcquisitionProvider(ABC):
    """Actively acquires *additional* evidence on request (used by AF-VoI).

    Implementations must be non-invasive by default. The simulation provider
    releases latent fixture evidence; a future provider could query an EDR or
    Velociraptor for a specific artifact.
    """

    name: str = "acquisition"

    @abstractmethod
    def acquire(self, incident_id: str, artifact_class: str, host: str | None) -> list[RawEvent]:
        """Return raw events for the requested artifact class (may be empty)."""


class SimulatedAcquisitionProvider(EvidenceAcquisitionProvider):
    """Releases latent evidence held back by a fixture/scenario."""

    name = "simulated_acquisition"

    def __init__(self, latent_events: Iterable[RawEvent] = ()):
        self.latent = list(latent_events)
        self.log: list[dict] = []

    def acquire(self, incident_id: str, artifact_class: str, host: str | None) -> list[RawEvent]:
        from fapt_guard.acquisition.adapters import adapt  # local import avoids a cycle

        def matches(e: RawEvent) -> bool:
            fields = adapt(e)
            return fields.get("artifact_class") == artifact_class and (
                host is None or fields.get("host") in (None, host)
            )

        released = [e for e in self.latent if matches(e)]
        self.latent = [e for e in self.latent if e not in released]
        self.log.append({"incident_id": incident_id, "artifact_class": artifact_class,
                         "host": host, "released": len(released)})
        out = []
        for e in released:
            e = dict(e)
            e.pop("latent", None)
            out.append(e)
        return out
