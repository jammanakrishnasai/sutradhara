"""
Tests for the optional Groq paraphrase layer (app/llm.py).

These tests never make a real network call to api.groq.com — they verify
the fail-safe contract: with no API key configured (the default in this
repo's checked-in .env), paraphrase_answer() must return the input
unchanged, and the citation-preservation checker must correctly accept/
reject candidate outputs.
"""
import importlib

from app import llm


def test_paraphrase_is_noop_without_api_key(monkeypatch):
    monkeypatch.setattr(llm, "GROQ_API_KEY", "")
    text = "(1) Some grounded sentence. [Source: The Patents Act, 1970, Section 3(p)]"
    result, used_llm = llm.paraphrase_answer(text)
    assert result == text
    assert used_llm is False


def test_paraphrase_disabled_flag_is_noop(monkeypatch):
    monkeypatch.setattr(llm, "GROQ_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(llm, "_ENABLED", False)
    text = "(1) Some grounded sentence. [Source: The Patents Act, 1970, Section 3(p)]"
    result, used_llm = llm.paraphrase_answer(text)
    assert result == text
    assert used_llm is False


def test_citations_preserved_accepts_reordered_identical_tags():
    original = (
        "(1) First point. [Source: A Act, 1970, Section 3(p)]\n\n"
        "(2) Second point. [Source: B Act, 2002, Section 5]"
    )
    candidate = (
        "Second point restated first. [Source: B Act, 2002, Section 5] "
        "Then the first point. [Source: A Act, 1970, Section 3(p)]"
    )
    assert llm._citations_preserved(original, candidate) is True


def test_citations_preserved_rejects_altered_citation():
    original = "Point one. [Source: A Act, 1970, Section 3(p)]"
    candidate = "Point one, reworded. [Source: A Act, 1970, Section 3(z)]"
    assert llm._citations_preserved(original, candidate) is False


def test_citations_preserved_rejects_dropped_citation():
    original = (
        "Point one. [Source: A Act, 1970, Section 3(p)]\n\n"
        "Point two. [Source: B Act, 2002, Section 5]"
    )
    candidate = "Both points combined into one sentence. [Source: A Act, 1970, Section 3(p)]"
    assert llm._citations_preserved(original, candidate) is False


def test_citations_preserved_rejects_when_original_has_no_citations():
    # An empty original citation set should never "trivially pass" —
    # guards against a future caller passing already-abstained/empty text.
    original = "No citations here at all."
    candidate = "No citations here at all, rephrased."
    assert llm._citations_preserved(original, candidate) is False
