from datetime import datetime

from app.schemas.incident import Incident
from app.services.evidence_service import (
    get_evidence_for_incident,
)


def get_simulated_incidents() -> list[Incident]:
    incident_id = "INC-00001"

    evidence_count = len(
        get_evidence_for_incident(incident_id)
    )

    return [
        Incident(
            incident_id=incident_id,
            title="Suspicious PowerShell and LSASS Access",
            severity="critical",
            status="active",
            detected_at=datetime(
                2026,
                9,
                25,
                10,
                2,
                0,
            ),
            affected_host="WIN-CLIENT-07",
            affected_user="kaushik",
            current_tactic="Credential Access",
            current_technique_id="T1003.001",
            current_technique_name="LSASS Memory",
            evidence_count=evidence_count,
            simulated=True,
        )
    ]


def get_simulated_incident(
    incident_id: str,
) -> Incident | None:
    incidents = get_simulated_incidents()

    for incident in incidents:
        if incident.incident_id == incident_id:
            return incident

    return None