"""
Unit tests for Multilingual Fixed Phrase-Template Matcher (Step C).
"""
import pytest
from backend.services.copilot.multilingual_matcher import multilingual_matcher
from backend.services.copilot.chat_engine import chat_engine


def test_hindi_clothing_color_search():
    res = multilingual_matcher.match_query("10 baje ke baad laal shirt wala aadmi")
    assert res["matched"] is True
    assert res["category"] == "person_clothing_search"
    assert "red" in res["normalized_english_query"]
    assert "shirt" in res["normalized_english_query"]


def test_gujarati_clothing_color_search():
    res = multilingual_matcher.match_query("10 vagya pachhi safed shirt valo manas")
    assert res["matched"] is True
    assert res["category"] == "person_clothing_search"
    assert "white" in res["normalized_english_query"]
    assert "shirt" in res["normalized_english_query"]


def test_hindi_vehicle_plate_search():
    res = multilingual_matcher.match_query("gaadi number DL01AB1234")
    assert res["matched"] is True
    assert res["category"] == "vehicle_plate"
    assert "DL01AB1234" in res["normalized_english_query"]


def test_gujarati_vehicle_search():
    res = multilingual_matcher.match_query("lal gadi shodho")
    assert res["matched"] is True
    assert res["category"] == "vehicle_search"
    assert "red" in res["normalized_english_query"]
    assert "car" in res["normalized_english_query"]


def test_hindi_missing_person_search():
    res = multilingual_matcher.match_query("gumshuda vyakti Vikram khojo")
    assert res["matched"] is True
    assert res["category"] == "missing_person"
    assert "vikram" in res["normalized_english_query"].lower()


def test_gujarati_missing_person_search():
    res = multilingual_matcher.match_query("gum thayel manas shodho")
    assert res["matched"] is True
    assert res["category"] == "missing_person"
    assert "missing person" in res["normalized_english_query"]


def test_out_of_pattern_query_returns_graceful_guidance():
    # Out of pattern query (e.g. philosophical or random sentence in Hindi)
    res = multilingual_matcher.match_query("aaj mausam kaisa hai aur kya chal raha hai")
    assert res["matched"] is False
    assert "error_message" in res
    assert "भाषा पैटर्न समर्थित नहीं है" in res["error_message"]


def test_copilot_end_to_end_multilingual_handling():
    # In-pattern Hindi query
    resp1 = chat_engine.process_text_query("gaadi number DL01AB1234")
    assert resp1 is not None
    assert "text" in resp1

    # Out-of-pattern Hindi query
    resp2 = chat_engine.process_text_query("kya chal raha hai yaha par batao bhai")
    assert resp2 is not None
    assert "भाषा पैटर्न समर्थित नहीं है" in resp2.get("text", "") or "कृपया समर्थित" in resp2.get("text", "")
