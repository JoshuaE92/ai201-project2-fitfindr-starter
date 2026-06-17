"""
demo_failures.py — Triggers all three FitFindr failure modes on purpose.

Run for your demo video / screenshot:
    python demo_failures.py

Each block deliberately breaks one tool and shows the graceful response
(no Python exceptions — specific, informative messages instead).
"""

from agent import run_agent
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


def line(title):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


# ── Failure 1: search returns zero results ──────────────────────────────────
line("FAILURE 1 — search_listings returns no matches")
results = search_listings("designer ballgown", size="XXS", max_price=5)
print(f"search_listings(...) -> {results}   (empty list, no exception)")

print("\nFull agent on the same impossible query:")
session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
print(f"  error           : {session['error']}")
print(f"  selected_item    : {session['selected_item']}")
print(f"  outfit_suggestion: {session['outfit_suggestion']}")
print(f"  fit_card         : {session['fit_card']}")


# ── Failure 2: suggest_outfit with an empty wardrobe ────────────────────────
line("FAILURE 2 — suggest_outfit with an empty wardrobe")
item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
suggestion = suggest_outfit(item, get_empty_wardrobe())
print(f"Item: {item['title']}")
print(f"suggest_outfit(item, empty_wardrobe) ->\n  {suggestion}")


# ── Failure 3: create_fit_card with an empty outfit string ──────────────────
line("FAILURE 3 — create_fit_card with an empty outfit string")
card = create_fit_card("", item)
print(f"create_fit_card('', item) ->\n  {card}")

print("\nAll three failure modes handled gracefully — no exceptions raised.\n")
