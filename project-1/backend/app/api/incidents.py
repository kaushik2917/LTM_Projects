from fastapi import APIRouter, HTTPException

from app.schemas.incident import Incident
from app.services.incident_service import (
    get_simulated_incident,
    get_simulated_incidents,
)


router = APIRouter(
    prefix="/api/incidents",
    tags=["Incidents"],
)


@router.get("", response_model=list[Incident])
def list_incidents():
    return get_simulated_incidents()


@router.get("/{incident_id}", response_model=Incident)
def get_incident(incident_id: str):
    incident = get_simulated_incident(incident_id)

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    return incident