"""Call-level termination policy. Utterance/silence events are never terminal."""
from datetime import datetime, timezone

class CallTerminationController:
    REASONS = {'manual_end', 'provider_hangup', 'provider_disconnect', 'transfer', 'max_duration', 'fatal_failure'}

    @classmethod
    def validate(cls, reason):
        if reason not in cls.REASONS:
            raise ValueError('Not a call termination event')

    @staticmethod
    def duration_reached(call, minutes):
        return minutes > 0 and (datetime.now(timezone.utc) - datetime.fromisoformat(call['created_at'])).total_seconds() >= minutes * 60
