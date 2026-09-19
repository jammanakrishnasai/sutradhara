"""
Regulatory Pathway Checklist Builder.

Generates a dynamic, jurisdiction and category specific regulatory compliance
checklist for Ayurvedic / Phytopharmaceutical / Nutraceutical / Cosmetic products.
"""
from typing import List, Dict, Any


def build_regulatory_checklist(
    query: str,
    category: str,
    jurisdiction_name: str,
    retrieved_sources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Builds the regulatory pathway checklist and completion status.
    """
    query_lower = query.lower()
    sources_text = " ".join([s.get("title", "") + " " + s.get("section", "") for s in (retrieved_sources or [])]).lower()

    items = []

    # Item 1: Prior Art & TKDL Verification
    has_tk_evidence = "3(p)" in sources_text or "traditional knowledge" in sources_text or "tkdl" in sources_text
    items.append({
        "id": "prior_art_tkdl",
        "title": "TKDL & Classical Text Prior-Art Search",
        "description": "Verify whether the formulation or ingredients are documented in classical Ayurvedic texts or TKDL databases.",
        "status": "COMPLETED" if has_tk_evidence else "ACTION_REQUIRED",
        "required": True,
        "authority": "Indian Patent Office / TKDL Access Committee" if jurisdiction_name == "India" else "WIPO / International Patent Offices",
    })

    # Item 2: Access & Benefit Sharing (ABS) Clearance
    has_bio_resource = any(kw in query_lower for kw in ["herb", "plant", "forest", "extract", "biological", "biodiversity", "species", "ashwagandha"]) or "biological diversity" in sources_text
    items.append({
        "id": "abs_clearance",
        "title": "Biological Diversity Act / ABS Clearance (Form 1 / Form 3)",
        "description": "Determine whether commercialization of biological resources requires prior approval or benefit sharing.",
        "status": "ACTION_REQUIRED" if has_bio_resource else "RECOMMENDED",
        "required": has_bio_resource,
        "authority": "National Biodiversity Authority (NBA)" if jurisdiction_name == "India" else "National Competent Authority (Nagoya Protocol)",
    })

    # Item 3: Regulatory Category & Manufacturing Licensing
    if category == "Cosmetic":
        lic_title = "Cosmetics Rules, 2020 Manufacturing License"
        lic_auth = "Central Drugs Standard Control Organization (CDSCO) / State Licensing Authority"
    elif category == "Ayurveda-Aahar / Nutraceutical":
        lic_title = "FSSAI Safety & Standardization Clearance (Ayurveda-Aahar)"
        lic_auth = "Food Safety and Standards Authority of India (FSSAI)"
    elif category == "Phytopharmaceutical":
        lic_title = "New Drug Approval & Clinical Trial Data (Form 44)"
        lic_auth = "DCGI / CDSCO"
    else:
        lic_title = "Ayurvedic Manufacturing License (Form 25D / 25E)"
        lic_auth = "State AYUSH Licensing Authority / CDSCO"

    items.append({
        "id": "category_licensing",
        "title": lic_title,
        "description": f"Obtain necessary product approval and manufacturing license for category '{category or 'Ayurvedic Drug'}'.",
        "status": "RECOMMENDED",
        "required": True,
        "authority": lic_auth,
    })

    # Item 4: Patentability & Section 3(p) Evaluation
    is_classical = category == "Classical / Generic Medicine" or "classical" in query_lower
    items.append({
        "id": "patentability_section3p",
        "title": "Patentability & Non-Patentable Subject Matter Check (Section 3(p) / TRIPS Art. 27)",
        "description": "Ensure the claim is not a mere duplication or traditional knowledge aggregation.",
        "status": "COMPLETED" if is_classical else "ACTION_REQUIRED",
        "required": True,
        "authority": "Patent Examiner / IP Facilitator",
    })

    # Item 5: Labelling & Therapeutic Claim Verification
    items.append({
        "id": "labelling_claims",
        "title": "Labelling & Magic Remedies Claim Verification",
        "description": "Verify package labeling and advertising compliance under Drugs & Magic Remedies Act / Consumer Protection Rules.",
        "status": "RECOMMENDED",
        "required": True,
        "authority": "AYUSH / Advertising Standards Council of India (ASCI)",
    })

    completed_count = sum(1 for i in items if i["status"] == "COMPLETED")
    total_count = len(items)
    progress_pct = round((completed_count / total_count) * 100, 1)

    return {
        "items": items,
        "total_items": total_count,
        "completed_items": completed_count,
        "progress_percentage": progress_pct,
        "jurisdiction": jurisdiction_name,
        "category": category,
    }
