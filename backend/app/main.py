import logging

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads backend/.env (GROQ_API_KEY, GROQ_MODEL, ...) if present
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import classifier, jurisdiction, retrieval, confidence, answer, db, translate
from . import language, query_expansion, llm
from .schemas import (
    AnalyzeRequest, AnalyzeResponse, SourceRef,
    EscalateRequest, FeedbackRequest,
)

app = FastAPI(title="SUTRADHARA API", version="0.1.0-prototype")

logger = logging.getLogger("ip_sakti.pipeline")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prototype only — restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "corpus_documents": len(retrieval._CORPUS)}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    try:
        jur = jurisdiction.resolve_jurisdiction(req.jurisdiction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # --- Multilingual normalization (retrieval-only; original query text is
    # preserved untouched for display, logging, and escalation). ---
    input_language = language.detect_language(req.query)
    retrieval_query = req.query
    if input_language != "en":
        translated, translated_ok = translate.translate_to_english(req.query, input_language)
        if translated_ok and translated.strip():
            retrieval_query = translated
        else:
            # Second, offline normalization strategy per the error-handling
            # requirement — never silently fall through to raw non-English
            # text, which would zero out the English-only TF-IDF tokenizer.
            retrieval_query = language.fallback_normalize(req.query)

    query_variants = query_expansion.expand_query(retrieval_query)

    # Classification and area-routing are keyword-based over English terms,
    # so they must also see the (translated) English retrieval query — not
    # the raw original-language text — to work for any input language rather
    # than only via the manual confirmed_category fallback path.
    classification = classifier.classify(retrieval_query, req.confirmed_category)

    if classification.needs_clarification:
        # Return early — the frontend should surface the clarification
        # question before calling /api/analyze again with confirmed_category set.
        abs_checklist = answer.build_abs_checklist(retrieval_query, [])
        return AnalyzeResponse(
            classification=classification,
            jurisdiction=jur,
            applicable_areas=[],
            answer="",
            confidence=0.0,
            confidence_label="LOW",
            confidence_breakdown={},
            sources=[],
            abs_checklist=abs_checklist,
            abstained=True,
            input_language=input_language,
            retrieval_query=retrieval_query if retrieval_query != req.query else None,
        )

    areas = jurisdiction.route_areas(retrieval_query, classification.category)
    retrieved = [] if jurisdiction.has_unsupported_foreign_country(req.query, jur) else retrieval.retrieve(query_variants, jur, areas, top_k=5)

    conf_score, conf_label, breakdown = confidence.score(retrieved, classification.confidence)
    abstained = confidence.should_abstain(conf_score, retrieved)
    abs_checklist = answer.build_abs_checklist(retrieval_query, retrieved)
    tk_pointer = answer.build_tk_pointer(classification.category, jur)

    lang = req.language if req.language in ("en", "te", "hi", "ta", "ml", "sa") else "en"

    logger.info(
        "INPUT_LANGUAGE=%s RETRIEVAL_LANGUAGE=en ORIGINAL=%r NORMALIZED=%r "
        "CLASSIFICATION=%s JURISDICTION=%s AREAS=%s RETRIEVED_CHUNKS=%d "
        "TOP_SCORE=%s SOURCES=%s EVIDENCE_SCORE=%s ABSTAIN=%s",
        input_language, req.query, retrieval_query,
        classification.category, jur, areas, len(retrieved),
        (retrieved[0]["relevance_score"] if retrieved else None),
        [s["id"] for s in retrieved], conf_score, abstained,
    )

    if abstained:
        db.log_audit(req.query, jur, classification.category, conf_score, True, retrieved)
        abstain_text, ok = translate.translate_text(
            "Insufficient authoritative evidence to provide a reliable answer from the available corpus.",
            lang,
        )
        return AnalyzeResponse(
            classification=classification,
            jurisdiction=jur,
            applicable_areas=areas,
            answer=abstain_text,
            confidence=conf_score,
            confidence_label=conf_label,
            confidence_breakdown=breakdown,
            sources=[SourceRef(**{**s, "relevance_score": s["relevance_score"]}) for s in retrieved],
            abs_checklist=abs_checklist,
            tk_pointer=tk_pointer,
            abstained=True,
            answer_language=lang,
            translation_available=ok,
            input_language=input_language,
            retrieval_query=retrieval_query if retrieval_query != req.query else None,
        )

    generated_answer = answer.build_answer(req.query, classification.category, jur, retrieved)

    # Optional Groq paraphrase layer: smooths the template-assembled answer
    # into more natural prose for display. Runs BEFORE Telugu translation and
    # is fail-safe — see llm.py. Every [Source: ...] tag must survive
    # unchanged or the original grounded text is used instead, so this can
    # never introduce an uncited or fabricated claim.
    generated_answer, used_llm = llm.paraphrase_answer(generated_answer)
    logger.info("LLM_PARAPHRASE_APPLIED=%s", used_llm)

    db.log_audit(req.query, jur, classification.category, conf_score, False, retrieved)

    # Translate the natural-language pieces only. Source titles, section
    # numbers, authority names, category labels, and area names are official
    # identifiers and are deliberately left untranslated (see app/translate.py).
    translation_ok = True
    if lang != "en":
        generated_answer, ok1 = translate.translate_text(generated_answer, lang)
        classification.reason, ok2 = translate.translate_text(classification.reason, lang)
        translation_ok = ok1 and ok2
        if tk_pointer:
            tk_pointer, ok3 = translate.translate_text(tk_pointer, lang)
            translation_ok = translation_ok and ok3
        if abs_checklist:
            abs_checklist.note, ok4 = translate.translate_text(abs_checklist.note, lang)
            translation_ok = translation_ok and ok4

    return AnalyzeResponse(
        classification=classification,
        jurisdiction=jur,
        applicable_areas=areas,
        answer=generated_answer,
        confidence=conf_score,
        confidence_label=conf_label,
        confidence_breakdown=breakdown,
        sources=[SourceRef(**s) for s in retrieved],
        abs_checklist=abs_checklist,
        tk_pointer=tk_pointer,
        abstained=False,
        answer_language=lang,
        translation_available=translation_ok,
        input_language=input_language,
        retrieval_query=retrieval_query if retrieval_query != req.query else None,
        llm_paraphrased=used_llm,
    )


@app.post("/api/query")
def query_alias(req: AnalyzeRequest):
    """Alias kept for architecture-spec compatibility; behaves like /api/analyze."""
    return analyze(req)


@app.get("/api/sources/{doc_id}")
def get_source(doc_id: str):
    doc = retrieval.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Source not found")
    return doc


@app.get("/api/graph")
def get_graph():
    """Static explainability graph for the prototype UI (mirrors graph/schema.cypher)."""
    return {
        "nodes": [
            {"id": "product", "label": "Ayurvedic Product", "type": "Product"},
            {"id": "category", "label": "Product Category", "type": "ProductCategory"},
            {"id": "tk", "label": "Traditional Knowledge", "type": "TraditionalKnowledge"},
            {"id": "regime", "label": "IP/Regulatory Regime", "type": "IPRegime"},
            {"id": "law", "label": "Governing Law", "type": "Law"},
            {"id": "provision", "label": "Provision", "type": "Provision"},
            {"id": "source", "label": "Authoritative Source", "type": "Source"},
        ],
        "edges": [
            {"from": "product", "to": "category", "label": "belongs_to"},
            {"from": "category", "to": "regime", "label": "relevant_to"},
            {"from": "category", "to": "tk", "label": "may_reference"},
            {"from": "regime", "to": "law", "label": "governed_by"},
            {"from": "law", "to": "provision", "label": "contains"},
            {"from": "provision", "to": "source", "label": "supported_by"},
        ],
        "note": "Static schema view for the prototype. See graph/schema.cypher for the live Neo4j model.",
    }


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    db.log_feedback(req.query, req.answer_id, req.rating, req.comment)
    return {"status": "recorded"}


@app.post("/api/escalate")
def escalate(req: EscalateRequest):
    escalation_id = db.log_escalation(
        req.query, req.product_category, req.jurisdiction,
        req.relevant_ip_area, req.retrieved_sources, req.contact_email,
    )
    return {"status": "escalated", "escalation_id": escalation_id}


@app.get("/api/eval")
def eval_summary():
    return db.get_eval_summary()
