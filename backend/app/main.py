import logging

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads backend/.env (GROQ_API_KEY, GROQ_MODEL, ...) if present
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from . import classifier, jurisdiction, retrieval, confidence, answer, db, translate, graph
from . import language, query_expansion, llm, tkdl, checklist, connectors, pdf_generator, eval_benchmark
from .schemas import (
    AnalyzeRequest, AnalyzeResponse, SourceRef,
    EscalateRequest, FeedbackRequest,
    ConnectorGrantRequest, ConnectorRevokeRequest, PdfExportRequest,
)

app = FastAPI(title="SUTRADHARA API", version="0.2.0-tkdl-enterprise")

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
    global _LAST_GRAPH
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
            retrieval_query = language.fallback_normalize(req.query)

    query_variants = query_expansion.expand_query(retrieval_query)
    classification = classifier.classify(retrieval_query, req.confirmed_category)

    if classification.needs_clarification:
        abs_checklist = answer.build_abs_checklist(retrieval_query, [])
        dynamic_graph = graph.build_dynamic_graph(
            query=req.query,
            category=classification.category,
            jurisdiction_name=jur,
            retrieved_sources=[],
            applicable_areas=[],
        )
        tkdl_res = tkdl.calculate_resemblance_score(req.query, classification.category, [])
        reg_chk = checklist.build_regulatory_checklist(req.query, classification.category, jur, [])
        _LAST_GRAPH = dynamic_graph
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
            graph=dynamic_graph,
            tkdl_resemblance=tkdl_res,
            regulatory_checklist=reg_chk,
        )

    areas = jurisdiction.route_areas(retrieval_query, classification.category)
    retrieved = [] if jurisdiction.has_unsupported_foreign_country(req.query, jur) else retrieval.retrieve(query_variants, jur, areas, top_k=5)

    conf_score, conf_label, breakdown = confidence.score(retrieved, classification.confidence)
    abstained = confidence.should_abstain(conf_score, retrieved)
    abs_checklist = answer.build_abs_checklist(retrieval_query, retrieved)
    tk_pointer = answer.build_tk_pointer(classification.category, jur)

    lang = req.language if req.language in ("en", "te", "hi", "ta", "ml", "sa") else "en"

    # Build dynamic Knowledge Graph
    dynamic_graph = graph.build_dynamic_graph(
        query=req.query,
        category=classification.category,
        jurisdiction_name=jur,
        retrieved_sources=retrieved,
        applicable_areas=areas,
    )
    _LAST_GRAPH = dynamic_graph

    # Calculate dynamic TKDL Resemblance Score and Regulatory Checklist
    tkdl_res = tkdl.calculate_resemblance_score(req.query, classification.category, retrieved)
    reg_chk = checklist.build_regulatory_checklist(req.query, classification.category, jur, retrieved)

    logger.info(
        "INPUT_LANGUAGE=%s RETRIEVAL_LANGUAGE=en ORIGINAL=%r NORMALIZED=%r "
        "CLASSIFICATION=%s JURISDICTION=%s AREAS=%s RETRIEVED_CHUNKS=%d "
        "TOP_SCORE=%s SOURCES=%s EVIDENCE_SCORE=%s ABSTAIN=%s TKDL_SCORE=%s",
        input_language, req.query, retrieval_query,
        classification.category, jur, areas, len(retrieved),
        (retrieved[0]["relevance_score"] if retrieved else None),
        [s["id"] for s in retrieved], conf_score, abstained, tkdl_res.get("score"),
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
            graph=dynamic_graph,
            tkdl_resemblance=tkdl_res,
            regulatory_checklist=reg_chk,
        )

    generated_answer = answer.build_answer(req.query, classification.category, jur, retrieved)

    generated_answer, used_llm = llm.paraphrase_answer(generated_answer)
    logger.info("LLM_PARAPHRASE_APPLIED=%s", used_llm)

    db.log_audit(req.query, jur, classification.category, conf_score, False, retrieved)

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
        graph=dynamic_graph,
        tkdl_resemblance=tkdl_res,
        regulatory_checklist=reg_chk,
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


_LAST_GRAPH = None


@app.get("/api/graph")
def get_graph(query: str = None, jurisdiction_name: str = "India"):
    """Returns dynamic query-dependent knowledge graph (or the latest analyzed graph)."""
    global _LAST_GRAPH
    if query:
        jur = jurisdiction.resolve_jurisdiction(jurisdiction_name)
        input_lang = language.detect_language(query)
        ret_query = query
        if input_lang != "en":
            trans, ok = translate.translate_to_english(query, input_lang)
            ret_query = trans if (ok and trans.strip()) else language.fallback_normalize(query)
        cat_res = classifier.classify(ret_query)
        areas = jurisdiction.route_areas(ret_query, cat_res.category)
        retrieved = retrieval.retrieve([ret_query], jur, areas, top_k=4)
        return graph.build_dynamic_graph(query, cat_res.category, jur, retrieved, areas)

    if _LAST_GRAPH is not None:
        return _LAST_GRAPH

    default_sources = retrieval.retrieve(["patent classical Ayurvedic formulation"], "India", ["Patents"], top_k=3)
    return graph.build_dynamic_graph(
        query="Can this Ayurvedic formulation be patented?",
        category="Classical / Generic Medicine",
        jurisdiction_name="India",
        retrieved_sources=default_sources,
        applicable_areas=["Patents", "Traditional Knowledge"],
    )


# --- PAID SOURCE CONNECTOR & CONSENT LIFECYCLE ENDPOINTS ---

@app.get("/api/connectors")
def get_connectors():
    """Lists all registered paid data source connectors and consent state."""
    return connectors.list_connectors()


@app.post("/api/connectors/consent")
def grant_connector_consent(req: ConnectorGrantRequest):
    """Grants consent and establishes connection for a paid source connector."""
    return connectors.grant_consent(req.source_id, req.token, req.email)


@app.post("/api/connectors/revoke")
def revoke_connector_consent(req: ConnectorRevokeRequest):
    """Revokes consent for a paid source connector (enforces immediate fail-closed access)."""
    return connectors.revoke_consent(req.source_id)


@app.get("/api/connectors/data/{source_id}")
def fetch_paid_connector_data(source_id: str):
    """
    Fetches data from a paid source connector.
    FAILS CLOSED with HTTP 403 Forbidden if consent is revoked.
    """
    return connectors.check_access_or_fail_closed(source_id)


# --- PDF REPORT EXPORT ENDPOINT ---

@app.post("/api/export/pdf")
def export_pdf(req: PdfExportRequest):
    """Generates and streams a downloadable PDF report containing analysis results."""
    pdf_bytes = pdf_generator.generate_analysis_pdf(req.analysis_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=sutradhara_ip_report.pdf"},
    )


# --- LIVE EVALUATION BENCHMARK ENDPOINT ---

@app.post("/api/eval/benchmark")
def run_benchmark():
    """Executes the live 20-item evaluation benchmark against real system pipeline."""
    return eval_benchmark.run_live_benchmark()


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
