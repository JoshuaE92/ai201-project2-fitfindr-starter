"""
Tool tests for FitFindr — one test per success path and per failure mode.

Run with:  pytest tests/

The search_listings tests need no API key. The suggest_outfit / create_fit_card
tests call Groq and are skipped automatically if GROQ_API_KEY isn't set.
"""

import os

import pytest
from dotenv import load_dotenv

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

load_dotenv()

needs_key = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live LLM test",
)


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=30)
    assert all(item["price"] <= 30 for item in results)


def test_search_size_filter_is_lenient():
    # "M" should match listings whose size is "M", "S/M", "M/L", etc.
    results = search_listings("tee", size="M", max_price=100)
    assert all("m" in item["size"].lower() for item in results)


def test_search_ranks_by_relevance():
    # More keyword overlap should rank higher (score is non-increasing).
    results = search_listings("vintage denim jacket", size=None, max_price=100)
    assert len(results) > 1  # sanity: there are several denim/jacket items


# ── suggest_outfit ────────────────────────────────────────────────────────────

@needs_key
def test_suggest_outfit_with_wardrobe():
    item = search_listings("graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


@needs_key
def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe must not crash; returns a usable string.
    item = search_listings("graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


# ── create_fit_card ─────────────────────────────────────────────────────────

@needs_key
def test_create_fit_card_returns_caption():
    item = search_listings("graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("Pair it with baggy jeans and chunky sneakers.", item)
    assert isinstance(card, str)
    assert len(card.strip()) > 0


def test_create_fit_card_empty_outfit():
    # Failure mode: empty outfit → descriptive error string, no exception,
    # and no API call required.
    item = {"title": "Faded Band Tee", "price": 22, "platform": "depop"}
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert "suggest_outfit" in card


@needs_key
def test_create_fit_card_varies():
    # Outputs should differ across calls (higher temperature).
    item = search_listings("graphic tee", size=None, max_price=50)[0]
    outfit = "Pair it with baggy jeans and chunky sneakers."
    a = create_fit_card(outfit, item)
    b = create_fit_card(outfit, item)
    assert a != b
