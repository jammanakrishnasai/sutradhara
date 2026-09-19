"""
Answer generation.

For the MVP this is template-grounded rather than a free-form LLM generation:
the answer text is assembled directly from the retrieved sources' `summary`
fields plus the classification/jurisdiction context, so every sentence in the
answer traces to a specific source in `sources`. This guarantees the "no
hallucinated law" restriction holds even before an LLM paraphrasing layer
(Groq, per the architecture doc) is wired in on top in a later phase — the
LLM call, when added, should be constrained to paraphrase these grounded
sentences, never to introduce new legal claims.
"""
from typing import List, Dict, Any, Optional
from .schemas import AbsChecklist


def build_answer(query: str, category: str, jurisdiction: str, sources: List[Dict[str, Any]]) -> str:
    if not sources:
        return ""

    lines = [
        f"For a product classified as '{category}' under {jurisdiction} jurisdiction, "
        f"the following authoritative considerations apply based on the retrieved sources:"
    ]
    for i, s in enumerate(sources, 1):
        lines.append(f"({i}) {s['summary']} [Source: {s['title']}, {s['section']}]")

    lines.append(
        "This is an informational synthesis of the cited provisions only — it does not "
        "constitute legal advice and does not guarantee any registration or approval outcome."
    )
    return "\n\n".join(lines)


def build_abs_checklist(query: str, sources: List[Dict[str, Any]]) -> Optional[AbsChecklist]:
    """
    NOTE: `query` here should be the English retrieval query (post
    translation/normalization), not necessarily the user's original-language
    text — the bio_terms keyword check below only understands English.
    """
    q = query.lower()
    bio_terms = ["herb", "plant", "biological resource", "genetic resource", "extract", "root", "leaf", "species"]
    involved = any(t in q for t in bio_terms)
    if not involved:
        return None

    abs_sources = [s for s in sources if s["domain"] == "Access-and-Benefit-Sharing"]
    provenance_terms = ["provenance", "particular region", "specific region", "forest", "tribal", "sourced from", "origin"]
    return AbsChecklist(
        biological_resource_involved=True,
        provenance_identified=any(t in q for t in provenance_terms),
        abs_framework_identified=len(abs_sources) > 0,
        supporting_source_retrieved=len(abs_sources) > 0,
    )


def build_tk_pointer(category: str, jurisdiction: str) -> Optional[str]:
    if category != "Classical / Generic Medicine":
        return None
    if jurisdiction == "India":
        return (
            "This formulation category is classical/traditional in nature. Prior art and "
            "traditional-knowledge documentation should be checked via the Traditional "
            "Knowledge Digital Library (TKDL) reference workflow before filing. This prototype "
            "does not access the real (access-restricted) TKDL database — it only demonstrates "
            "the reference-check step in the workflow."
        )
    return (
        "Internationally, several patent offices (e.g. EPO, USPTO) consult India's Traditional "
        "Knowledge Digital Library (TKDL) as prior art under access agreements. This prototype "
        "demonstrates the reference-check step only; it does not connect to real TKDL data."
    )
