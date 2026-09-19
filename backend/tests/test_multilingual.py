"""
Automated multilingual-equivalence tests (brief sections 13-14).

Real machine translation (deep-translator -> Google Translate) needs live
internet access, which may not be available in CI/sandboxed environments.
So these tests exercise the pipeline the way it actually behaves offline:
via the fallback normalization path (language.fallback_normalize), which is
the same code path main.py falls back to when translate_to_english() fails.
This keeps the tests deterministic while still proving the real bug is
fixed: a Telugu-script query must retrieve the same authoritative evidence
as its English equivalent, and unsupported queries must still abstain.

If real translation is available (network + deep-translator working), the
`test_live_translation_path` test additionally exercises the real
translate_to_english() call; it is skipped (not failed) if that call can't
reach the network, since this prototype must fail safe rather than fail the
build when offline.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import classifier, jurisdiction, retrieval, confidence, language, query_expansion, translate  # noqa: E402

EN_QUERY = "Can I patent a classical Ayurvedic formulation that is already described in a traditional Ayurvedic text?"
TE_QUERY = (
    "సాంప్రదాయ ఆయుర్వేద గ్రంథంలో ఇప్పటికే వివరించబడిన ఒక శాస్త్రీయ ఆయుర్వేద "
    "ఫార్ములేషన్‌కు నేను పేటెంట్ పొందగలనా?"
)
HI_QUERY = (
    "पारंपरिक आयुर्वेदिक ग्रंथ में पहले से वर्णित शास्त्रीय आयुर्वेदिक "
    "फॉर्मूलेशन के लिए क्या मैं पेटेंट प्राप्त कर सकता हूं?"
)
TA_QUERY = "இந்த ஆயுர்வேத தயாரிப்புக்கு காப்புரிமை பெற முடியுமா?"
ML_QUERY = "ഈ ആയുർവേദ ഉൽപ്പന്നത്തിന് പേറ്റന്റ് ലഭിക്കുമോ?"
SA_QUERY = "अस्य आयुर्वेदिक-उत्पादस्य पेटेण्ट् प्राप्तुं शक्यते किम्?"

# NOTE: a trademark-fee question used to be the "unsupported" example here.
# After the corpus expansion (brief's RAG-upgrade task) added a real Trade
# Marks Act, 1999 entry, that question started retrieving genuine (if
# general) trademark law and correctly stopped abstaining — it just no
# longer contains a specific fee figure, which the template answer never
# invents anyway. A completely unrelated, non-legal, non-Ayurveda topic is
# a more robust "zero evidence" example against a growing corpus: even a
# fairly generic off-topic phrasing (e.g. an unrelated everyday question
# using common words like "work" or "schedule") can pick up a stray
# single-word TF-IDF overlap with some corpus summary purely by chance, so
# the test query should share essentially no vocabulary with any legal
# domain in the corpus at all.
UNSUPPORTED_QUERY = "What is the boiling point of tungsten?"


def _run_pipeline(retrieval_query: str, jurisdiction_name: str = "India"):
    """Mirrors the main.py /api/analyze pipeline for a given (English)
    retrieval query, without going through FastAPI/HTTP."""
    classification = classifier.classify(retrieval_query)
    areas = jurisdiction.route_areas(retrieval_query, classification.category)
    variants = query_expansion.expand_query(retrieval_query)
    retrieved = retrieval.retrieve(variants, jurisdiction_name, areas, top_k=5)
    conf_score, conf_label, _ = confidence.score(retrieved, classification.confidence)
    abstained = confidence.should_abstain(conf_score, retrieved)
    return classification, areas, retrieved, conf_score, abstained


def test_language_detection():
    assert language.detect_language(EN_QUERY) == "en"
    assert language.detect_language(TE_QUERY) == "te"
    assert language.detect_language(HI_QUERY) == "hi"
    assert language.detect_language(TA_QUERY) == "ta"
    assert language.detect_language(ML_QUERY) == "ml"
    assert language.detect_language(SA_QUERY) == "sa"


def test_sample_queries_language_detection():
    """Explicitly tests the 6 sample queries specified in requirements."""
    assert language.detect_language("Can this Ayurvedic formulation be patented?") == "en"
    assert language.detect_language("ఈ ఆయుర్వేద ఉత్పత్తికి పేటెంట్ పొందవచ్చా?") == "te"
    assert language.detect_language("क्या इस आयुर्वेदिक उत्पाद का पेटेंट प्राप्त किया जा सकता है?") == "hi"
    assert language.detect_language("இந்த ஆயுர்வேத தயாரிப்புக்கு காப்புரிமை பெற முடியுமா?") == "ta"
    assert language.detect_language("ഈ ആയുർവേദ ഉൽപ്പന്നത്തിന് പേറ്റന്റ് ലഭിക്കുമോ?") == "ml"
    assert language.detect_language("अस्य आयुर्वेदिक-उत्पादस्य पेटेण्ट् प्राप्तुं शक्यते किम्?") == "sa"


def test_english_query_retrieves_evidence_and_does_not_abstain():
    classification, areas, retrieved, conf_score, abstained = _run_pipeline(EN_QUERY)
    assert classification.category == "Classical / Generic Medicine"
    assert "Patents" in areas
    assert len(retrieved) > 0
    assert not abstained


def test_telugu_query_via_fallback_normalization_retrieves_same_evidence():
    # Simulates the offline fallback path main.py uses when live translation
    # is unavailable — this is the exact bug scenario from the brief.
    normalized = language.fallback_normalize(TE_QUERY)
    assert normalized.strip(), "fallback normalization must not return empty text"

    classification_en, areas_en, retrieved_en, _, abstained_en = _run_pipeline(EN_QUERY)
    classification_te, areas_te, retrieved_te, _, abstained_te = _run_pipeline(normalized)

    assert not abstained_te, "Telugu-equivalent query must not abstain when English does not"
    assert classification_te.category == classification_en.category
    assert set(areas_te) & set(areas_en), "expected overlapping applicable areas"

    ids_en = {s["id"] for s in retrieved_en}
    ids_te = {s["id"] for s in retrieved_te}
    overlap = ids_en & ids_te
    assert len(overlap) >= 1, f"expected overlapping sources, got EN={ids_en} TE={ids_te}"


def test_hindi_query_via_fallback_normalization_retrieves_same_evidence():
    normalized = language.fallback_normalize(HI_QUERY)
    assert normalized.strip(), "fallback normalization must not return empty text"

    classification_en, areas_en, retrieved_en, _, abstained_en = _run_pipeline(EN_QUERY)
    classification_hi, areas_hi, retrieved_hi, _, abstained_hi = _run_pipeline(normalized)

    assert not abstained_en
    assert not abstained_hi, "Hindi-equivalent query must not abstain when English does not"
    assert classification_hi.category == classification_en.category
    assert set(areas_hi) & set(areas_en), "expected overlapping applicable areas"

    ids_en = {s["id"] for s in retrieved_en}
    ids_hi = {s["id"] for s in retrieved_hi}
    overlap = ids_en & ids_hi
    assert len(overlap) >= 1, f"expected overlapping sources, got EN={ids_en} HI={ids_hi}"


def test_tamil_query_via_fallback_normalization_retrieves_evidence():
    normalized = language.fallback_normalize(TA_QUERY)
    assert normalized.strip()
    classification, areas, retrieved, _, abstained = _run_pipeline(normalized)
    assert not abstained
    assert len(retrieved) > 0


def test_malayalam_query_via_fallback_normalization_retrieves_evidence():
    normalized = language.fallback_normalize(ML_QUERY)
    assert normalized.strip()
    classification, areas, retrieved, _, abstained = _run_pipeline(normalized)
    assert not abstained
    assert len(retrieved) > 0


def test_sanskrit_query_via_fallback_normalization_retrieves_evidence():
    normalized = language.fallback_normalize(SA_QUERY)
    assert normalized.strip()
    classification, areas, retrieved, _, abstained = _run_pipeline(normalized)
    assert not abstained
    assert len(retrieved) > 0


def test_unsupported_query_still_abstains():
    """Proves retrieval was improved without disabling safe abstention."""
    _, _, retrieved, _, abstained = _run_pipeline(UNSUPPORTED_QUERY)
    assert abstained


def test_raw_telugu_text_without_normalization_would_fail_lexical_match():
    """
    Documents the original bug precisely: retrieval on the RAW Telugu string
    (no normalization at all) must find nothing, because the TF-IDF
    tokenizer only extracts a-zA-Z tokens. This is what main.py now avoids
    by always normalizing before calling retrieve().
    """
    areas = jurisdiction._CATEGORY_DEFAULT_AREAS["Classical / Generic Medicine"]
    retrieved_raw = retrieval.retrieve(TE_QUERY, "India", areas, top_k=5)
    assert retrieved_raw == []


def test_live_translation_path():
    """Best-effort check of the real translator; skipped if offline."""
    translated, ok = translate.translate_to_english(TE_QUERY, "te")
    if not ok:
        import pytest
        pytest.skip("live translation service unavailable in this environment")
    assert translated.strip()
    classification, areas, retrieved, _, abstained = _run_pipeline(translated)
    assert not abstained
    assert classification.category == "Classical / Generic Medicine"

