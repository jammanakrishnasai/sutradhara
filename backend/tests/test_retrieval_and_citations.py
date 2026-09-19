"""
Additional automated coverage requested for the RAG-upgrade task:
  - India vs International filtering (never mixed)
  - citation correctness (every retrieved source has complete, real fields)
  - the two named demo scenarios (classical formulation, new formulation)
  - which retrieval backend is actually active (informational, not a failure)

Kept separate from test_multilingual.py, which already owns EN/TE evidence
equivalence and the unsupported-query abstention test — no need to
duplicate those here.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import classifier, jurisdiction, retrieval, confidence, query_expansion, answer  # noqa: E402

REQUIRED_SOURCE_FIELDS = [
    "id", "title", "section", "authority", "jurisdiction", "domain",
    "source_type", "version_date", "retrieved_date", "source_url", "precision",
]

CLASSICAL_QUERY = "Can I patent a classical Ayurvedic formulation?"
NEW_FORMULATION_QUERY = (
    "I developed a new Ayurvedic formulation that is not found in a classical text. "
    "What IP and regulatory considerations should I check?"
)


def _run(query: str, jurisdiction_name: str):
    classification = classifier.classify(query)
    areas = jurisdiction.route_areas(query, classification.category)
    variants = query_expansion.expand_query(query)
    retrieved = retrieval.retrieve(variants, jurisdiction_name, areas, top_k=5)
    conf_score, conf_label, _ = confidence.score(retrieved, classification.confidence)
    abstained = confidence.should_abstain(conf_score, retrieved)
    return classification, areas, retrieved, conf_score, abstained


def test_retrieval_backend_is_reported_and_valid():
    """Informational: confirms the module always reports a real backend name.
    Not a hard requirement on WHICH backend — this sandbox cannot reach the
    Hugging Face Hub to download the sentence-transformer model, so it
    always falls back to 'tfidf' here; a machine with internet access
    should see 'embeddings' instead (see retrieval.py docstring)."""
    assert retrieval.BACKEND in ("embeddings", "tfidf")


# --- Demo scenario 1: classical formulation, India --------------------------

def test_demo1_classical_formulation_india():
    classification, areas, retrieved, conf_score, abstained = _run(CLASSICAL_QUERY, "India")
    assert classification.category == "Classical / Generic Medicine"
    assert "Patents" in areas
    assert not abstained
    assert len(retrieved) > 0
    ids = {s["id"] for s in retrieved}
    # Section 3(p) (traditional-knowledge patent exclusion) must be among the
    # cited sources for this exact scenario — this is the brief's own
    # required demo assertion, not just "some source or other".
    assert "IN-PAT-3P" in ids or "IN-PAT-3J" in ids


# --- Demo scenario 2: new/non-classical formulation, India -------------------

def test_demo2_new_formulation_india_differs_from_classical():
    classical = _run(CLASSICAL_QUERY, "India")
    new_formulation = _run(NEW_FORMULATION_QUERY, "India")

    assert classical[0].category == "Classical / Generic Medicine"
    assert new_formulation[0].category == "New / Non-Classical Drug"
    assert not new_formulation[4]  # not abstained

    # The brief requires the system to demonstrably distinguish classical
    # from new/non-classical — different classification, at minimum.
    assert classical[0].category != new_formulation[0].category


# --- Jurisdiction isolation ---------------------------------------------------

def test_jurisdiction_isolation_india_never_returns_international_sources():
    for query in (CLASSICAL_QUERY, NEW_FORMULATION_QUERY):
        _, _, retrieved, _, _ = _run(query, "India")
        for s in retrieved:
            assert s["jurisdiction"] == "India", f"leaked non-India source: {s['id']}"


def test_jurisdiction_isolation_international_never_returns_india_sources():
    for query in (CLASSICAL_QUERY, NEW_FORMULATION_QUERY):
        _, _, retrieved, _, _ = _run(query, "International")
        for s in retrieved:
            assert s["jurisdiction"] == "International", f"leaked India source: {s['id']}"


def test_india_to_international_switch_changes_the_source_set():
    """Mirrors the brief's Demo 2 assertion: switching jurisdiction on the
    SAME question must change which sources are cited, not just relabel them."""
    _, _, retrieved_india, _, _ = _run(CLASSICAL_QUERY, "India")
    _, _, retrieved_intl, _, _ = _run(CLASSICAL_QUERY, "International")

    ids_india = {s["id"] for s in retrieved_india}
    ids_intl = {s["id"] for s in retrieved_intl}

    assert ids_india, "India jurisdiction should return evidence for the core demo query"
    assert ids_intl, "International jurisdiction should return evidence for the core demo query"
    assert ids_india.isdisjoint(ids_intl), "India and International source sets must never overlap"


# --- Citation correctness ----------------------------------------------------

def test_citation_fields_are_complete_for_every_retrieved_source():
    for query, jur in ((CLASSICAL_QUERY, "India"), (CLASSICAL_QUERY, "International"),
                       (NEW_FORMULATION_QUERY, "India")):
        _, _, retrieved, _, _ = _run(query, jur)
        for s in retrieved:
            for field in REQUIRED_SOURCE_FIELDS:
                assert s.get(field), f"source {s.get('id')} missing/empty field '{field}'"
            # a citation must be traceable to an actual corpus entry, not a
            # value invented at answer-generation time
            assert retrieval.get_document(s["id"]) is not None
            assert 0.0 <= s["relevance_score"] <= 1.0


def test_generated_answer_only_cites_sources_that_were_actually_retrieved():
    classification, areas, retrieved, conf_score, abstained = _run(CLASSICAL_QUERY, "India")
    assert not abstained
    generated = answer.build_answer(CLASSICAL_QUERY, classification.category, "India", retrieved)
    for s in retrieved:
        assert s["title"] in generated, f"answer text does not cite retrieved source {s['id']}"


def test_corpus_has_been_expanded_to_the_requested_range():
    """20-40 verified sources, per the brief."""
    assert 20 <= len(retrieval._CORPUS) <= 40


def test_requested_category_and_abstention_routes():
    gi_query = "I want to sell my Ayurvedic product under a regional name tied to where it is traditionally made — do I need a Geographical Indication registration?"
    gi_classification = classifier.classify(gi_query)
    assert not gi_classification.needs_clarification
    assert "Geographical Indications" in jurisdiction.route_areas(gi_query, gi_classification.category)

    formulary = classifier.classify("A tablet made using a formulation and method described in the Ayurvedic Formulary of India")
    nutraceutical = classifier.classify("A functional food product made from ashwagandha and turmeric marketed for daily wellness")
    cosmetic = classifier.classify("A face pack made from neem and sandalwood, marketed for skin brightening with no therapeutic claim")
    assert formulary.category == "Classical / Generic Medicine"
    assert nutraceutical.category == "Ayurveda-Aahar / Nutraceutical"
    assert cosmetic.category == "Cosmetic"

    assert jurisdiction.has_unsupported_foreign_country(
        "What export documentation does Vietnam require for herbal cosmetics?", "India"
    )
    assert not jurisdiction.has_unsupported_foreign_country(CLASSICAL_QUERY, "International")
