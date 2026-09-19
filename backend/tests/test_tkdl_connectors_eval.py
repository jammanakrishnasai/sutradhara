"""
Automated pytest suite for TKDL Resemblance, Regulatory Checklist,
Paid Source Connectors & Consent Lifecycle (Fail-Closed), PDF Export, and Benchmark.
"""
import pytest
from fastapi import HTTPException
from app.tkdl import calculate_resemblance_score
from app.checklist import build_regulatory_checklist
from app import connectors
from app.pdf_generator import generate_analysis_pdf
from app.eval_benchmark import run_live_benchmark
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_tkdl_resemblance_scoring_dynamic():
    # Test case 1: Classical formulation query
    query = "Can I patent a classical Ayurvedic formulation?"
    res = calculate_resemblance_score(query, "Classical / Generic Medicine", [{"domain": "Traditional Knowledge", "section": "Section 3(p)"}])
    assert res["score"] > 50.0
    assert "classical" in res["matched_terms"]
    assert res["risk_band"] in ["CRITICAL_PRIOR_ART", "HIGH_RESEMBLANCE"]

    # Test case 2: Novel formulation without classical terms
    query_novel = "I created a brand new synthetic chemical molecule X200."
    res_novel = calculate_resemblance_score(query_novel, "New / Non-Classical Drug", [])
    assert res_novel["score"] < 40.0
    assert res_novel["risk_band"] in ["MODERATE_RESEMBLANCE", "LOW_RESEMBLANCE"]


def test_regulatory_checklist_generation():
    chk = build_regulatory_checklist("I want to market a herbal face cream", "Cosmetic", "India", [])
    assert chk["total_items"] > 0
    assert "items" in chk
    assert any("Cosmetics" in item["title"] for item in chk["items"])

    chk_nutra = build_regulatory_checklist("Ashwagandha health food supplement", "Ayurveda-Aahar / Nutraceutical", "India", [])
    assert any("FSSAI" in item["authority"] or "FSSAI" in item["title"] for item in chk_nutra["items"])


def test_paid_source_connector_consent_and_fail_closed():
    source_id = "AYUSH-PREMIUM"

    # Grant consent
    granted = connectors.grant_consent(source_id)
    assert granted["status"] == "ACTIVE"
    assert granted["consent_granted"] is True

    # Check access succeeds
    access_ok = connectors.check_access_or_fail_closed(source_id)
    assert access_ok["status"] == "AUTHORIZED"

    # Revoke consent
    revoked = connectors.revoke_consent(source_id)
    assert revoked["status"] == "REVOKED"
    assert revoked["consent_granted"] is False

    # Check access fails closed with HTTP 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        connectors.check_access_or_fail_closed(source_id)
    assert exc_info.value.status_code == 403
    assert "FAIL-CLOSED" in exc_info.value.detail

    # Restore consent after test
    connectors.grant_consent(source_id)


def test_connector_api_endpoints():
    # GET /api/connectors
    res = client.get("/api/connectors")
    assert res.status_code == 200
    connectors_list = res.json()
    assert len(connectors_list) >= 3

    # POST /api/connectors/revoke
    rev = client.post("/api/connectors/revoke", json={"source_id": "WIPO-TK-REGISTRY"})
    assert rev.status_code == 200

    # GET /api/connectors/data/WIPO-TK-REGISTRY should return 403
    data_res = client.get("/api/connectors/data/WIPO-TK-REGISTRY")
    assert data_res.status_code == 403

    # Restore consent
    client.post("/api/connectors/consent", json={"source_id": "WIPO-TK-REGISTRY"})
    data_res_ok = client.get("/api/connectors/data/WIPO-TK-REGISTRY")
    assert data_res_ok.status_code == 200


def test_pdf_export_generation():
    sample_analysis = {
        "query": "Can I patent a classical Ayurvedic formulation?",
        "jurisdiction": "India",
        "classification": {"category": "Classical / Generic Medicine", "confidence": 0.95},
        "confidence": 0.92,
        "answer": "Under Indian Patent Law Section 3(p), traditional knowledge formulations are non-patentable.",
        "tkdl_resemblance": {"score": 85.0, "risk_label": "High Resemblance", "matched_terms": ["classical", "ayurvedic"]},
        "regulatory_checklist": {
            "progress_percentage": 60.0,
            "items": [
                {"title": "TKDL Prior-Art Search", "authority": "Indian Patent Office", "status": "COMPLETED"},
                {"title": "AYUSH Manufacturing License", "authority": "State AYUSH Authority", "status": "ACTION_REQUIRED"},
            ]
        }
    }
    pdf_bytes = generate_analysis_pdf(sample_analysis)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")


def test_live_benchmark_execution():
    metrics = run_live_benchmark()
    assert metrics["total_items"] == 20
    assert "accuracy_pct" in metrics
    assert "citation_precision_pct" in metrics
    assert "jurisdiction_isolation_pct" in metrics
    assert metrics["total_items"] == len(metrics["item_results"])
