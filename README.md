# FitFindr 🛍️

FitFindr is an agent that takes a shopper's natural-language request for a secondhand
clothing item, finds a matching listing, styles it against the user's existing wardrobe,
and writes a short, post-ready caption ("fit card") for it.

It runs as a three-tool agent orchestrated by a planning loop, with a Gradio web UI.

---

## Setup

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

**Run the app:**
```bash
python app.py
```
Then open the URL shown in your terminal (usually http://localhost:7860).

**Run the tests:**
```bash
pytest tests/
```

**Trigger the failure modes (for the demo):**
```bash
python demo_failures.py
```

---

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── tools.py                   # The three tools
├── agent.py                   # Planning loop + session state
├── app.py                     # Gradio UI
├── tests/test_tools.py        # Per-tool success + failure tests
├── demo_failures.py           # Triggers all three failure modes
└── planning.md                # Full design spec
```

The dataset (`data/listings.json`) holds 40 mock listings across categories (tops, bottoms,
outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear).
Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`,
`condition`, `price`, `colors`, `brand`, `platform`. The wardrobe
(`data/wardrobe_schema.json`) provides an `example_wardrobe` (10 items) and an
`empty_wardrobe` template, loaded via `get_example_wardrobe()` / `get_empty_wardrobe()`.

---

## Tool Inventory

These match the actual function signatures in `tools.py`.

### 1. `search_listings(description, size=None, max_price=None) -> list[dict]`

| | |
|---|---|
| **Purpose** | Find secondhand listings matching what the user described, filtered by size and price, ranked by relevance. |
| **Inputs** | `description` (`str`) — keywords, matched against each listing's `title`, `description`, and `style_tags`. `size` (`str \| None`) — size token (e.g. `"M"`); lenient match (counts if the token appears anywhere in the listing's `size`, so `"M"` matches `"S/M"`, `"M/L"`). `max_price` (`float \| None`) — inclusive price ceiling. |
| **Output** | `list[dict]` of matching listings in listings.json shape, sorted most-relevant first (higher keyword overlap ranks higher). Returns `[]` when nothing matches — never raises. |

### 2. `suggest_outfit(new_item, wardrobe) -> str`

| | |
|---|---|
| **Purpose** | Suggest how to style the selected item against the pieces the user already owns. Calls the Groq LLM (`llama-3.3-70b-versatile`). |
| **Inputs** | `new_item` (`dict`) — the selected listing (from `search_listings`). `wardrobe` (`dict`) — the user's closet in `wardrobe_schema.json` shape (`{"items": [...]}`); may be empty. |
| **Output** | `str` — a 1–2 sentence styling suggestion. With a wardrobe it names real owned pieces; with an empty wardrobe it describes the item as a standalone centerpiece (no invented garments). |

### 3. `create_fit_card(outfit, new_item) -> str`

| | |
|---|---|
| **Purpose** | Turn the item + styling suggestion into a casual, post-ready social caption. Calls the Groq LLM at a higher temperature so repeated calls vary. |
| **Inputs** | `outfit` (`str`) — the suggestion from `suggest_outfit`. `new_item` (`dict`) — the selected listing, used for `title` / `price` / `platform`. |
| **Output** | `str` — a 2–4 sentence first-person caption referencing the real item details. Only references clothing named in the `outfit` text — it does not invent garments. |

---

## Planning Loop

The agent's brain is `run_agent(query, wardrobe)` in `agent.py`. It runs the three tools
as a pipeline, but with **conditional branches** — it does not call all three tools
unconditionally.

1. **Parse the query.** `_parse_query()` uses regex to pull a `description`, an optional
   `size` (`"size M"`, `"size 8"`), and an optional `max_price` (`"under $30"`, `"$40"`)
   out of the natural-language request. The result is stored in `session["parsed"]`.
2. **Search.** Call `search_listings(description, size, max_price)`.
   - **Branch — no results:** if the list is empty, set `session["error"]` to a helpful
     message and **return early.** The agent does *not* call `suggest_outfit` or
     `create_fit_card` with empty input.
   - **Otherwise:** set `session["selected_item"] = results[0]` (the top-ranked match)
     and continue.
3. **Suggest an outfit.** Call `suggest_outfit(selected_item, wardrobe)`.
   - An **empty wardrobe is not an error** — the pipeline continues. The tool returns a
     single-item suggestion centered on the piece itself instead of referencing things
     the user doesn't own.
4. **Create the fit card.** Call `create_fit_card(outfit_suggestion, selected_item)`.
5. **Return the session.** Success = `fit_card` is set; early exit = `error` is set.

The key decision the agent makes is at step 2: **does the search return anything?** That
single branch is what makes the agent's behavior differ by input — a matchable query runs
all three tools, an impossible query stops after one.

---

## State Management

A single `session` dict (created by `_new_session()`) is the single source of truth for
one interaction. Each tool writes its output into a named key; the next tool reads the key
it needs. Nothing is re-asked of the user and nothing is hardcoded between steps.

| Key | Set by | Type | Read by |
|---|---|---|---|
| `query` | entry point | `str` | `_parse_query` |
| `parsed` | `_parse_query` | `dict` (`description`, `size`, `max_price`) | `search_listings` |
| `wardrobe` | entry point (`get_example_wardrobe` / `get_empty_wardrobe`) | `dict` | `suggest_outfit` |
| `search_results` | `search_listings` | `list[dict]` | branch check |
| `selected_item` | `= search_results[0]` | `dict` | `suggest_outfit`, `create_fit_card` |
| `outfit_suggestion` | `suggest_outfit` | `str` | `create_fit_card` |
| `fit_card` | `create_fit_card` | `str` | final output |
| `error` | no-results branch | `str` | final output (early return) |

**Flow:** search writes `selected_item` → suggest reads `selected_item` + `wardrobe`,
writes `outfit_suggestion` → fit card reads `outfit_suggestion` + `selected_item`, writes
`fit_card`. The *same* `selected_item` dict object flows into both downstream tools — this
was verified with identity (`is`) checks during testing.

---

## Interaction Walkthrough

**User query:** `"vintage graphic tee under $30, size M"` (with the example wardrobe)

**Step 1 — `search_listings`**
- Input: `description="vintage graphic tee"`, `size="M"`, `max_price=30.0` (parsed from the query)
- Why: the user is asking to find an item, so the agent searches first.
- Output: a ranked list of matches; the top result (`selected_item`) is the *Y2K Baby Tee — Butterfly Print* ($18, depop, size S/M).

**Step 2 — `suggest_outfit`**
- Input: `new_item=<Y2K Baby Tee>`, `wardrobe=<example wardrobe>` (the *same* item dict from Step 1)
- Why: a real item was found, so the agent styles it against the user's closet.
- Output: *"Pair the Y2K Baby Tee with the Baggy straight-leg jeans and Chunky white sneakers for a casual, streetwear-inspired look… or layer the Vintage black denim jacket over the tee for an edgier touch."*

**Step 3 — `create_fit_card`**
- Input: `outfit=<the suggestion above>`, `new_item=<Y2K Baby Tee>`
- Why: a complete outfit exists, so the agent writes a shareable caption.
- Output: *"Just scored this adorable Y2K Baby Tee with a butterfly print on Depop for $18 and I'm obsessed. I've been wearing it with my baggy straight-leg jeans and chunky white sneakers for a super relaxed, streetwear vibe…"*

**Final output to user:** all three UI panels populate — the listing, the outfit idea, and
the fit card. The item found in Step 1 is the same item styled in Step 2 and captioned in
Step 3; it is never re-entered.

---

## Error Handling and Fail Points

| Tool | Failure mode | Agent response |
|---|---|---|
| `search_listings` | No listing matches the query | Returns `[]`; the planning loop sets `session["error"]` and **stops** before calling the other tools. The user sees what failed and what to try. |
| `suggest_outfit` | Wardrobe is empty (new user) | Not treated as an error — the pipeline continues. The tool describes the item as a standalone centerpiece and avoids naming pieces the user doesn't own. |
| `create_fit_card` | `outfit` string is empty / missing | Returns a descriptive error string (no exception, no API call): *"Can't write a fit card without an outfit suggestion — run suggest_outfit first."* |

**Concrete example from testing — triggered no-results failure:**

Running the agent on `"designer ballgown size XXS under $5"`:
```
error           : No listings found for 'designer ballgown' in size XXS under $5.
                  Try raising the price, loosening the size, or using broader keywords.
selected_item    : None
outfit_suggestion: None
fit_card         : None
```
The agent searched, got zero matches, and returned early — `suggest_outfit` was **never
called** (verified by spying on the tool functions during testing). The response is
specific and actionable, not just "no results."

**A second issue found and fixed during testing:** with an empty wardrobe, the fit card
originally invented garments the user didn't own (e.g. "pastel pink shorts and a flowery
headband"). The LLM in `create_fit_card` was hallucinating state it was never given. Fixed
by (a) rewriting the empty-wardrobe prompt in `suggest_outfit` to describe only the item,
and (b) adding a guardrail to `create_fit_card` to only reference clothing named in the
`outfit` text. Verified across multiple runs that the caption now stays centered on the
single item.

---

## AI Usage

I used Claude (via Claude Code) to help implement and debug the agent. Two specific instances:

**1. Implementing the planning loop.** I gave Claude the **Planning Loop**, **State
Management**, and **Architecture** (agent diagram) sections of `planning.md` and asked it
to implement `run_agent()` against that spec. It produced the loop wiring the three tools
through the `session` dict. I reviewed it against my spec before running: I confirmed it
branched on the empty-search result (early return) rather than calling all three tools
unconditionally, and that the empty-wardrobe case did *not* terminate the pipeline. I also
added the regex query parser (`_parse_query`) myself, since the generated version didn't
extract `size`/`max_price` from natural language the way my spec described.

**2. Debugging the empty-wardrobe fit card.** When I tested the "new user" path in the UI,
the fit card described garments I didn't own. I gave Claude the actual misleading output
and both tool prompts and asked it to trace the cause. It identified that the
`create_fit_card` LLM was concretizing the generic suggestion into specific fake items. I
had it tighten both prompts (item-only suggestion + a "don't invent garments" guardrail),
then I re-ran the empty-wardrobe flow several times to confirm the caption stayed centered
on the one item before accepting the change.

---

## Spec Reflection

**One way `planning.md` helped during implementation:** Writing the State Management table
*before* coding meant the session dict had a defined contract — every tool knew exactly
which key it read and which it wrote. When I implemented `agent.py`, wiring the tools was
mechanical because the data flow was already decided; I just followed the table. It also
made the no-results branch obvious: the spec already said "set `error`, return early,"
so I didn't accidentally fall through into `suggest_outfit`.

**One divergence from the spec, and why:** My Tool 2 spec said the empty-wardrobe case
should "offer general styling advice… what kinds of pieces would pair well." In practice
that backfired — `create_fit_card` turned that generic advice into specific garments the
user didn't own, which was misleading for a new user. I diverged: the empty-wardrobe path
now describes *only the item itself* as a centerpiece and explicitly avoids suggesting
other pieces, and `create_fit_card` is guarded against inventing anything not in the
outfit text. The spec's instinct (handle empty gracefully) was right, but "general styling
advice" was the wrong shape for it.
