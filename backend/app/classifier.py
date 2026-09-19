"""
Product classification logic.

Deliberately rule-based (keyword + pattern matching) rather than an LLM call:
classification is a factual routing decision that downstream retrieval and
jurisdiction logic depend on, so it needs to be deterministic, auditable, and
explainable to a judge. An LLM can be layered on top later (Phase-9+) without
changing this interface.
"""
from typing import Optional
import re
from .schemas import ClassificationResult

CATEGORIES = [
    "Classical / Generic Medicine",
    "Patent / Proprietary Medicine",
    "New / Non-Classical Drug",
    "Phytopharmaceutical",
    "Ayurveda-Aahar / Nutraceutical",
    "Cosmetic",
]

_KEYWORDS = {
    "Classical / Generic Medicine": [
        "classical", "traditional formulation", "authoritative text", "ancient text", "formulary",
        "charaka", "sushruta", "ashtanga", "shastra", "classical text", "generic",
        "traditional ayurvedic", "known formulation", "prior art", "triphala",
        "medicinal plant", "forest region", "provenance", "tribal community", "turmeric", "neem",
        "geographical indication", "regional name", "traditionally made",
    ],
    "Patent / Proprietary Medicine": [
        "proprietary", "patent medicine", "brand", "my own formula", "own formulation",
        "proprietary ayurvedic",
    ],
    "New / Non-Classical Drug": [
        "new formulation", "not found in classical", "novel formulation", "not in any classical text",
        "developed a new", "innovation", "new drug", "not documented", "not a classical",
    ],
    "Phytopharmaceutical": [
        "phytopharmaceutical", "standardized extract", "purified extract", "botanical drug",
        "isolated compound", "phyto",
    ],
    "Ayurveda-Aahar / Nutraceutical": [
        "nutraceutical", "health supplement", "aahar", "food supplement", "functional food",
        "dietary supplement",
    ],
    "Cosmetic": [
        "cosmetic", "skincare", "cream for skin", "soap", "beauty product", "hair oil",
        "face pack",
    ],
}


_NEW_FORMULATION_PATTERNS = [
    # Naive substring keyword-counting (below) has no negation awareness:
    # "...not found in a classical text" contains both "classical" and
    # "classical text" as bare substrings, so it was outscoring the correct
    # "New / Non-Classical Drug" category, which only matched "developed a
    # new" once — exactly the brief's own Demo Scenario 2 query. These
    # patterns catch the negated phrasing explicitly and win first, before
    # the keyword-count competition ever runs.
    re.compile(r"not\s+(found|documented|described|present)\s+in\s+(any\s+|a\s+)?classical"),
    re.compile(r"not\s+in\s+any\s+classical"),
    re.compile(r"non[\s-]?classical"),
    re.compile(r"not\s+a\s+classical"),
]


def classify(query: str, confirmed_category: Optional[str] = None) -> ClassificationResult:
    if confirmed_category and confirmed_category in CATEGORIES:
        return ClassificationResult(
            category=confirmed_category,
            confidence=0.99,
            reason="Category confirmed directly by the user.",
            needs_clarification=False,
        )

    q = query.lower()

    if any(p.search(q) for p in _NEW_FORMULATION_PATTERNS):
        return ClassificationResult(
            category="New / Non-Classical Drug",
            confidence=0.85,
            reason=(
                "The query explicitly states the formulation is NOT found in any "
                "classical text, which is treated as a new/non-classical drug for "
                "regulatory purposes."
            ),
            needs_clarification=False,
        )

    if any(term in q for term in ("functional food", "daily wellness", "food product")):
        return ClassificationResult(
            category="Ayurveda-Aahar / Nutraceutical",
            confidence=0.85,
            reason="The query describes a food or daily-wellness product rather than a medicinal formulation.",
            needs_clarification=False,
        )

    if any(term in q for term in ("face pack", "skin brightening", "no therapeutic claim")):
        return ClassificationResult(
            category="Cosmetic",
            confidence=0.85,
            reason="The query describes a topical product for cosmetic use without a therapeutic claim.",
            needs_clarification=False,
        )

    scores = {cat: 0 for cat in CATEGORIES}
    for cat, kws in _KEYWORDS.items():
        for kw in kws:
            if kw in q:
                scores[cat] += 1

    best_cat = max(scores, key=scores.get)
    best_score = scores[best_cat]
    total_hits = sum(scores.values())

    if best_score == 0:
        # No strong signal — ask the minimum necessary clarification question
        # rather than guessing.
        return ClassificationResult(
            category="Classical / Generic Medicine",
            confidence=0.35,
            reason="No explicit signal found in the query for a specific category.",
            needs_clarification=True,
            clarification_question=(
                "Is this formulation described in a classical/authoritative Ayurvedic "
                "text, or is it a new formulation you have developed that is not found "
                "in a classical text?"
            ),
        )

    confidence = min(0.95, 0.5 + 0.15 * best_score - 0.05 * (total_hits - best_score))
    confidence = max(0.4, confidence)

    reason_map = {
        "Classical / Generic Medicine": (
            "The query indicates the formulation is associated with an authoritative "
            "classical source or traditional knowledge."
        ),
        "Patent / Proprietary Medicine": (
            "The query indicates a proprietary formulation intended for branded manufacture "
            "under the Patent/Proprietary Ayurvedic medicine regime."
        ),
        "New / Non-Classical Drug": (
            "The query indicates a formulation that is not documented in any classical text, "
            "which is treated as a new/non-classical drug for regulatory purposes."
        ),
        "Phytopharmaceutical": (
            "The query describes a standardized or purified botanical extract, which falls "
            "under the phytopharmaceutical category."
        ),
        "Ayurveda-Aahar / Nutraceutical": (
            "The query describes a food/health-supplement style product rather than a drug."
        ),
        "Cosmetic": (
            "The query describes a topical/cosmetic-use product rather than an internal medicine."
        ),
    }

    return ClassificationResult(
        category=best_cat,
        confidence=round(confidence, 2),
        reason=reason_map[best_cat],
        needs_clarification=False,
    )
