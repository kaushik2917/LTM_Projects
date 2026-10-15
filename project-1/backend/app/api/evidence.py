from fastapi import APIRouter, HTTPException

from app.schemas.evidence import Evidence
from app.services.evidence_service import (
    get_evidence_by_id,
    get_evidence_for_incident,
    get_simulated_evidence,
)


router = APIRouter(
    prefix="/api/evidence",
    tags=["Digital Evidence"],
)


@router.get("", response_model=list[Evidence])
def list_evidence():
    return get_simulated_evidence()


@router.get(
    "/incident/{incident_id}",
    response_model=list[Evidence],
)
def list_incident_evidence(
    incident_id: str,
):
    return get_evidence_for_incident(
        incident_id
    )


@router.get(
    "/{evidence_id}",
    response_model=Evidence,
)
def get_evidence(
    evidence_id: str,
):
    evidence = get_evidence_by_id(
        evidence_id
    )

    if evidence is None:
        raise HTTPException(
            status_code=404,
            detail="Evidence not found",
        )

    return evidence