"""
Input-language detection + fallback query normalization.

This is the missing piece in the pipeline: previously `language` on
AnalyzeRequest only controlled *output* translation. The query text itself
was passed straight into classify()/route_areas()/retrieve(), all of which
only understand English keywords/tokens. For a Telugu query that meant a
guaranteed zero-relevance retrieval (see retrieval.py docstring for the
mechanism), regardless of how good the underlying corpus match actually was.

detect_language() looks at the query text itself (Unicode script), not a
UI toggle or browser locale, per the "use the actual query text" requirement.

fallback_normalize() is a small, explicit second line of defense: if the real
translator (translate.translate_to_english) is unavailable or fails, we still
want *some* English signal for retrieval rather than silently returning
nothing. It is intentionally tiny and is never used to author legal claims —
only to help the TF-IDF retriever match on domain terms.
"""
import re

_TELUGU_RANGE = re.compile(r"[\u0C00-\u0C7F]")
_TAMIL_RANGE = re.compile(r"[\u0B80-\u0BFF]")
_MALAYALAM_RANGE = re.compile(r"[\u0D00-\u0D7F]")
_DEVANAGARI_RANGE = re.compile(r"[\u0900-\u097F]")

# Sanskrit-specific grammatical markers / terms used to distinguish Sanskrit from Hindi in Devanagari script.
_SANSKRIT_PATTERNS = [
    re.compile(r"स्य\b"),
    re.compile(r"तुम्\b|तुं\b"),
    re.compile(r"\bअस्य\b|\bतस्य\b|\bकस्य\b|\bएतस्य\b"),
    re.compile(r"\bकिम्\b|\bकथम्\b|\bकुत्र\b|\bकदा\b"),
    re.compile(r"\bशक्यते\b|\bअस्ति\b|\bभवति\b|\bवर्तते\b|\bइति\b"),
    re.compile(r"भ्याम्\b|णाम्\b|याः\b"),
]


def _is_sanskrit(text: str) -> bool:
    """Return True if Devanagari text contains Sanskrit-specific grammatical patterns or words."""
    for pattern in _SANSKRIT_PATTERNS:
        if pattern.search(text):
            return True
    return False


def detect_language(text: str) -> str:
    """Detect input language from the query text itself.

    Telugu (te), Tamil (ta), Malayalam (ml), Hindi (hi), Sanskrit (sa), and English (en)
    are distinguished by Unicode script and targeted Sanskrit heuristics.
    """
    if text:
        if _TELUGU_RANGE.search(text):
            return "te"
        if _TAMIL_RANGE.search(text):
            return "ta"
        if _MALAYALAM_RANGE.search(text):
            return "ml"
        if _DEVANAGARI_RANGE.search(text):
            if _is_sanskrit(text):
                return "sa"
            return "hi"
    return "en"


# Small, explicit term glossary — used ONLY as a fallback normalization
# strategy when live translation is unavailable (see main.py). NOT a
# replacement for real translation, and NOT applied to the corpus or to
# anything shown to the user.
TELUGU_TERM_MAP = {
    "పేటెంట్": "patent",
    "సాంప్రదాయ జ్ఞానం": "traditional knowledge",
    "ఆయుర్వేదం": "Ayurveda",
    "ఆయుర్వేద": "Ayurvedic",
    "శాస్త్రీయ": "classical",
    "ఫార్ములేషన్": "formulation",
    "జీవ వనరులు": "biological resources",
    "ప్రయోజన భాగస్వామ్యం": "access and benefit sharing",
    "గ్రంథం": "text",
    "సంప్రదాయ": "traditional",
}

HINDI_TERM_MAP = {
    "पेटेंट": "patent",
    "पारंपरिक ज्ञान": "traditional knowledge",
    "आयुर्वेदिक": "Ayurvedic",
    "आयुर्वेद": "Ayurveda",
    "शास्त्रीय": "classical",
    "फॉर्मूलेशन": "formulation",
    "जैविक संसाधन": "biological resources",
    "लाभ साझा करना": "access and benefit sharing",
    "ग्रंथ": "text",
    "पारंपरिक": "traditional",
}

TAMIL_TERM_MAP = {
    "காப்புரிமை": "patent",
    "தயாரிப்புக்கு": "product",
    "தயாரிப்பு": "product formulation",
    "ஆயுர்వేத": "Ayurvedic",
    "ஆயுர்வேதம்": "Ayurveda",
    "பாரம்பரிய அறிவு": "traditional knowledge",
    "பாரம்பரிய": "traditional",
    "உயிரியல் வளங்கள்": "biological resources",
    "சட்டம்": "law",
    "நூல்": "text",
}

MALAYALAM_TERM_MAP = {
    "പേറ്റന്റ്": "patent",
    "ഉൽപ്പന്നത്തിന്": "product",
    "ഉൽപ്പന്നം": "product formulation",
    "ആയുർവേദ": "Ayurvedic",
    "ആയുർവേദം": "Ayurveda",
    "പാരമ്പര്യ അറിവ്": "traditional knowledge",
    "പാരമ്പര്യ": "traditional",
    "ജൈവ വിഭവങ്ങൾ": "biological resources",
    "നിയമം": "law",
    "ഗ്രന്ഥം": "text",
}

SANSKRIT_TERM_MAP = {
    "पेटेण्ट्": "patent",
    "उत्पादस्य": "product formulation",
    "उत्पाद": "product",
    "आयुर्वेदिक": "Ayurvedic",
    "आयुर्वेद": "Ayurveda",
    "पारम्परिक-ज्ञानम्": "traditional knowledge",
    "पारम्परिक": "traditional",
    "ज्ञानम्": "knowledge",
    "शास्त्रीय": "classical",
    "ग्रन्थस्य": "text",
    "ग्रन्थ": "text",
}


def fallback_normalize(text: str) -> str:
    """Best-effort English gloss built by substring term substitution.

    Used only when the real translator call fails/is offline. Strips any
    remaining non-Latin characters afterward so leftover native text can't
    silently zero out the TF-IDF tokenizer again.
    """
    out = text
    for term_map in (TELUGU_TERM_MAP, HINDI_TERM_MAP, TAMIL_TERM_MAP, MALAYALAM_TERM_MAP, SANSKRIT_TERM_MAP):
        for source_term, en_term in term_map.items():
            out = out.replace(source_term, f" {en_term} ")
    out = re.sub(r"[^\x00-\x7F]+", " ", out)
    return re.sub(r"\s+", " ", out).strip()
