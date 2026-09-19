"""
Lightweight domain-term query expansion for retrieval only.

Given the (already-English, already-normalized) retrieval query, generate a
small number (<=5) of additional phrasings that surface the specific legal
concepts a judge-readable IP corpus is indexed under (e.g. "Section 3(p)",
"patentability", "traditional knowledge prior art"). These variants are never
shown to the user — they only widen what retrieval.retrieve() matches against,
which then reranks by taking the max relevance across variants per document.

This is deliberately a short, auditable keyword->concept table, not an LLM
call: query expansion here is a retrieval aid, not a place to introduce new
legal claims.
"""
from typing import List

_EXPANSIONS = [
    (("ayurved",), "classical Ayurvedic formulation"),
    (("classical", "traditional", "authoritative text", "ancient text"),
     "traditional knowledge prior art"),
    (("classical", "ayurved"), "Section 3(p) patents act traditional knowledge exclusion"),
    (("patent",), "patentability India patent law"),
    (("biological resource", "genetic resource", "biodivers", "medicinal plant", "extract", "provenance", "forest", "tribal"),
     "access and benefit sharing biological resources"),
    (("geographical indication", " gi "), "geographical indication registration"),
    (("nutraceutical", "food supplement", "dietary supplement"),
     "food and nutraceutical regulation labelling"),
]


def expand_query(english_query: str, max_variants: int = 5) -> List[str]:
    """Return [original_query, *up to max_variants-1 concept variants]."""
    if not english_query or not english_query.strip():
        return [english_query]

    q = english_query.lower()
    variants = [english_query]
    for triggers, concept in _EXPANSIONS:
        if any(t in q for t in triggers) and concept not in variants:
            variants.append(concept)
        if len(variants) >= max_variants:
            break
    return variants[:max_variants]
