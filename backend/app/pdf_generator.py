"""
PDF Report Generator for SUTRADHARA.

Generates a downloadable PDF report containing:
- Product Analysis Summary
- TKDL Resemblance Score & Risk Band
- Regulatory Pathway Checklist Status
- Authoritative Evidence & Citations
"""
import io
from typing import Dict, Any

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False


def generate_analysis_pdf(analysis_data: Dict[str, Any]) -> bytes:
    """
    Generates PDF bytes for the given analysis response dictionary.
    """
    if _REPORTLAB_AVAILABLE:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=18,
            textColor=colors.HexColor("#1F3B2C"),
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "SubTitle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#8F6A22"),
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            "SectionHeader",
            parent=styles["Heading2"],
            fontSize=12,
            textColor=colors.HexColor("#1F3B2C"),
            spaceBefore=10,
            spaceAfter=6,
        )
        body_style = ParagraphStyle("BodyTextCustom", parent=styles["Normal"], fontSize=9, spaceAfter=4)

        elements = []

        # Header
        elements.append(Paragraph("SUTRADHARA — IP & Regulatory Intelligence Report", title_style))
        elements.append(Paragraph("Built for Ministry of AYUSH & All India Institute of Ayurveda", subtitle_style))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1F3B2C"), spaceAfter=10))

        # Query & Classification Summary
        query_text = str(analysis_data.get("query", "N/A"))
        classification = analysis_data.get("classification", {})
        category = classification.get("category", "N/A") if isinstance(classification, dict) else getattr(classification, "category", "N/A")
        jurisdiction = str(analysis_data.get("jurisdiction", "India"))
        confidence = float(analysis_data.get("confidence", 0.0))

        summary_table_data = [
            [Paragraph("<b>Product Query:</b>", body_style), Paragraph(query_text, body_style)],
            [Paragraph("<b>Product Category:</b>", body_style), Paragraph(category, body_style)],
            [Paragraph("<b>Jurisdiction:</b>", body_style), Paragraph(jurisdiction, body_style)],
            [Paragraph("<b>Evidence Confidence:</b>", body_style), Paragraph(f"{confidence * 100:.1f}%", body_style)],
        ]
        t = Table(summary_table_data, colWidths=[130, 410])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FAF7EF')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#EAE0C4')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#1F3B2C')),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 10))

        # TKDL Resemblance Score Section
        elements.append(Paragraph("1. TKDL Resemblance Scoring", heading_style))
        tkdl = analysis_data.get("tkdl_resemblance") or {}
        score = tkdl.get("score", 0.0)
        risk_label = tkdl.get("risk_label", "Low Prior-Art Overlap")
        matched_terms = ", ".join(tkdl.get("matched_terms", [])) or "None"

        tkdl_data = [
            [Paragraph("<b>Resemblance Score:</b>", body_style), Paragraph(f"<b>{score}%</b> ({risk_label})", body_style)],
            [Paragraph("<b>Matched Terms:</b>", body_style), Paragraph(matched_terms, body_style)],
        ]
        t_tkdl = Table(tkdl_data, colWidths=[130, 410])
        t_tkdl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FFFDF9')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#EAE0C4')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#8F6A22')),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        elements.append(t_tkdl)
        elements.append(Spacer(1, 10))

        # Regulatory Pathway Checklist Section
        elements.append(Paragraph("2. Regulatory Pathway Checklist", heading_style))
        chk = analysis_data.get("regulatory_checklist") or {}
        chk_items = chk.get("items", [])
        progress_pct = chk.get("progress_percentage", 0.0)

        elements.append(Paragraph(f"<b>Checklist Progress: {progress_pct}%</b>", body_style))
        chk_table_data = [[Paragraph("<b>Checklist Item</b>", body_style), Paragraph("<b>Authority</b>", body_style), Paragraph("<b>Status</b>", body_style)]]
        for item in chk_items:
            chk_table_data.append([
                Paragraph(str(item.get("title", "")), body_style),
                Paragraph(str(item.get("authority", "")), body_style),
                Paragraph(f"<b>{item.get('status', '')}</b>", body_style),
            ])

        t_chk = Table(chk_table_data, colWidths=[240, 200, 100])
        t_chk.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1F3B2C')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#EAE0C4')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#1F3B2C')),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        elements.append(t_chk)
        elements.append(Spacer(1, 10))

        # Grounded Answer Text
        elements.append(Paragraph("3. AI Legal & Regulatory Assessment", heading_style))
        ans_text = str(analysis_data.get("answer", "No answer generated."))
        elements.append(Paragraph(ans_text.replace("\n", "<br/>"), body_style))
        elements.append(Spacer(1, 10))

        # Disclaimer Footer
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#8F6A22'), spaceAfter=6))
        elements.append(Paragraph("<i>Disclaimer: Information provided for intelligence and regulatory reference, not formal legal advice.</i>", ParagraphStyle("Footer", parent=body_style, fontSize=8, textColor=colors.gray)))

        doc.build(elements)
        return buffer.getvalue()

    else:
        # Fallback PDF generator stream if reportlab is not installed
        pdf_str = f"%PDF-1.4\n% SUTRADHARA PDF Export Report\n"
        pdf_str += f"Query: {analysis_data.get('query')}\n"
        pdf_str += f"Category: {analysis_data.get('classification', {}).get('category') if isinstance(analysis_data.get('classification'), dict) else 'N/A'}\n"
        pdf_str += f"TKDL Resemblance Score: {analysis_data.get('tkdl_resemblance', {}).get('score')}%\n"
        pdf_str += f"Answer: {analysis_data.get('answer')}\n"
        return pdf_str.encode("utf-8")
