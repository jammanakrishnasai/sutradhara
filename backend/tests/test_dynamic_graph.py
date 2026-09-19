"""
Unit tests for Dynamic Knowledge Graph generation and RAG integration.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import graph, main, schemas, language, retrieval, classifier, jurisdiction


def test_dynamic_graph_varies_by_query_topic():
    # Query 1: Patent question
    query_a = "Can I patent a classical Ayurvedic formulation?"
    req_a = schemas.AnalyzeRequest(query=query_a, jurisdiction="India", language="en")
    resp_a = main.analyze(req_a)

    assert resp_a.graph is not None, "Response must include dynamic graph"
    graph_a = resp_a.graph
    nodes_a = {n["label"] for n in graph_a["nodes"]}
    types_a = {n["type"] for n in graph_a["nodes"]}

    assert "ProductCategory" in types_a
    assert "Classical / Generic Medicine" in nodes_a

    # Query 2: Nutraceutical / ABS question
    query_b = "I want to sell a herbal nutraceutical supplement made from ashwagandha as a health food."
    req_b = schemas.AnalyzeRequest(query=query_b, jurisdiction="India", language="en")
    resp_b = main.analyze(req_b)

    assert resp_b.graph is not None
    graph_b = resp_b.graph
    nodes_b = {n["label"] for n in graph_b["nodes"]}

    # Prove Query A and Query B produce DIFFERENT dynamic graph contexts
    assert nodes_a != nodes_b, "Different queries must retrieve different graph node sets"
    assert "Ayurveda-Aahar / Nutraceutical" in nodes_b


def test_dynamic_graph_preserves_jurisdiction_separation():
    query = "Can I patent a classical Ayurvedic formulation?"

    req_india = schemas.AnalyzeRequest(query=query, jurisdiction="India", language="en")
    resp_india = main.analyze(req_india)

    req_intl = schemas.AnalyzeRequest(query=query, jurisdiction="International", language="en")
    resp_intl = main.analyze(req_intl)

    nodes_india = str(resp_india.graph["nodes"])
    nodes_intl = str(resp_intl.graph["nodes"])

    assert resp_india.graph["jurisdiction"] == "India"
    assert resp_intl.graph["jurisdiction"] == "International"
    assert "The Patents Act, 1970" in nodes_india
    assert "The Patents Act, 1970" not in nodes_intl


def test_get_graph_endpoint_query_param():
    g_patent = main.get_graph(query="Can I patent an Ayurvedic product?", jurisdiction_name="India")
    g_nutra = main.get_graph(query="I want to sell a herbal nutraceutical supplement as a health food.", jurisdiction_name="India")

    assert g_patent["nodes"] != g_nutra["nodes"]
