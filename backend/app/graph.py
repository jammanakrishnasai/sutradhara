"""
Dynamic Knowledge Graph Builder.

Constructs query-dependent knowledge graph representations (nodes & edges)
from user queries, product categories, jurisdictions, governing laws, legal provisions,
and RAG retrieved sources.

Supports live Neo4j Cypher querying if configured (via NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD),
and automatically falls back to RAG corpus dynamic graph construction if Neo4j is offline or unavailable.
"""
import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ip_sakti.graph")

# Optional Neo4j driver
try:
    from neo4j import GraphDatabase
    _NEO4J_AVAILABLE = True
except ImportError:
    _NEO4J_AVAILABLE = False


def _query_neo4j_graph(query: str, category: str, jurisdiction_name: str) -> Optional[Dict[str, Any]]:
    """Try querying live Neo4j database if configured."""
    if not _NEO4J_AVAILABLE:
        return None
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")

    if not uri or not password:
        return None

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            cypher = """
            MATCH (c:ProductCategory {name: $category})-[:relevant_to]->(r:IPRegime)-[:governed_by]->(l:Law)-[:contains]->(p:Provision)-[:supported_by]->(s:Source)
            RETURN c, r, l, p, s LIMIT 10
            """
            result = session.run(cypher, category=category)
            records = list(result)
            if not records:
                driver.close()
                return None

            nodes = []
            edges = []
            seen_nodes = set()

            for rec in records:
                c_node = rec["c"]
                r_node = rec["r"]
                l_node = rec["l"]
                p_node = rec["p"]
                s_node = rec["s"]

                if "cat" not in seen_nodes:
                    nodes.append({"id": "category", "label": c_node.get("name", category), "type": "ProductCategory"})
                    seen_nodes.add("cat")

                reg_id = f"regime_{r_node.get('name', 'regime')}"
                if reg_id not in seen_nodes:
                    nodes.append({"id": reg_id, "label": r_node.get("name", "IP Regime"), "type": "IPRegime"})
                    seen_nodes.add(reg_id)
                    edges.append({"from": "category", "to": reg_id, "label": "relevant_to"})

                law_id = f"law_{l_node.get('title', 'law')}"
                if law_id not in seen_nodes:
                    nodes.append({"id": law_id, "label": l_node.get("title", "Law"), "type": "Law"})
                    seen_nodes.add(law_id)
                    edges.append({"from": reg_id, "to": law_id, "label": "governed_by"})

                prov_id = f"prov_{p_node.get('section', 'prov')}"
                if prov_id not in seen_nodes:
                    nodes.append({"id": prov_id, "label": p_node.get("section", "Provision"), "type": "Provision"})
                    seen_nodes.add(prov_id)
                    edges.append({"from": law_id, "to": prov_id, "label": "contains"})

                src_id = f"src_{s_node.get('id', 'src')}"
                if src_id not in seen_nodes:
                    nodes.append({"id": src_id, "label": s_node.get("id", "Source"), "type": "Source"})
                    seen_nodes.add(src_id)
                    edges.append({"from": prov_id, "to": src_id, "label": "supported_by"})

            driver.close()
            return {
                "nodes": nodes,
                "edges": edges,
                "note": f"Live Cypher graph retrieved from Neo4j for {category} in {jurisdiction_name}.",
                "source": "neo4j",
            }
    except Exception as e:
        logger.warning(f"Neo4j query failed: {e}. Falling back to dynamic RAG graph.")
        return None


def build_dynamic_graph(
    query: str,
    category: str,
    jurisdiction_name: str,
    retrieved_sources: List[Dict[str, Any]],
    applicable_areas: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Builds a query-dependent dynamic knowledge graph representation.

    Nodes represent:
    - Product / Query Topic
    - Product Category
    - Relevant IP Regimes
    - Governing Laws
    - Legal Provisions / Sections
    - Authoritative Sources

    Edges represent relationship types:
    - belongs_to, relevant_to, governed_by, contains, supported_by
    """
    # 1. Try Neo4j if configured
    neo4j_graph = _query_neo4j_graph(query, category, jurisdiction_name)
    if neo4j_graph:
        return neo4j_graph

    # 2. Dynamic RAG Graph Builder
    nodes = []
    edges = []

    # Node 1: Product / Query Context
    short_query = query.strip()
    if len(short_query) > 35:
        short_query = short_query[:32] + "..."

    product_node_id = "product"
    nodes.append({
        "id": product_node_id,
        "label": short_query or "Ayurvedic Query",
        "type": "Product",
        "category": "Query Context",
    })

    # Node 2: ProductCategory
    category_label = category if category and category != "n/a" else "General IP Query"
    cat_node_id = "category"
    nodes.append({
        "id": cat_node_id,
        "label": category_label,
        "type": "ProductCategory",
        "category": "Product Category",
    })

    edges.append({
        "from": product_node_id,
        "to": cat_node_id,
        "label": "belongs_to",
    })

    # Node 3: IP Regimes
    regime_ids = []
    areas_to_use = list(applicable_areas) if applicable_areas else []

    if retrieved_sources:
        for src in retrieved_sources:
            domain = src.get("domain")
            if domain and domain not in areas_to_use:
                areas_to_use.append(domain)

    if not areas_to_use:
        areas_to_use = ["Patents", "Traditional Knowledge"]

    for idx, area in enumerate(areas_to_use[:3]):
        reg_id = f"regime_{idx+1}"
        nodes.append({
            "id": reg_id,
            "label": area,
            "type": "IPRegime",
            "category": "IP Regime",
        })
        edges.append({
            "from": cat_node_id,
            "to": reg_id,
            "label": "relevant_to",
        })
        regime_ids.append(reg_id)

    # Node 4: Laws, Provisions, and Sources from retrieved sources
    law_map = {}      # title -> node_id
    prov_map = {}     # section -> node_id
    source_map = {}   # src_id -> node_id

    if retrieved_sources:
        for idx, src in enumerate(retrieved_sources[:4]):
            law_title = src.get("title", "Governing Law")
            section = src.get("section", f"Section {idx+1}")
            src_id_val = src.get("id", f"SRC-{idx+1}")

            # Law node
            if law_title not in law_map:
                law_node_id = f"law_{len(law_map)+1}"
                law_map[law_title] = law_node_id
                nodes.append({
                    "id": law_node_id,
                    "label": law_title,
                    "type": "Law",
                    "category": "Governing Law",
                })
                target_regime = regime_ids[0] if regime_ids else cat_node_id
                edges.append({
                    "from": target_regime,
                    "to": law_node_id,
                    "label": "governed_by",
                })
            else:
                law_node_id = law_map[law_title]

            # Provision node
            prov_key = f"{law_title}::{section}"
            if prov_key not in prov_map:
                prov_node_id = f"provision_{len(prov_map)+1}"
                prov_map[prov_key] = prov_node_id
                nodes.append({
                    "id": prov_node_id,
                    "label": section,
                    "type": "Provision",
                    "category": "Provision",
                })
                edges.append({
                    "from": law_node_id,
                    "to": prov_node_id,
                    "label": "contains",
                })
            else:
                prov_node_id = prov_map[prov_key]

            # Source node
            if src_id_val not in source_map:
                src_node_id = f"source_{len(source_map)+1}"
                source_map[src_id_val] = src_node_id
                nodes.append({
                    "id": src_node_id,
                    "label": src_id_val,
                    "type": "Source",
                    "category": "Authoritative Source",
                })
                edges.append({
                    "from": prov_node_id,
                    "to": src_node_id,
                    "label": "supported_by",
                })

    else:
        # Fallback law & provision node for queries where evidence set is empty
        if jurisdiction_name == "International":
            law_title = "WTO Agreement on TRIPS"
            section = "Article 27"
            src_code = "INT-TRIPS-27"
        else:
            law_title = "The Patents Act, 1970"
            section = "Section 3(p)"
            src_code = "IN-PAT-3P"

        law_node_id = "law_1"
        prov_node_id = "provision_1"
        src_node_id = "source_1"

        nodes.append({"id": law_node_id, "label": law_title, "type": "Law", "category": "Governing Law"})
        nodes.append({"id": prov_node_id, "label": section, "type": "Provision", "category": "Provision"})
        nodes.append({"id": src_node_id, "label": src_code, "type": "Source", "category": "Authoritative Source"})

        target_regime = regime_ids[0] if regime_ids else cat_node_id
        edges.append({"from": target_regime, "to": law_node_id, "label": "governed_by"})
        edges.append({"from": law_node_id, "to": prov_node_id, "label": "contains"})
        edges.append({"from": prov_node_id, "to": src_node_id, "label": "supported_by"})

    note = f"Dynamic knowledge graph generated for '{short_query}' ({category_label}) in {jurisdiction_name} jurisdiction."

    return {
        "nodes": nodes,
        "edges": edges,
        "note": note,
        "jurisdiction": jurisdiction_name,
        "source": "dynamic_rag",
    }
