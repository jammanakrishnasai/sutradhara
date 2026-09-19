"""
Paid Source Connector & Consent Lifecycle Manager.

Manages integration with external paid/premium databases (AYUSH Premium, WIPO TK Registry,
Commercial Patent DB) and enforces strict FAIL-CLOSED access control upon consent revocation.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

# In-memory connector state registry
_CONNECTORS: Dict[str, Dict[str, Any]] = {
    "AYUSH-PREMIUM": {
        "id": "AYUSH-PREMIUM",
        "name": "AYUSH Premium Manuscript & Clinical Corpus",
        "provider": "Ministry of AYUSH / AIIA",
        "tier": "Paid Premium",
        "status": "ACTIVE",
        "consent_granted": True,
        "consent_timestamp": "2026-09-01T00:00:00Z",
        "scope": "Full Text Manuscripts, Classical Formulations, Prior Art Registers",
    },
    "WIPO-TK-REGISTRY": {
        "id": "WIPO-TK-REGISTRY",
        "name": "WIPO Global Traditional Knowledge Portal",
        "provider": "WIPO International",
        "tier": "International Enterprise",
        "status": "ACTIVE",
        "consent_granted": True,
        "consent_timestamp": "2026-09-05T00:00:00Z",
        "scope": "International TK Filings, Benefit Sharing Registers",
    },
    "GLOBAL-PATENT-DB": {
        "id": "GLOBAL-PATENT-DB",
        "name": "Commercial Global Patent Claims Database",
        "provider": "LexisNexis / Clarivate IP",
        "tier": "Commercial Paid",
        "status": "ACTIVE",
        "consent_granted": True,
        "consent_timestamp": "2026-09-10T00:00:00Z",
        "scope": "Full-text Global Patent Claims & Non-Patent Literature",
    },
}


def list_connectors() -> List[Dict[str, Any]]:
    """Returns status and consent details for all paid source connectors."""
    return list(_CONNECTORS.values())


def get_connector(source_id: str) -> Optional[Dict[str, Any]]:
    """Returns connector details by ID."""
    return _CONNECTORS.get(source_id)


def grant_consent(source_id: str, token: str = "demo_token_123", email: Optional[str] = None) -> Dict[str, Any]:
    """Grants/links consent for a paid source connector."""
    if source_id not in _CONNECTORS:
        raise HTTPException(status_code=404, detail=f"Paid connector '{source_id}' not found.")

    conn = _CONNECTORS[source_id]
    conn["status"] = "ACTIVE"
    conn["consent_granted"] = True
    conn["consent_timestamp"] = datetime.now(timezone.utc).isoformat()
    conn["user_email"] = email or "user@ayush.gov.in"
    conn["token_hash"] = f"tok_{hash(token)}"
    return conn


def revoke_consent(source_id: str) -> Dict[str, Any]:
    """Revokes consent for a paid source connector. Invalidates access immediately."""
    if source_id not in _CONNECTORS:
        raise HTTPException(status_code=404, detail=f"Paid connector '{source_id}' not found.")

    conn = _CONNECTORS[source_id]
    conn["status"] = "REVOKED"
    conn["consent_granted"] = False
    conn["revoked_timestamp"] = datetime.now(timezone.utc).isoformat()
    return conn


def check_access_or_fail_closed(source_id: str) -> Dict[str, Any]:
    """
    Enforces FAIL-CLOSED access control for a paid data source.
    Raises HTTP 403 Forbidden if consent has been revoked or is inactive.
    """
    conn = _CONNECTORS.get(source_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Paid connector '{source_id}' not found.")

    if not conn.get("consent_granted") or conn.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail=f"FAIL-CLOSED: Consent has been REVOKED for paid source connector '{source_id}'. Access denied.",
        )

    return {
        "status": "AUTHORIZED",
        "source_id": source_id,
        "name": conn["name"],
        "scope": conn["scope"],
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sample_records": [
            {"record_id": f"{source_id}-REC-01", "title": f"{conn['name']} High-Precision Entry 1"},
            {"record_id": f"{source_id}-REC-02", "title": f"{conn['name']} High-Precision Entry 2"},
        ],
    }
