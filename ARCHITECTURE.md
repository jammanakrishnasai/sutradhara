# SUTRADHARA — System Architecture

## A. System architecture

```
User (browser)
   │
   ▼
React + Tailwind Frontend (Vite dev server / static build)
   │  fetch /api/*
   ▼
FastAPI Backend
   │
   ├─▶ Query Understanding + Product Classifier  (app/classifier.py)
   ├─▶ Jurisdiction Router                         (app/jurisdiction.py — hard filter)
   ├─▶ IP/Regulatory Area Router                    (app/jurisdiction.py)
   ├─▶ Hybrid Retrieval: sentence-transformer embeddings + FAISS, auto-falling
   │   back to TF-IDF if the embedding model can't be downloaded  (app/retrieval.py)
   ├─▶ Evidence scoring / Confidence + Abstention   (app/confidence.py)
   ├─▶ Grounded Answer Assembly (+ ABS + TK pointer) (app/answer.py)
   └─▶ Audit / Feedback / Escalation store (SQLite)  (app/db.py)
   │
   ▼
Neo4j (optional, Phase 6) — explainability graph
   backend/graph/schema.cypher
```

The answer is assembled directly from retrieved source text first, which
guarantees zero hallucination independent of any LLM. An **optional Groq
paraphrase layer** (`app/llm.py`, model `openai/gpt-oss-120b`) then runs on
top of that already-grounded text purely to smooth it into more natural
prose. It is constrained to paraphrase only — never to introduce a new legal
claim, statute, or citation — and every `[Source: ...]` tag is checked
programmatically after the call; if any tag was altered, added, or dropped,
the paraphrase is discarded and the original template-assembled answer is
used instead. If `GROQ_API_KEY` is unset or the call fails for any reason
(no network route, timeout, rate limit), the pipeline falls back to the
grounded template answer with no visible difference to the rest of the
response. This is the single most important invariant to preserve as the
system grows.

## B. Folder structure

See `README.md` §4.

## C. Database schema (SQLite — metadata, feedback, audit)

```sql
audit_log(id, timestamp, query, jurisdiction, category, confidence, abstained, sources_json)
feedback(id, timestamp, query, answer_id, rating, comment)
escalation(id, timestamp, query, product_category, jurisdiction, relevant_ip_area,
           retrieved_sources, contact_email, status)
```

## D. Neo4j graph schema

See `backend/graph/schema.cypher`. Node labels: `Jurisdiction`,
`ProductCategory`, `IPRegime`, `Law`, `Provision`, `Source`,
`TraditionalKnowledge`, `BiologicalResource`. Relationships:
`belongs_to`, `relevant_to`, `governed_by`, `contains`, `supported_by`,
`may_involve`, `may_trigger`, `referenced_by`, `governs` — matching §14 of
the brief exactly.

## E. RAG pipeline

1. **Hard filter** candidates by jurisdiction (India / International) —
   never combined.
2. **Soft rank**: with the embeddings backend active, per-jurisdiction FAISS
   `IndexFlatIP` search over L2-normalized sentence-transformer embeddings
   (inner product on normalized vectors = cosine similarity). If the
   embedding model can't be loaded (no internet to the Hugging Face Hub),
   automatic fallback to TF-IDF cosine similarity between the query and each
   document's `title + section + summary + domain`. Either way, a small
   domain-match boost is applied *only* when there is already genuine
   relevance from the base similarity score (prevents an irrelevant document
   from passing purely on a category-default boost — this was caught and
   fixed during testing).
3. Documents below a relevance floor are dropped entirely.
4. Confidence is computed from the *retained* set (§I below).
5. If confidence is below threshold or the set is empty → abstain.

## F. API specification

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/classify` | Classify a query into one of 6 product categories |
| POST | `/api/analyze` | Full pipeline: classification → routing → retrieval → answer/abstention |
| POST | `/api/query` | Alias for `/api/analyze` (spec compatibility) |
| GET | `/api/sources/{id}` | Fetch one corpus document's full metadata |
| GET | `/api/graph` | Static explainability graph (nodes/edges) |
| POST | `/api/feedback` | Log a rating/comment |
| POST | `/api/escalate` | Log a human-facilitator escalation |
| GET | `/api/eval` | Real logged evaluation stats (never fabricated) |
| GET | `/api/health` | Liveness + corpus size |

Request/response shapes are Pydantic models in `app/schemas.py`, matching the
`/api/analyze` example in the brief (§15) field-for-field.

## G. UI screen structure

Implemented as a single-page app with a tab bar rather than 7 separate
routes, to keep the demo fast and the codebase small — all 7 required
"screens" are present as sections/modals within it:

1. Landing / Query — top panel (jurisdiction switch + query box)
2. Product Classification — classification card in the result view
3. Analysis Result — assessment + confidence + ABS/TK panels
4. Source / Citation Viewer — `SourceCard` grid, one per retrieved document
5. Knowledge Graph — dedicated tab
6. Human Escalation — modal, triggered from the result view or the
   abstention panel
7. Evaluation Dashboard — dedicated tab

## H. Component hierarchy

```
App
├── JurisdictionSwitch
├── (query textarea + Analyze button)
├── ConfidenceMeter
├── SourceCard[]
├── EscalationModal
├── KnowledgeGraphView   (tab)
└── EvalDashboard        (tab)
```

## I. Knowledge corpus structure

25 curated documents in `backend/data/corpus.json` (13 India + 12
International), covering Patents/TKDL, Drugs & Cosmetics, ABS/Biological
Diversity, Geographical Indications, Trademarks, Copyright, Designs, Plant
Variety Protection, FSSAI/Ayurveda-Aahar, Advertising, Labelling, TRIPS,
CBD, Nagoya, WIPO, PCT, Madrid, Hague, Berne, Paris, and UPOV. Every entry uses real, well-established, publicly
known provisions (e.g. Patents Act §3(p)/§3(j), TRIPS Art. 27, CBD, Nagoya
Protocol) — no invented sections, treaty articles, or case names. Where an
exact deep-link URL could not be verified, the `precision` field says so
explicitly rather than presenting a fabricated link as authoritative.

## J. Metadata format

Matches the brief's §7 schema exactly, with two additions found necessary
during implementation: `retrieved_date` (for source-versioning per §22) and
`precision` (honest statement of how exact the section-level citation is).

## K. Classification logic

Deliberately rule-based (keyword matching across the 6 categories), not an
LLM call — see `app/classifier.py` docstring for the reasoning: classification
is a routing decision the rest of the pipeline depends on, so it needs to be
deterministic and auditable. Returns a clarification question instead of a
low-confidence guess when no category has a clear signal.

## L. Jurisdiction-routing logic

`resolve_jurisdiction()` validates against `{India, International}` only.
`route_areas()` matches query keywords against the IP/regulatory domain list
in §5 of the brief, folds in the classified category's typical areas, and
caps the result at 4 areas so the UI never shows every category for every
query (per the brief's explicit instruction).

## M. Citation-validation logic

Every source returned by `/api/analyze` is a document that was actually
retrieved from the corpus (never invented at answer-generation time) —
the answer text is built by directly concatenating retrieved sources'
`summary` fields with an inline `[Source: title, section]` tag per claim, so
citation and claim can never drift apart.

## N. Confidence calculation approach

Weighted combination (see `app/confidence.py`):
`0.35·retrieval_relevance + 0.15·source_count_factor + 0.20·source_authority
+ 0.10·agreement + 0.20·classification_confidence`, mapped to HIGH (≥0.75),
MEDIUM (≥0.40), LOW (<0.40).

## O. Safe-abstention logic

Abstain when the retained retrieval set is empty OR combined confidence is
below 0.40. Verified in testing: an out-of-scope query correctly produces
zero retained sources and triggers the clarification/abstention path rather
than a hallucinated answer.

## P. Test queries

8 manually curated queries in `backend/data/test_queries.json` (TQ-01–TQ-08),
covering both required demo scenarios, jurisdiction switching, an
ABS-triggering query, a GI-triggering query, and a deliberate out-of-scope
query.

## Q. Judge demo script

See `README.md` §2.

## R. Deployment architecture (suggested, not yet built)

```
Frontend  → static build (npm run build) → any static host (Vercel/Netlify)
Backend   → FastAPI on Render/Railway/a VM behind Uvicorn+Gunicorn
Database  → SQLite for the prototype; PostgreSQL for anything beyond a demo
Neo4j     → Neo4j Aura (managed) if the live graph is needed beyond the demo
```

## S. Development roadmap

Phases 1–5 (RAG + citations, classification, jurisdiction separation,
IP/regulatory routing, confidence + abstention) are implemented and tested
end-to-end. Phase 6 (Neo4j) has a schema and a static-graph fallback but no
live database wired in. Phase 7 (Telugu) covers both UI chrome and live
translation of the generated answer (`app/translate.py`, via
`deep-translator`/Google Translate), with a verified fail-safe fallback to
English when the translation service is unreachable. Phase 8 (escalation) is
implemented. Phase 9 (UI polish) has a first pass; Phase 10
(testing/deployment/demo prep) is partially done — unit-level pipeline
testing is complete, deployment is not yet configured.
