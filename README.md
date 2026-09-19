# SUTRADHARA — AI-Powered IP & Regulatory Intelligence for Ayurveda — Team Chaturya (SIH26045)

A multilingual, RAG-based, citation-grounded AI assistant for Intellectual
Property and regulatory guidance in Ayurveda, across Indian and
international regimes. Built for Ministry of AYUSH / All India Institute of
Ayurveda, Smart India Hackathon 2026.

This is a **working prototype**, not a production system. It prioritizes
correctness, traceability, and jurisdictional clarity over feature count, per
the problem statement's own restrictions (see `ARCHITECTURE.md` §26).

---

## 1. Quick start

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate     # optional but recommended
pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY here if you want the paraphrase layer; blank works fine
uvicorn app.main:app --reload --port 8000
```

Check it's alive: `curl http://127.0.0.1:8000/api/health`

The system works fully with `GROQ_API_KEY` left blank — the grounded,
template-assembled answer is returned as-is (`llm_paraphrased: false`). Set
`GROQ_API_KEY` and `GROQ_MODEL` in `.env` to enable the optional Groq
paraphrase pass (see `app/llm.py`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the printed URL (default `http://127.0.0.1:5173`). The Vite dev server
proxies `/api/*` to `http://127.0.0.1:8000` (see `vite.config.js`) — make sure
the backend is running first.

### Neo4j (optional — Phase 6, not required for the core demo)

The prototype's `/api/graph` endpoint returns a static explainability graph
that works without Neo4j. If you want the real graph database running:

```bash
cat backend/graph/schema.cypher | cypher-shell -u neo4j -p <password>
```

---

## 2. Judge demo script (3–5 minutes)

**Demo 1 — India, classical formulation (core scenario)**
1. Jurisdiction: 🇮🇳 India
2. Ask: *"Can I patent a classical Ayurvedic formulation?"*
3. Show: classification (Classical / Generic Medicine), applicable areas
   (Patents, Traditional Knowledge, ABS), the grounded answer citing
   Patents Act §3(p)/§3(j) and the Drugs & Cosmetics Act, the Traditional
   Knowledge / Prior-Art Pointer, and the confidence breakdown.

**Demo 2 — jurisdiction switch**
1. Switch to 🌍 International, ask the same question.
2. Show the answer and source set change completely — now TRIPS Art. 27,
   CBD, Nagoya Protocol, TKDL — with **zero** Indian statutes present.

**Demo 3 — safe abstention**
1. Ask an out-of-scope question. Two variants are worth showing:
   - *"What is the boiling point of tungsten?"* — no classifier signal at all,
     so the system asks a clarification question rather than guessing.
   - A query that classifies fine but has no supporting evidence — the system
     instead returns "Insufficient authoritative evidence to provide a
     reliable answer" and offers escalation.
   Either way: never a hallucinated legal claim.

**Demo 4 — multilingual UI (English / Telugu)**
1. Toggle English → తెలుగు, or type the query directly in Telugu script.
2. The query itself is now translated to English for retrieval (so a Telugu
   question surfaces the same evidence as its English equivalent — see
   `app/language.py` + `app/translate.py`), and the generated answer is
   translated back to Telugu for display. Source titles, section numbers,
   and authority names stay untranslated, since those are official
   identifiers.
3. Both directions make a live network call (Google Translate via
   `deep-translator`, with a MyMemory fallback). If the judging venue's
   internet is flaky, query normalization falls back to an offline
   term-substitution gloss (`language.fallback_normalize`) and the answer
   falls back to English with a small "translation unavailable" note —
   verified in testing, since that's exactly what happens in the sandbox
   this was built in (no route to Google Translate or Hugging Face there).

Optional, if time allows: show the Knowledge Graph tab (explainability) and
the Evaluation Dashboard tab (real logged stats only, "Evaluation pending"
where nothing has been measured yet).

---

## 3. Test queries and automated tests

`backend/data/test_queries.json` has 8 manually curated test queries
(TQ-01–TQ-08) for manual verification via the Evaluation Dashboard — no
scores are auto-generated or fabricated.

`backend/tests/` has automated pytest coverage:
- `test_multilingual.py` — language detection, Telugu-query evidence
  equivalence with its English counterpart, unsupported-query abstention,
  and (network permitting) the real translation path.
- `test_retrieval_and_citations.py` — both named demo scenarios, India/
  International jurisdiction isolation in both directions, citation-field
  completeness, corpus size, and that the generated answer only cites
  sources that were actually retrieved.

Run them with:
```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```
One test (`test_live_translation_path`) is skipped rather than failed if the
machine running it has no internet access.

---

## 4. Project structure

```
sutradhara/
├── README.md                  (this file)
├── ARCHITECTURE.md            (full system design: A–S deliverables)
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app + all endpoints
│   │   ├── classifier.py      Product classification (rule-based, with
│   │   │                       explicit negation-pattern handling)
│   │   ├── jurisdiction.py    Jurisdiction + IP-area routing
│   │   ├── retrieval.py       Embeddings + FAISS retrieval, falls back to
│   │   │                       TF-IDF if the embedding model can't load
│   │   ├── language.py        Input-language detection + offline fallback
│   │   │                       normalization for query translation
│   │   ├── query_expansion.py Small domain-concept query-variant expansion
│   │   ├── translate.py       Query→English / answer→Telugu translation,
│   │   │                       multi-provider with fail-safe fallback
│   │   ├── confidence.py      Evidence-based confidence + abstention
│   │   ├── answer.py          Grounded answer / ABS checklist / TK pointer
│   │   ├── db.py               SQLite audit log / feedback / escalation
│   │   └── schemas.py         Pydantic request/response models
│   ├── data/
│   │   ├── corpus.json        25-document curated knowledge corpus
│   │   └── test_queries.json  Manually verified test set
│   ├── graph/
│   │   └── schema.cypher      Neo4j schema + seed data
│   ├── tests/                 Automated pytest suite (see §3)
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx             Main analyze flow
    │   ├── api.js               API client
    │   ├── copy.js              English/Telugu UI strings
    │   └── components/          JurisdictionSwitch, ConfidenceMeter,
    │                             SourceCard, EscalationModal,
    │                             KnowledgeGraphView, EvalDashboard
    └── (Vite + Tailwind config)
```

---

## 5. Known limitations (be upfront with judges about these)

- The corpus is a curated prototype set (25 documents), not the full legal
  universe — by design (see brief §7), though now covering patents/TKDL,
  drugs & cosmetics, ABS/biodiversity, GI, trademarks, copyright, designs,
  plant variety protection, FSSAI, and the major WIPO-administered treaties
  (PCT, Madrid, Hague, Berne, Paris) plus UPOV.
- Retrieval uses sentence-transformer embeddings + FAISS as the primary
  path, with an automatic, tested fallback to TF-IDF if the embedding model
  can't be downloaded (no internet to Hugging Face) — same interface either
  way. `retrieval.BACKEND` reports which one actually served a given
  request. The embedding-path relevance thresholds are a reasoned starting
  point, not empirically tuned against live model output, since this was
  built in a sandbox with no route to the Hugging Face Hub — worth a quick
  sanity check with real queries once you have it running with internet.
- The answer is template-assembled directly from retrieved source summaries
  (guaranteed grounded) and then optionally passed through a Groq
  (`openai/gpt-oss-120b`) paraphrase layer (`app/llm.py`) purely for
  readability. The paraphrase is discarded automatically — falling back to
  the grounded template text — if any `[Source: ...]` citation tag is
  altered, or if `GROQ_API_KEY` is unset / the call fails for any reason
  (this sandbox has no outbound route to `api.groq.com`, so it was verified
  to fall back correctly, not verified against a live response — do that
  sanity check once you have it running with internet and a real key).
- TKDL is represented as a reference workflow only; this prototype does not
  and cannot connect to the real, access-restricted TKDL database.
- Multilingual support translates both the incoming query (for retrieval)
  and the generated answer (for display) live via Google Translate /
  MyMemory (through `deep-translator`, no API key needed) — this requires
  internet access at request time and was verified to fail safe (falls back
  to an offline term-substitution gloss for the query, and to English with
  a visible note for the answer) when the translation service is
  unreachable, since that's exactly what happens in the sandbox this was
  built in.
- Source URLs point to official portal domains, not verified deep links to
  specific clauses — each corpus entry's `precision` field says so honestly.
- The rule-based classifier now handles the specific "not found in a
  classical text" negation pattern explicitly (this was a real bug caught
  while testing Demo Scenario 2 — see `classifier.py`), but it is still
  keyword/pattern-based, not a general NLP classifier, so unusual phrasings
  of the same intent may not be recognized.
