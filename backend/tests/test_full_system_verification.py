"""
Comprehensive E2E System Verification Suite for SUTRADHARA.

Tests every API endpoint, database table, dynamic knowledge graph,
RAG retrieval, 6-language translations, PDF export stream, fail-closed consent access,
and evaluation metrics logging.
"""
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import db

client = TestClient(app)


def test_01_health_and_corpus_retrieval():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["corpus_documents"] > 0

    # Retrieve specific document
    doc_res = client.get("/api/sources/IN-PAT-3P")
    assert doc_res.status_code == 200
    doc = doc_res.json()
    assert doc["id"] == "IN-PAT-3P"
    assert "Patents Act" in doc["title"]


def test_02_database_initialization_and_logging():
    db.init_db()

    # Feedback logging
    fb_res = client.post("/api/feedback", json={
        "query": "Test feedback query",
        "answer_id": "ANS-001",
        "rating": 5,
        "comment": "Excellent evidence grounding"
    })
    assert fb_res.status_code == 200
    assert fb_res.json()["status"] == "recorded"

    # Escalation logging
    esc_res = client.post("/api/escalate", json={
        "query": "Escalation test query for rare herb",
        "product_category": "Phytopharmaceutical",
        "jurisdiction": "India",
        "relevant_ip_area": ["Access-and-Benefit-Sharing"],
        "retrieved_sources": ["IN-BIO-001"],
        "contact_email": "facilitator@ayush.gov.in"
    })
    assert esc_res.status_code == 200
    assert esc_res.json()["status"] == "escalated"
    assert esc_res.json()["escalation_id"] > 0

    # Eval summary retrieval
    eval_res = client.get("/api/eval")
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["total_queries"] >= 0


def test_03_multilingual_analysis_pipeline_6_languages():
    languages = [
        ("en", "Can I patent a classical Ayurvedic formulation?"),
        ("te", "సాంప్రదాయ ఆయుర్వేద ఔషధానికి పేటెంట్ పొందవచ్చా?"),
        ("hi", "क्या मैं शास्त्रीय आयुर्वेदिक योग पेटेंट करा सकता हूँ?"),
        ("ta", "மரபுவழி ஆயுர்வேத மருந்துக்கு காப்புரிமை பெற முடியுமா?"),
        ("ml", "പരമ്പരാഗത ആയുർവേദ ഔഷധത്തിന് പേറ്റന്റ് നേടാനാകുമോ?"),
        ("sa", "किं अहम् शास्त्रीय आयुर्वेद योगस्य एकस्वम् प्राप्तुम् शक्नोमि?"),
    ]

    with patch("app.translate.translate_to_english", return_value=("Can I patent a classical Ayurvedic formulation?", True)), \
         patch("app.translate.translate_text", side_effect=lambda text, target_lang="en", **kw: (f"[{target_lang}] {text}", True)):
        for lang_code, query_text in languages:
            resp = client.post("/api/analyze", json={
                "query": query_text,
                "jurisdiction": "India",
                "language": lang_code
            })
            assert resp.status_code == 200, f"Failed for language {lang_code}"
            data = resp.json()
            assert data["jurisdiction"] == "India"
            assert "classification" in data
            assert "category" in data["classification"]
            assert "confidence" in data
            assert "answer" in data
            assert data["answer_language"] == lang_code
            assert "tkdl_resemblance" in data
            assert "regulatory_checklist" in data
            assert data["tkdl_resemblance"]["score"] >= 0.0
            assert len(data["regulatory_checklist"]["items"]) > 0


def test_04_jurisdiction_isolation():
    # India query -> should include Indian Patents Act / Section 3(p)
    res_in = client.post("/api/analyze", json={
        "query": "Can I patent a classical formulation?",
        "jurisdiction": "India",
        "language": "en"
    })
    assert res_in.status_code == 200
    sources_in = [s["title"] + " " + s["section"] for s in res_in.json()["sources"]]
    assert any("Section 3(p)" in s or "Patents Act" in s for s in sources_in)

    # International query -> must NOT include Indian Patents Act Section 3(p)
    res_intl = client.post("/api/analyze", json={
        "query": "Can I patent a classical formulation?",
        "jurisdiction": "International",
        "language": "en"
    })
    assert res_intl.status_code == 200
    sources_intl = [s["title"] + " " + s["section"] for s in res_intl.json()["sources"]]
    assert not any("Patents Act, 1970" in s for s in sources_intl)


def test_05_dynamic_knowledge_graph():
    # Graph for query 1
    g1_res = client.get("/api/graph?query=Herbal+face+cream+cosmetics&jurisdiction_name=India")
    assert g1_res.status_code == 200
    g1 = g1_res.json()
    assert "nodes" in g1 and "edges" in g1
    labels1 = [n.get("label", "") for n in g1["nodes"]]

    # Graph for query 2
    g2_res = client.get("/api/graph?query=Ashwagandha+nutraceutical+food+supplement&jurisdiction_name=India")
    assert g2_res.status_code == 200
    g2 = g2_res.json()
    labels2 = [n.get("label", "") for n in g2["nodes"]]

    assert any("Cosmetic" in l or "Cosmetics" in l for l in labels1)
    assert any("Nutraceutical" in l or "Ayurveda-Aahar" in l or "Food" in l for l in labels2)


def test_06_paid_source_connectors_and_fail_closed():
    # List connectors
    list_res = client.get("/api/connectors")
    assert list_res.status_code == 200
    connectors = list_res.json()
    assert len(connectors) >= 3

    source_id = "GLOBAL-PATENT-DB"

    # Revoke consent
    rev_res = client.post("/api/connectors/revoke", json={"source_id": source_id})
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "REVOKED"

    # Access data -> MUST respond with HTTP 403 Forbidden
    fail_closed_res = client.get(f"/api/connectors/data/{source_id}")
    assert fail_closed_res.status_code == 403
    assert "FAIL-CLOSED" in fail_closed_res.json()["detail"]

    # Grant consent
    grant_res = client.post("/api/connectors/consent", json={"source_id": source_id})
    assert grant_res.status_code == 200
    assert grant_res.json()["status"] == "ACTIVE"

    # Access data -> Authorized
    access_ok = client.get(f"/api/connectors/data/{source_id}")
    assert access_ok.status_code == 200
    assert access_ok.json()["status"] == "AUTHORIZED"


def test_07_pdf_export_service():
    sample_data = {
        "query": "Can I patent a classical Ayurvedic formulation?",
        "jurisdiction": "India",
        "classification": {"category": "Classical / Generic Medicine", "confidence": 0.95},
        "confidence": 0.92,
        "answer": "Under Indian Patent Law Section 3(p), traditional knowledge formulations are non-patentable.",
        "tkdl_resemblance": {"score": 85.0, "risk_label": "High Resemblance", "matched_terms": ["classical", "ayurvedic"]},
        "regulatory_checklist": {
            "progress_percentage": 75.0,
            "items": [
                {"title": "TKDL Search", "authority": "IPO", "status": "COMPLETED"},
                {"title": "AYUSH License", "authority": "State AYUSH", "status": "ACTION_REQUIRED"},
            ]
        }
    }
    pdf_res = client.post("/api/export/pdf", json={"analysis_data": sample_data})
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 500
    assert pdf_res.content.startswith(b"%PDF")


def test_08_live_evaluation_benchmark():
    bench_res = client.post("/api/eval/benchmark")
    assert bench_res.status_code == 200
    metrics = bench_res.json()
    assert metrics["total_items"] == 20
    assert metrics["accuracy_pct"] >= 80.0
    assert metrics["citation_precision_pct"] >= 80.0
    assert metrics["jurisdiction_isolation_pct"] == 100.0
