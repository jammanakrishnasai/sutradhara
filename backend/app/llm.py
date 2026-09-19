"""
Optional LLM paraphrasing layer — Groq.

Per ARCHITECTURE.md's own invariant (see answer.py docstring): the grounded
answer is assembled directly from retrieved source text so that "no
hallucinated law" holds even without an LLM. This module adds an *optional*
layer on top of that assembled text, using Groq's chat-completions API
(OpenAI-compatible) purely to smooth the prose into a single readable
paragraph-style assessment for the judge-facing UI.

Hard constraints enforced here, not just requested in the prompt:
  1. The LLM is never given retrieval, corpus, or "what does the law say"
     latitude — it receives the ALREADY-GROUNDED text and is instructed only
     to paraphrase it for readability.
  2. Every `[Source: ...]` citation tag, and every legal identifier inside it
     (Act name, Section/Article/Rule number), must survive unchanged. This is
     verified programmatically after the call (see `_citations_preserved`) —
     we do not simply trust the model's instruction-following. If the check
     fails, or the call fails/times out/is unconfigured, the ORIGINAL
     template-assembled answer is returned untouched. The pipeline behaves
     identically whether or not GROQ_API_KEY is set.
  3. This module only ever runs on the English-language grounded answer,
     BEFORE Telugu translation (see main.py) — so the multilingual pipeline
     and citation-preservation guarantees are unaffected either way.

Network note: this calls api.groq.com directly. If the deployment
environment has no outbound access to that host, the call fails and the
pipeline silently falls back to the template answer — never a crash, never a
missing response.
"""
import os
import re
import logging
from typing import List, Tuple

logger = logging.getLogger("ip_sakti.llm")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip()
_ENABLED = os.environ.get("ENABLE_LLM_PARAPHRASE", "true").strip().lower() not in ("0", "false", "no")
_TIMEOUT_SECONDS = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "12"))

_SYSTEM_PROMPT = (
    "You are a formatting and readability assistant for a legal-information "
    "system. You will be given an already-grounded, already-cited answer "
    "assembled from retrieved statutory/treaty sources. Your ONLY job is to "
    "rephrase it into clearer, more natural prose for a reader. You must NOT:\n"
    "- add any new legal claim, fact, statute, section, treaty, or citation "
    "that is not already present in the input text\n"
    "- remove, renumber, translate, or alter any '[Source: ...]' tag, or any "
    "Act name, Section/Article/Rule/Treaty number inside it\n"
    "- change the substantive meaning of any sentence\n"
    "- add a preamble, apology, or any text outside the rewritten answer\n"
    "Every '[Source: ...]' tag from the input MUST appear verbatim, in the "
    "same order, in your output. If you are not confident you can do this "
    "safely, return the input text unchanged."
)

_CITATION_TAG_RE = re.compile(r"\[Source:[^\]]+\]")


def _extract_citation_tags(text: str) -> List[str]:
    return _CITATION_TAG_RE.findall(text)


def _citations_preserved(original: str, candidate: str) -> bool:
    """
    The single non-negotiable safety check: every citation tag from the
    original grounded text must appear, verbatim, in the candidate — same
    set, same multiset (a tag dropped or duplicated is also a failure).
    Order is not required (a paraphrase may reasonably reorder sentences),
    but content must be exact, since these tags are the traceability
    guarantee back to a specific retrieved source.
    """
    original_tags = sorted(_extract_citation_tags(original))
    candidate_tags = sorted(_extract_citation_tags(candidate))
    return bool(original_tags) and original_tags == candidate_tags


def paraphrase_answer(grounded_text: str) -> Tuple[str, bool]:
    """
    Returns (text, used_llm). On any failure, disablement, or missing
    config, returns (grounded_text, False) unchanged — this function must
    never be able to make the answer less grounded than its input.
    """
    if not _ENABLED or not GROQ_API_KEY or not grounded_text.strip():
        return grounded_text, False

    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed; skipping Groq paraphrase layer.")
        return grounded_text, False

    try:
        response = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "temperature": 0.2,
                "max_tokens": 1200,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": grounded_text},
                ],
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        candidate = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        # Broad on purpose: covers no network route to api.groq.com, DNS
        # failure, timeout, rate limiting, malformed response, missing/
        # revoked key, model-not-found, etc. All of these mean "fall back
        # to the grounded template answer", none of them a request failure.
        logger.info("Groq paraphrase call failed or unavailable: %r. Using grounded template answer.", e)
        return grounded_text, False

    if not candidate or not _citations_preserved(grounded_text, candidate):
        logger.warning(
            "Groq paraphrase output failed citation-preservation check; "
            "discarding and using the grounded template answer instead."
        )
        return grounded_text, False

    return candidate, True
