import hashlib
from datetime import datetime

from app.schemas.evidence import Evidence


# ---------------------------------------------------------
# INTEGRITY HASH GENERATION
# ---------------------------------------------------------

def generate_integrity_hash(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------
# SIMULATED DIGITAL EVIDENCE
# ---------------------------------------------------------

def get_simulated_evidence() -> list[Evidence]:
    evidence_records = [
        Evidence(
            evidence_id="EV-00001",
            incident_id="INC-00001",
            timestamp=datetime(
                2026,
                9,
                25,
                10,
                2,
                0,
            ),
            source="authentication",
            host="WIN-CLIENT-07",
            user="kaushik",
            subject_type="user",
            subject="kaushik",
            action="LOGIN",
            object_type="host",
            object="WIN-CLIENT-07",
            evidence_type="user_login",
            attack_technique_id=None,
            attack_technique_name=None,
            confidence=0.99,
            integrity_hash=generate_integrity_hash(
                "EV-00001|kaushik|LOGIN|WIN-CLIENT-07"
            ),
            volatility=0.20,
            simulated=True,
        ),

        Evidence(
            evidence_id="EV-00002",
            incident_id="INC-00001",
            timestamp=datetime(
                2026,
                9,
                25,
                10,
                3,
                0,
            ),
            source="process",
            host="WIN-CLIENT-07",
            user="kaushik",
            subject_type="process",
            subject="OUTLOOK.EXE",
            action="OPEN",
            object_type="file",
            object="invoice.docm",
            evidence_type="attachment_open",
            attack_technique_id=None,
            attack_technique_name=None,
            confidence=0.95,
            integrity_hash=generate_integrity_hash(
                "EV-00002|OUTLOOK.EXE|OPEN|invoice.docm"
            ),
            volatility=0.30,
            simulated=True,
        ),

        Evidence(
            evidence_id="EV-00003",
            incident_id="INC-00001",
            timestamp=datetime(
                2026,
                9,
                25,
                10,
                3,
                15,
            ),
            source="process",
            host="WIN-CLIENT-07",
            user="kaushik",
            subject_type="process",
            subject="OUTLOOK.EXE",
            action="SPAWN",
            object_type="process",
            object="invoice.exe",
            evidence_type="process_creation",
            attack_technique_id=None,
            attack_technique_name=None,
            confidence=0.94,
            integrity_hash=generate_integrity_hash(
                "EV-00003|OUTLOOK.EXE|SPAWN|invoice.exe"
            ),
            volatility=0.55,
            simulated=True,
        ),

        Evidence(
            evidence_id="EV-00004",
            incident_id="INC-00001",
            timestamp=datetime(
                2026,
                9,
                25,
                10,
                4,
                0,
            ),
            source="sysmon",
            host="WIN-CLIENT-07",
            user="kaushik",
            subject_type="process",
            subject="invoice.exe",
            action="SPAWN",
            object_type="process",
            object="powershell.exe",
            evidence_type="process_creation",
            attack_technique_id="T1059.001",
            attack_technique_name="PowerShell",
            confidence=0.97,
            integrity_hash=generate_integrity_hash(
                "EV-00004|invoice.exe|SPAWN|powershell.exe"
            ),
            volatility=0.70,
            simulated=True,
        ),

        Evidence(
            evidence_id="EV-00005",
            incident_id="INC-00001",
            timestamp=datetime(
                2026,
                9,
                25,
                10,
                4,
                20,
            ),
            source="network",
            host="WIN-CLIENT-07",
            user="kaushik",
            subject_type="process",
            subject="powershell.exe",
            action="CONNECT",
            object_type="ip",
            object="203.0.113.50",
            evidence_type="network_connection",
            attack_technique_id=None,
            attack_technique_name=None,
            confidence=0.91,
            integrity_hash=generate_integrity_hash(
                "EV-00005|powershell.exe|CONNECT|203.0.113.50"
            ),
            volatility=0.88,
            simulated=True,
        ),

        Evidence(
            evidence_id="EV-00006",
            incident_id="INC-00001",
            timestamp=datetime(
                2026,
                9,
                25,
                10,
                5,
                2,
            ),
            source="sysmon",
            host="WIN-CLIENT-07",
            user="kaushik",
            subject_type="process",
            subject="powershell.exe",
            action="ACCESS",
            object_type="process",
            object="lsass.exe",
            evidence_type="process_access",
            attack_technique_id="T1003.001",
            attack_technique_name="LSASS Memory",
            confidence=0.96,
            integrity_hash=generate_integrity_hash(
                "EV-00006|powershell.exe|ACCESS|lsass.exe"
            ),
            volatility=0.92,
            simulated=True,
        ),
    ]

    return evidence_records


# ---------------------------------------------------------
# GET EVIDENCE FOR A SPECIFIC INCIDENT
# ---------------------------------------------------------

def get_evidence_for_incident(
    incident_id: str,
) -> list[Evidence]:
    return [
        evidence
        for evidence in get_simulated_evidence()
        if evidence.incident_id == incident_id
    ]


# ---------------------------------------------------------
# GET ONE EVIDENCE RECORD BY ID
# ---------------------------------------------------------

def get_evidence_by_id(
    evidence_id: str,
) -> Evidence | None:
    for evidence in get_simulated_evidence():
        if evidence.evidence_id == evidence_id:
            return evidence

    return None


# ---------------------------------------------------------
# VERIFY DIGITAL EVIDENCE INTEGRITY
# ---------------------------------------------------------

def verify_evidence_integrity(
    evidence_id: str,
) -> bool | None:
    evidence = get_evidence_by_id(
        evidence_id
    )

    if evidence is None:
        return None

    integrity_material = (
        f"{evidence.evidence_id}|"
        f"{evidence.subject}|"
        f"{evidence.action}|"
        f"{evidence.object}"
    )

    calculated_hash = generate_integrity_hash(
        integrity_material
    )

    return (
        calculated_hash
        == evidence.integrity_hash
    )