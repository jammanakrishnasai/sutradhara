"""
Retrieval layer.

Primary path: sentence-transformer embeddings + FAISS (per the brief's RAG
upgrade request). Two per-jurisdiction FAISS IndexFlatIP indices are built
over L2-normalized embeddings (inner product on normalized vectors = cosine
similarity), so jurisdiction filtering is structural — an India query
physically cannot touch the International index, not just post-filtered.

Fallback path: the original TF-IDF retrieval (kept verbatim, renamed
`_retrieve_tfidf`). This is not a toy fallback — it is what actually runs in
any environment without live internet access to download the embedding
model from the Hugging Face Hub on first use (e.g. this project's own build
sandbox), and it is what the automated test suite exercises. In a normal
internet-connected dev/demo machine, the model downloads once (~90MB, cached
locally by sentence-transformers afterwards) and the embeddings path takes
over transparently — no config flag to flip, no API change either way.

`retrieve()` keeps the exact same signature and return shape regardless of
which backend served the request: List[dict] with a `relevance_score` field
added, same corpus dict fields otherwise. `retrieval.BACKEND` reports which
one is actually active, for logging/tests.
"""
import json
import logging
import os
import re
from typing import List, Dict, Any, Union

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("ip_sakti.retrieval")

_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "corpus.json")

with open(_CORPUS_PATH, "r", encoding="utf-8") as f:
    _CORPUS: List[Dict[str, Any]] = json.load(f)

_CORPUS_BY_ID = {doc["id"]: doc for doc in _CORPUS}

_DOC_TEXTS = [f"{d['title']} {d['section']} {d['summary']} {d['domain']}" for d in _CORPUS]

# Retrieval-floor / domain-boost constants differ by backend: cosine
# similarity from a general-purpose sentence embedding model sits on a
# noticeably higher baseline (~0.15-0.35) for *unrelated* text than sparse
# TF-IDF does, because embeddings encode broad topical/semantic proximity,
# not just shared vocabulary. Reusing the TF-IDF thresholds unchanged would
# let more irrelevant documents pass the abstention floor. These embedding
# thresholds are a reasoned starting point, not empirically tuned against
# live model output — this sandbox cannot reach the Hugging Face Hub to
# download the model and verify real score distributions (see EMBEDDINGS
# section below). Revisit once you can run this end-to-end with internet.
_TFIDF_RELEVANCE_FLOOR = 0.05
_TFIDF_DOMAIN_BOOST_GATE = 0.02
_TFIDF_DOMAIN_BOOST = 0.15

_EMB_RELEVANCE_FLOOR = 0.30
_EMB_DOMAIN_BOOST_GATE = 0.20
_EMB_DOMAIN_BOOST = 0.10

_EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _light_stem(token: str) -> str:
    """
    Very small suffix-stripping stemmer (no external NLTK data needed offline).
    Exact-token TF-IDF otherwise misses obvious matches like patent/patents/
    patentable/patentability, which would silently starve retrieval.
    """
    for suffix in ("abilities", "ability", "ization", "ations", "ation", "ing", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _tokenizer(text: str) -> List[str]:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [_light_stem(w) for w in words]


_VECTORIZER = TfidfVectorizer(stop_words="english", tokenizer=_tokenizer, token_pattern=None)
_DOC_MATRIX = _VECTORIZER.fit_transform(_DOC_TEXTS)


def get_document(doc_id: str):
    return _CORPUS_BY_ID.get(doc_id)


# --------------------------------------------------------------------------
# EMBEDDINGS + FAISS (primary path)
# --------------------------------------------------------------------------
BACKEND = "tfidf"  # flipped to "embeddings" below iff model+index load succeeds
_EMBED_MODEL = None
_FAISS_INDEX_BY_JUR: Dict[str, Any] = {}
_JUR_DOC_IDS: Dict[str, List[int]] = {}  # per-jurisdiction: FAISS row -> global corpus index


def _try_init_embeddings() -> bool:
    """
    Attempt to load the sentence-transformer model and build per-jurisdiction
    FAISS indices. Returns True on success. Any failure (missing packages,
    no internet to fetch the model from the Hugging Face Hub, corrupted
    cache, etc.) is caught broadly and logged — this must never crash
    startup; the TF-IDF path above is already fully built and ready to serve
    every request on its own.
    """
    global _EMBED_MODEL, _FAISS_INDEX_BY_JUR, _JUR_DOC_IDS

    if os.getenv("SUTRADHARA_DISABLE_EMBEDDINGS") == "1":
        logger.info("Embeddings backend disabled by SUTRADHARA_DISABLE_EMBEDDINGS. Using TF-IDF.")
        return False

    try:
        import faiss
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        logger.warning("Embeddings backend unavailable (missing package): %r. Using TF-IDF.", e)
        return False

    try:
        model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
        doc_embeddings = model.encode(_DOC_TEXTS, normalize_embeddings=True, show_progress_bar=False)
        doc_embeddings = np.asarray(doc_embeddings, dtype="float32")

        index_by_jur: Dict[str, Any] = {}
        ids_by_jur: Dict[str, List[int]] = {}
        for jur in ("India", "International"):
            row_ids = [i for i, d in enumerate(_CORPUS) if d["jurisdiction"] == jur]
            if not row_ids:
                continue
            sub_matrix = doc_embeddings[row_ids]
            dim = sub_matrix.shape[1]
            index = faiss.IndexFlatIP(dim)  # inner product on normalized vectors == cosine similarity
            index.add(sub_matrix)
            index_by_jur[jur] = index
            ids_by_jur[jur] = row_ids

        _EMBED_MODEL = model
        _FAISS_INDEX_BY_JUR = index_by_jur
        _JUR_DOC_IDS = ids_by_jur
        logger.info(
            "Embeddings backend ready: model=%s, indices=%s",
            _EMBEDDING_MODEL_NAME, {k: v.ntotal for k, v in index_by_jur.items()},
        )
        return True
    except Exception as e:
        # Broad on purpose: covers no-internet model download failures
        # (OSError/HTTPError variants from huggingface_hub), corrupted local
        # cache, FAISS build issues, etc. — all of which mean "fall back",
        # none of which should be allowed to take the API down.
        logger.warning("Embeddings backend failed to initialize: %r. Falling back to TF-IDF.", e)
        return False


if _try_init_embeddings():
    BACKEND = "embeddings"


def _retrieve_embeddings(variants: List[str], jurisdiction: str, areas: List[str], top_k: int) -> List[Dict[str, Any]]:
    index = _FAISS_INDEX_BY_JUR.get(jurisdiction)
    row_ids = _JUR_DOC_IDS.get(jurisdiction)
    if index is None or not row_ids:
        return []

    query_vecs = _EMBED_MODEL.encode(variants, normalize_embeddings=True, show_progress_bar=False)
    query_vecs = np.asarray(query_vecs, dtype="float32")

    k = min(len(row_ids), max(top_k * 3, 10))
    all_scores, all_idx = index.search(query_vecs, k)  # each: (num_variants, k)

    # Max-across-variants rerank, mirroring the TF-IDF path: a document only
    # needs to match one good phrasing of the question, not every variant.
    best_score_per_local_row: Dict[int, float] = {}
    for variant_scores, variant_rows in zip(all_scores, all_idx):
        for score, local_row in zip(variant_scores, variant_rows):
            if local_row < 0:
                continue
            if score > best_score_per_local_row.get(local_row, -1.0):
                best_score_per_local_row[local_row] = float(score)

    scored = []
    for local_row, raw_sim in best_score_per_local_row.items():
        global_i = row_ids[local_row]
        doc = _CORPUS[global_i]
        score = raw_sim
        if doc["domain"] in areas and raw_sim > _EMB_DOMAIN_BOOST_GATE:
            score += _EMB_DOMAIN_BOOST
        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, doc in scored[:top_k]:
        if score > _EMB_RELEVANCE_FLOOR:
            d = dict(doc)
            d["relevance_score"] = round(min(score, 0.99), 3)
            results.append(d)
    return results


def _retrieve_tfidf(variants: List[str], jurisdiction: str, areas: List[str], top_k: int) -> List[Dict[str, Any]]:
    # 1. Hard filter by jurisdiction — never mixed.
    candidate_idx = [i for i, d in enumerate(_CORPUS) if d["jurisdiction"] == jurisdiction]
    if not candidate_idx:
        return []

    query_vecs = _VECTORIZER.transform(variants)
    sims_per_variant = cosine_similarity(query_vecs, _DOC_MATRIX[candidate_idx])
    sims = sims_per_variant.max(axis=0)

    scored = []
    for local_i, global_i in enumerate(candidate_idx):
        doc = _CORPUS[global_i]
        raw_sim = float(sims[local_i])
        score = raw_sim
        # Only apply the domain-match boost when there is already some genuine
        # lexical relevance — otherwise a domain-only match on a completely
        # off-topic query (e.g. classifier fell back to a default category)
        # could push an irrelevant document above the retrieval threshold.
        if doc["domain"] in areas and raw_sim > _TFIDF_DOMAIN_BOOST_GATE:
            score += _TFIDF_DOMAIN_BOOST
        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, doc in scored[:top_k]:
        if score > _TFIDF_RELEVANCE_FLOOR:
            d = dict(doc)
            d["relevance_score"] = round(min(score, 0.99), 3)
            results.append(d)
    return results


def retrieve(
    query: Union[str, List[str]],
    jurisdiction: str,
    areas: List[str],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    `query` may be a single retrieval string, or a list of query-expansion
    variants (see query_expansion.py). Dispatches to the embeddings+FAISS
    backend if it initialized successfully at import time, else to TF-IDF.
    Same return shape either way: List[dict] with a `relevance_score` field.
    """
    variants = query if isinstance(query, (list, tuple)) else [query]
    variants = [v for v in variants if v and v.strip()]
    if not variants:
        return []

    if BACKEND == "embeddings":
        return _retrieve_embeddings(variants, jurisdiction, areas, top_k)
    return _retrieve_tfidf(variants, jurisdiction, areas, top_k)
