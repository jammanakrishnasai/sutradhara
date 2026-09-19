"""
TKDL Resemblance Scoring System.

Calculates a non-hardcoded prior-art resemblance score (0% to 100%)
based on lexical overlap, retrieved classical/TKDL corpus entries,
and product classification signals.
"""
import re
from typing import List, Dict, Any

CLASSICAL_KEYWORDS = [
    "classical", "generic", "traditional", "text", "Ayurveda", "Ayurvedic",
    "formulation", "grantha", "samhita", "charaka", "susruta", "vagbhata",
    "prior art", "tkdl", "traditional knowledge", "shastriya", "yog"
]


def calculate_resemblance_score(
    query: str,
    category: str,
    retrieved_sources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Computes a dynamic TKDL Resemblance Score and Risk Band.
    """
    query_lower = query.lower()

    # Factor 1: Query Keyword Match Ratio (0 - 40 points)
    matched_terms = [kw for kw in CLASSICAL_KEYWORDS if kw in query_lower]
    term_score = min(40.0, len(matched_terms) * 10.0)

    # Factor 2: Retrieved TK / Prior-Art Sources Ratio (0 - 40 points)
    tk_sources = []
    if retrieved_sources:
        for src in retrieved_sources:
            domain = src.get("domain", "").lower()
            title = src.get("title", "").lower()
            sec = src.get("section", "").lower()
            src_id = src.get("id", "").lower()

            if "traditional knowledge" in domain or "3(p)" in sec or "tkdl" in title or "tkdl" in src_id:
                tk_sources.append(src.get("title") or src.get("id"))

        source_score = min(40.0, len(tk_sources) * 20.0)
    else:
        source_score = 0.0

    # Factor 3: Category Prior-Art Weight (0 - 20 points)
    category_weights = {
        "Classical / Generic Medicine": 20.0,
        "Patent / Proprietary Medicine": 10.0,
        "New / Non-Classical Drug": 5.0,
        "Phytopharmaceutical": 12.0,
        "Ayurveda-Aahar / Nutraceutical": 8.0,
        "Cosmetic": 5.0,
    }
    cat_score = category_weights.get(category, 5.0)

    # Total Resemblance Score (0.0 to 100.0)
    total_score = round(min(100.0, term_score + source_score + cat_score), 1)

    # Risk Band Determination
    if total_score >= 80.0:
        risk_band = "CRITICAL_PRIOR_ART"
        risk_label = "High Resemblance / Direct Classical Prior Art"
    elif total_score >= 50.0:
        risk_band = "HIGH_RESEMBLANCE"
        risk_label = "Significant Traditional Knowledge Resemblance"
    elif total_score >= 25.0:
        risk_band = "MODERATE_RESEMBLANCE"
        risk_label = "Moderate Traditional Knowledge Overlap"
    else:
        risk_band = "LOW_RESEMBLANCE"
        risk_label = "Low Prior-Art Overlap"

    return {
        "score": total_score,
        "risk_band": risk_band,
        "risk_label": risk_label,
        "matched_terms": matched_terms,
        "matched_tk_sources": list(set(tk_sources)),
        "breakdown": {
            "query_term_weight": round(term_score, 1),
            "retrieved_tk_evidence_weight": round(source_score, 1),
            "category_prior_art_weight": round(cat_score, 1),
        },
    }
