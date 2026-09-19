"""
Answer translation.

Phase 7 of the brief scoped multilingual support as "UI chrome first, don't
spend most of development time on languages." That's right for a v0, but a
judge asking for a Telugu answer and getting English back looks broken, not
scoped. This module adds real machine translation of the *generated answer
text* (which is template-assembled from English-language legal sources, so
translating it is safe — we are not asking a model to invent legal claims in
Telugu, only to render already-grounded English sentences in Telugu).

Deliberately NOT translated:
  - Source titles, section numbers, authority names, URLs — these are
    official document identifiers; translating them would make citations
    unverifiable and is standard practice not to translate.
  - The corpus.json content itself — corpus stays English/source-language;
    only the assembled answer is translated per-request.

PROVIDER CHAIN: uses deep-translator (free, no API key), trying Google
Translate first, then MyMemory as a second free provider, in that order.
Both are live network calls, and both are unofficial/rate-limited free
services (Google's especially so — it's a scrape of translate.google.com,
not a paid API, and returns HTTP 429/TooManyRequests fairly readily on
shared or high-traffic IPs, independent of this app's own call volume).
Falling through to a second provider makes that much less likely to take
the whole feature down. If every provider fails (offline, all rate-limited,
services down), we fail safe: return the original English text plus a flag
so the frontend can show a small "(translation unavailable — showing
English)" note instead of silently losing content or crashing the request.
For the query-translation direction specifically, main.py additionally
falls back to language.fallback_normalize() (an offline term-substitution
gloss) so retrieval still gets usable English signal even with zero network
access — see language.py.
"""
from typing import Tuple, Optional, List, Callable
from collections import OrderedDict
import hashlib
import logging
import re

try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

logger = logging.getLogger("ip_sakti.translate")

# The same demo queries get re-run repeatedly during rehearsal and again
# live in front of judges (Demo 4's exact script, retries after a
# transient failure, a judge asking the same question twice). Both free
# providers are rate-limited independent of this app's own logic, so
# memoizing identical (text, source, target) calls for the life of the
# process meaningfully cuts real request volume without changing any
# translation *behavior* -- a cache hit returns exactly what a fresh
# successful call would have returned. Bounded (simple FIFO eviction via
# OrderedDict) so a long-running demo process can't grow this unbounded.
_CACHE: "OrderedDict[str, str]" = OrderedDict()
_CACHE_MAX_ENTRIES = 256


def _cache_key(text: str, source: str, target: str) -> str:
    # Hash rather than store the raw text as the key: answer text can be
    # long (multi-paragraph), and every corpus/query combination is
    # already reproducible from (source, target, text) alone.
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{source}:{target}:{digest}"


def _cache_get(key: str) -> Optional[str]:
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    return None


def _cache_put(key: str, value: str) -> None:
    _CACHE[key] = value
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX_ENTRIES:
        _CACHE.popitem(last=False)

# Google's own codes ("en", "te") work fine as-is. MyMemory, however,
# requires locale-qualified codes (e.g. "en-US", "te-IN") and raises
# LanguageNotSupportedException on bare "en"/"te" -- this is NOT a network
# problem, it fails the same way with a perfect connection, so it needs its
# own mapping rather than reusing _LANG_MAP.
_LANG_MAP = {"te": "te", "hi": "hi", "ta": "ta", "ml": "ml", "sa": "sa", "en": "en"}
_MYMEMORY_LANG_MAP = {"te": "te-IN", "hi": "hi-IN", "ta": "ta-IN", "ml": "ml-IN", "sa": "sa-IN", "en": "en-US"}

# Each free provider enforces its OWN hard per-request character limit,
# independent of rate-limiting/network issues:
#   - Google (via deep-translator's scrape endpoint): ~5000 chars/request.
#   - MyMemory: a hard 500 chars/request (raises NotValidLength above that;
#     see deep_translator/mymemory.py -- is_input_valid(text, max_chars=500)).
# The assembled multi-source answer routinely exceeds 500 chars, so without
# chunking, MyMemory rejects it every single time regardless of connectivity.
# Limits below are set conservatively under each provider's real cap.
_PROVIDER_MAX_CHARS = {"google": 4500, "mymemory": 480}


def _split_into_chunks(text: str, max_chars: int) -> List[str]:
    """
    Split text into pieces <= max_chars, preferring to break on paragraph
    boundaries ("\\n\\n"), then sentence boundaries, then a hard cut only as
    a last resort. Keeps whole paragraphs/sentences together where possible
    so each chunk translates coherently on its own.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    current = ""

    def flush():
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for para in text.split("\n\n"):
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue

        flush()
        if len(para) <= max_chars:
            current = para
            continue

        # This single paragraph alone exceeds max_chars -- split by sentence.
        sub = ""
        for sent in re.split(r"(?<=[.!?])\s+", para):
            cand = f"{sub} {sent}" if sub else sent
            if len(cand) <= max_chars:
                sub = cand
                continue
            if sub:
                chunks.append(sub)
                sub = ""
            if len(sent) <= max_chars:
                sub = sent
            else:
                # Last resort: hard-cut an unreasonably long single sentence.
                for i in range(0, len(sent), max_chars):
                    chunks.append(sent[i:i + max_chars])
        if sub:
            chunks.append(sub)

    flush()
    return chunks


def _translate_full_text(text: str, translate_one: Callable[[str], str], max_chars: int) -> Optional[str]:
    """
    Translate arbitrarily long text with a single provider by chunking to
    that provider's own limit, translating each chunk, and rejoining with
    paragraph breaks. Returns None (whole attempt fails) if any chunk fails
    -- we don't stitch together a partially-translated answer from a
    provider that broke midway; the caller moves on to the next provider.
    """
    chunks = _split_into_chunks(text, max_chars)
    translated_chunks = []
    for chunk in chunks:
        result = translate_one(chunk)
        if not result:
            return None
        translated_chunks.append(result)
    return "\n\n".join(translated_chunks)


def _translate_with_fallback_providers(text: str, source: str, target: str) -> Optional[str]:
    """
    Try each free provider in order; return the first non-empty result, or
    None if all of them fail (offline, rate-limited, service down, wrong
    language code, text too long for that provider's own limit, etc.). Each
    provider's exceptions are caught and logged individually so one
    provider's failure doesn't stop us from trying the next -- but the
    reason is still visible in the logs, instead of disappearing into a
    bare `False`.
    """
    if not _AVAILABLE:
        return None

    key = _cache_key(text, source, target)
    cached = _cache_get(key)
    if cached is not None:
        logger.info("translation cache hit (%s->%s, %d chars)", source, target, len(text))
        return cached

    providers = [
        (
            "google",
            lambda t: GoogleTranslator(source=source, target=target).translate(t),
            _PROVIDER_MAX_CHARS["google"],
        ),
        (
            "mymemory",
            lambda t: MyMemoryTranslator(
                source=_MYMEMORY_LANG_MAP.get(source, source),
                target=_MYMEMORY_LANG_MAP.get(target, target),
            ).translate(t),
            _PROVIDER_MAX_CHARS["mymemory"],
        ),
    ]
    for name, translate_one, max_chars in providers:
        try:
            result = _translate_full_text(text, translate_one, max_chars)
            if result:
                _cache_put(key, result)
                return result
        except Exception as e:
            logger.info("translation provider '%s' failed: %r", name, e)
            continue
    return None


def translate_text(text: str, target_lang: str) -> Tuple[str, bool]:
    """
    Returns (text, translated_ok). If target_lang is 'en' or empty text,
    returns the original text untouched with translated_ok=True (no-op).
    """
    if not text or target_lang == "en" or target_lang not in _LANG_MAP:
        return text, True

    # Chunked per-provider inside _translate_with_fallback_providers -- long
    # multi-source answers now translate correctly instead of silently
    # failing MyMemory's 500-char limit.
    translated = _translate_with_fallback_providers(text, "en", _LANG_MAP[target_lang])
    if translated is None:
        return text, False
    return translated, True


def translate_to_english(text: str, source_lang: str) -> Tuple[str, bool]:
    """
    The other half of the pipeline: translate a non-English *query* to
    English so it can be matched against the (English) authoritative
    corpus. This is a retrieval-only step — the original query text is
    always preserved separately for display/logging; only this translated
    copy is used to build the retrieval query.

    Returns (text, translated_ok), same contract as translate_text().
    """
    if not text or source_lang == "en" or source_lang not in _LANG_MAP:
        return text, True

    translated = _translate_with_fallback_providers(text, _LANG_MAP[source_lang], "en")
    if translated is None:
        return text, False
    return translated, True

