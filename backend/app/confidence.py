"""
Confidence scoring and safe-abstention.

Deliberately NOT a random number. Confidence is a weighted combination of:
  - retrieval_relevance : mean relevance_score of the retrieved sources
  - source_count_factor : more independent authoritative sources -> more confidence
  - source_authority     : statutes/treaties score higher than lower-precision entries
  - agreement            : how many distinct domains among sources agree with the routed areas
  - classification_conf  : confidence from the product classifier

Abstention threshold: if retrieval finds nothing above the relevance floor,
or the combined score falls below ABSTAIN_THRESHOLD, the system must abstain
rather than answer from the LLM's own (unverified) knowledge.
"""
from typing import List, Dict, Any, Tuple

ABSTAIN_THRESHOLD = 0.40

_AUTHORITY_WEIGHT = {
    "Statute": 1.0,
    "Statute/Rules": 1.0,
    "Regulation": 0.9,
    "Treaty": 1.0,
    "Database / Access Agreement": 0.6,
    "International body / ongoing negotiation": 0.5,
}


def score(
    sources: List[Dict[str, Any]],
    classification_confidence: float,
) -> Tuple[float, str, Dict[str, float]]:
    if not sources:
        breakdown = {
            "retrieval_relevance": 0.0,
            "source_count_factor": 0.0,
            "source_authority": 0.0,
            "classification_confidence": round(classification_confidence, 2),
        }
        return 0.0, "LOW", breakdown

    relevance_scores = [s["relevance_score"] for s in sources]
    retrieval_relevance = sum(relevance_scores) / len(relevance_scores)

    source_count_factor = min(1.0, 0.3 + 0.2 * len(sources))  # saturates at ~4 sources

    authority_scores = [_AUTHORITY_WEIGHT.get(s["source_type"], 0.6) for s in sources]
    source_authority = sum(authority_scores) / len(authority_scores)

    domains = {s["domain"] for s in sources}
    agreement = min(1.0, 0.5 + 0.15 * len(domains))

    combined = (
        0.35 * retrieval_relevance
        + 0.15 * source_count_factor
        + 0.20 * source_authority
        + 0.10 * agreement
        + 0.20 * classification_confidence
    )
    combined = round(min(combined, 0.97), 2)

    if combined >= 0.75:
        label = "HIGH"
    elif combined >= ABSTAIN_THRESHOLD:
        label = "MEDIUM"
    else:
        label = "LOW"

    breakdown = {
        "retrieval_relevance": round(retrieval_relevance, 2),
        "source_count_factor": round(source_count_factor, 2),
        "source_authority": round(source_authority, 2),
        "agreement": round(agreement, 2),
        "classification_confidence": round(classification_confidence, 2),
    }
    return combined, label, breakdown


def should_abstain(confidence: float, sources: List[Dict[str, Any]]) -> bool:
    return (not sources) or confidence < ABSTAIN_THRESHOLD
