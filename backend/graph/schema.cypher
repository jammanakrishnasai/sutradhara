// SUTRADHARA — Neo4j knowledge graph schema + seed data (Phase 6)
// Run with: cat schema.cypher | cypher-shell -u neo4j -p <password>

// --- Constraints -----------------------------------------------------------
CREATE CONSTRAINT product_category_name IF NOT EXISTS FOR (c:ProductCategory) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT ip_regime_name IF NOT EXISTS FOR (r:IPRegime) REQUIRE r.name IS UNIQUE;
CREATE CONSTRAINT law_title IF NOT EXISTS FOR (l:Law) REQUIRE l.title IS UNIQUE;
CREATE CONSTRAINT source_id IF NOT EXISTS FOR (s:Source) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT jurisdiction_name IF NOT EXISTS FOR (j:Jurisdiction) REQUIRE j.name IS UNIQUE;

// --- Jurisdictions -----------------------------------------------------------
MERGE (:Jurisdiction {name: "India"});
MERGE (:Jurisdiction {name: "International"});

// --- Product categories -----------------------------------------------------
MERGE (:ProductCategory {name: "Classical / Generic Medicine"});
MERGE (:ProductCategory {name: "Patent / Proprietary Medicine"});
MERGE (:ProductCategory {name: "New / Non-Classical Drug"});
MERGE (:ProductCategory {name: "Phytopharmaceutical"});
MERGE (:ProductCategory {name: "Ayurveda-Aahar / Nutraceutical"});
MERGE (:ProductCategory {name: "Cosmetic"});

// --- IP / regulatory regimes --------------------------------------------------
MERGE (:IPRegime {name: "Patents"});
MERGE (:IPRegime {name: "Traditional Knowledge"});
MERGE (:IPRegime {name: "Access-and-Benefit-Sharing"});
MERGE (:IPRegime {name: "Drug regulation"});
MERGE (:IPRegime {name: "Food / nutraceutical regulation"});
MERGE (:IPRegime {name: "Geographical Indications"});
MERGE (:IPRegime {name: "Cosmetic regulation"});

// --- Laws / treaties ---------------------------------------------------------
MERGE (:Law {title: "The Patents Act, 1970"});
MERGE (:Law {title: "The Biological Diversity Act, 2002"});
MERGE (:Law {title: "The Drugs and Cosmetics Act, 1940 and Rules, 1945"});
MERGE (:Law {title: "WTO Agreement on TRIPS"});
MERGE (:Law {title: "Convention on Biological Diversity"});
MERGE (:Law {title: "Nagoya Protocol"});

// --- Example relationships: Classical / Generic Medicine (India) ------------
MATCH (cat:ProductCategory {name: "Classical / Generic Medicine"})
MATCH (regime1:IPRegime {name: "Patents"})
MATCH (regime2:IPRegime {name: "Traditional Knowledge"})
MERGE (cat)-[:relevant_to]->(regime1)
MERGE (cat)-[:relevant_to]->(regime2);

MATCH (regime:IPRegime {name: "Patents"})
MATCH (law:Law {title: "The Patents Act, 1970"})
MERGE (regime)-[:governed_by]->(law);

MATCH (law:Law {title: "The Patents Act, 1970"})
MERGE (p1:Provision {section: "Section 3(p)"})
MERGE (law)-[:contains]->(p1);

MATCH (p1:Provision {section: "Section 3(p)"})
MERGE (src:Source {id: "IN-PAT-3P", title: "The Patents Act, 1970"})
MERGE (p1)-[:supported_by]->(src);

// --- Node label reference (for driving the /api/graph visualization) --------
// (Product) -[:belongs_to]-> (ProductCategory)
// (ProductCategory) -[:relevant_to]-> (IPRegime)
// (IPRegime) -[:governed_by]-> (Law)
// (Law) -[:contains]-> (Provision)
// (Provision) -[:supported_by]-> (Source)
// (Product) -[:may_involve]-> (BiologicalResource)
// (BiologicalResource) -[:may_trigger]-> (ABS:IPRegime)
// (TraditionalKnowledge) -[:referenced_by]-> (TKDL:Source)
// (Jurisdiction) -[:governs]-> (IPRegime)
