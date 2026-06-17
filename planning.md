# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (loaded with `load_listings()`) for secondhand items that match what the user described, then filters by size and price and returns the matches ranked by relevance.

**Input parameters:**
- `description` (str): free-text keywords describing the item the user wants (e.g. "vintage graphic tee"). Matched against each listing's `title`, `description`, and `style_tags`.
- `size` (str): the size the user needs (e.g. "M"). Filters out listings whose `size` field doesn't match. Sizing in the data is messy ("M", "S/M", "M/L", "W30"), so the match is lenient — a listing counts if the requested size token appears anywhere in its `size` string.
- `max_price` (float): the upper price limit. Filters out any listing whose `price` is greater than this value.

**What it returns:**
A `list[dict]` of matching listings in the **same shape as listings.json** (each dict has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`), sorted most-relevant first (more keyword/style-tag overlaps = higher rank). The planning loop uses `results[0]` as the selected item. Returns an empty list `[]` when nothing matches.

**What happens if it fails or returns nothing:**
Returns `[]` (it does not raise). The planning loop checks for the empty list, stores an error message in the session, and stops before calling `suggest_outfit` — it never passes empty input down the pipeline. (See Error Handling for the exact message.)

---

### Tool 2: suggest_outfit

**What it does:**
Takes the listing selected by `search_listings` and suggests how to style it against the pieces the user already owns. It builds a prompt from the new item plus the wardrobe and asks the model for a short, concrete styling tip (which pieces to pair, how to wear it).

**Input parameters:**
- `new_item` (dict): the listing chosen in Step 1 (`results[0]` from `search_listings`), in listings.json shape.
- `wardrobe` (dict): the user's closet in `wardrobe_schema.json` shape — a dict with an `items` key holding a list of wardrobe pieces (each has `id`, `name`, `category`, `colors`, `style_tags`, `notes`). May be empty (`{"items": []}`).

**What it returns:**
A styling suggestion as a `str` — one or two sentences naming specific wardrobe pieces to pair with the new item and how to wear it (e.g. "Pair this with your wide-leg jeans and platform boots for a 90s grunge look. Roll the sleeves once.").

**What happens if it fails or returns nothing:**
An **empty wardrobe is not a failure** — the pipeline continues. When `wardrobe["items"]` is empty, the tool returns a single-item suggestion that styles the new piece on its own (e.g. "Your closet's empty, so this band tee is your starting piece — wear it as the anchor of the fit") instead of referencing pieces the user doesn't own. The prompt is written to handle the "we only have this one item" case. The result still flows into `create_fit_card`. If the model returns nothing usable, the loop falls back to a generic suggestion built from the item's own `style_tags`/`colors` so Step 3 still has input.

---

### Tool 3: create_fit_card

**What it does:**
Turns the selected item and its styling suggestion into a short, casual social-media caption (a "fit card") the user could post — first-person, hyped, with the price/platform woven in.

**Input parameters:**
- `outfit` (str): the styling suggestion returned by `suggest_outfit`.
- `new_item` (dict): the selected listing, used to pull concrete details into the caption (`title`, `price`, `platform`, `condition`).

**What it returns:**
A `str` caption in social-post voice that must reference the actual item details (e.g. "thrifted this faded band tee off depop for $22 and it was made for my wide-legs 🖤"). It must produce something different for different inputs — the caption is generated from the specific item/outfit, not a fixed template.

**What happens if it fails or returns nothing:**
If `outfit` is missing/empty or `new_item` lacks key fields (`title`, `price`), the tool does not invent details. It returns a minimal caption built only from the fields that are present (e.g. just the title and platform), and the loop still completes. It never fabricates a price or wardrobe pieces that weren't passed in.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop runs the three tools as a fixed pipeline, but with conditional branches that can stop early or skip styling. It reads from and writes to a session dict at each step:

1. **Parse the query** → extract `description`, `size`, and `max_price` from the user's message. Store them in the session.
2. **Call `search_listings(description, size, max_price)`.**
   - If `results == []` → set `session["error"] = "No listings found..."`, **return early.** Do not call `suggest_outfit`.
   - Else → set `session["selected_item"] = results[0]` and continue.
3. **Call `suggest_outfit(selected_item, wardrobe)`.**
   - If `wardrobe["items"]` is empty → this is **not** an error. The tool returns a single-item suggestion; store it in `session["outfit_suggestion"]` and continue to Step 4 anyway (we still make a fit card for the one item).
   - Else → store the normal styling suggestion in `session["outfit_suggestion"]` and continue.
4. **Call `create_fit_card(outfit_suggestion, selected_item)`** → store the caption in `session["fit_card"]`.
5. **Done.** Return the session. The loop knows it's finished when `fit_card` is set (success) or when `error` is set (early return).

The only branch that terminates early is an empty search result. The empty-wardrobe branch changes *what* `suggest_outfit` produces but does **not** stop the pipeline.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict is created at the start of the interaction and passed through the loop. Each tool's output is written into a named key; the next tool reads the key it needs. No tool re-runs a previous step or re-reads raw input.

| Key | Set by | Type | Used by |
|-----|--------|------|---------|
| `query` / `description` / `size` / `max_price` | query parsing | str / str / str / float | `search_listings` |
| `wardrobe` | loaded at start via `get_example_wardrobe()` or `get_empty_wardrobe()` | dict | `suggest_outfit` |
| `selected_item` | `search_listings` (= `results[0]`) | dict | `suggest_outfit`, `create_fit_card` |
| `outfit_suggestion` | `suggest_outfit` | str | `create_fit_card` |
| `fit_card` | `create_fit_card` | str | final output to user |
| `error` | `search_listings` empty-result branch | str | final output (early return) |

Flow: search writes `selected_item` → suggest reads `selected_item` + `wardrobe`, writes `outfit_suggestion` → fit card reads `outfit_suggestion` + `selected_item`, writes `fit_card`. At the end the agent reads either `fit_card` (success) or `error` (early return) to decide what to show the user.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Stop the pipeline and tell the user exactly what blocked the match and what to change: "I couldn't find a vintage graphic tee in size M under $30. Want me to raise the budget to ~$40, open up the size (a lot of these run S/M or L), or try broader keywords like 'band tee'?" Does **not** call `suggest_outfit`. |
| suggest_outfit | Wardrobe is empty | Not treated as an error — the pipeline continues. The tool returns a single-item suggestion that styles the new piece on its own ("Your closet's empty, so this band tee is the anchor — build the fit around it") and that result flows into `create_fit_card` as normal. |
| create_fit_card | Outfit input is missing or incomplete | Generate a minimal caption from only the fields that are present (e.g. `title` + `platform` + `price` if available). Never fabricate a price, brand, or wardrobe piece that wasn't passed in. The interaction still completes with a usable, if shorter, caption. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     Use ASCII art or a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html).
     Do NOT embed an image — graders need to read your diagram directly in the file;
     an embedded image or screenshot cannot be evaluated.
     You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

```
User query: "vintage graphic tee, size M, under $30"
    │
    ▼
Planning Loop ──────────────────────────────────────────────────────────┐
    │                                                                    │
    │   parse query → session{ description, size, max_price, wardrobe }  │
    │                                                                    │
    ├─► search_listings(description, size, max_price)                    │
    │       │                                                            │
    │       │ results == []                                              │
    │       ├──► [ERROR] session.error = "No listings found —            │
    │       │            try raising price / loosening size" → return ───┤
    │       │                                                            │
    │       │ results == [item, ...]                                     │
    │       ▼                                                            │
    │   Session: selected_item = results[0] ◄──────────────┐            │
    │       │                                              │            │
    ├─► suggest_outfit(selected_item, wardrobe)            │ reads      │
    │       │                                              │            │
    │       ├── wardrobe.items == []  → single-item suggestion          │
    │       │      (style the new piece on its own — NOT an error)      │
    │       │                                                            │
    │       └── wardrobe.items != []  → pair with owned pieces          │
    │       ▼                                                            │
    │   Session: outfit_suggestion = "..."                              │
    │       │                                                            │
    └─► create_fit_card(outfit_suggestion, selected_item) ◄─ reads ─────┘
            │
        Session: fit_card = "..."        (error path returns here too)
            │
            ▼
        Return session → show user: listing + styling tip + fit card
                         (or, on early return, the error + what to try)
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

I'll use **Claude (Claude Code)** for all three tools, one at a time.
- **`search_listings`** — I'll give Claude the Tool 1 block (inputs, return shape, empty-result behavior) and tell it to load data with `load_listings()` from `utils/data_loader.py` rather than re-reading the file. I expect a function that filters by all three params (keyword match on title/description/style_tags, lenient size match, `price <= max_price`) and returns a ranked `list[dict]` or `[]`. **Verify:** confirm it uses `load_listings()`, filters on all three params, and returns `[]` on no match — then test 3 queries: (a) "vintage graphic tee"/M/$30 (loose match), (b) an impossible combo like size XS/$5 (must return `[]`), (c) "denim"/W30/$40 (multiple matches, check ranking).
- **`suggest_outfit`** — I'll give Claude the Tool 2 block plus the `wardrobe_schema.json` shape, stressing the empty-wardrobe branch. I expect a function that returns a styling string and handles `{"items": []}` with a single-item suggestion. **Verify:** call it once with `get_example_wardrobe()` (should name real owned pieces) and once with `get_empty_wardrobe()` (must not reference pieces the user doesn't own).
- **`create_fit_card`** — I'll give Claude the Tool 3 block. I expect a caption string that pulls real fields (`title`, `price`, `platform`) from `new_item`. **Verify:** run it on two different items and confirm the captions differ and contain that item's actual price/platform.

**Milestone 4 — Planning loop and state management:**

I'll give Claude the **Planning Loop**, **State Management**, **Error Handling**, and **Architecture** sections together and ask it to implement the loop that wires the three tools through a single `session` dict. I expect: query parsing → `search_listings` → early return on `[]` → `suggest_outfit` (continues even on empty wardrobe) → `create_fit_card` → return session. **Verify:** trace the happy-path query end-to-end and check all four session keys get set; then force the no-results case and confirm it returns early with `error` set and never calls `suggest_outfit`; then run with an empty wardrobe and confirm the pipeline still reaches `fit_card`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**What FitFindr needs to do:** FitFindr takes a shopper's natural-language request for a secondhand clothing item and turns it into a finished, post-ready outfit. A search request triggers `search_listings` to find matching listings; a found item then triggers `suggest_outfit`, which styles it against the user's existing wardrobe; and a finished outfit triggers `create_fit_card` to write a short social caption. If any step fails — most importantly when `search_listings` returns no matches — the agent stops, tells the user what to adjust (loosen the price, change the size, try different keywords), and does **not** pass empty input down the chain to the styling or fit-card tools.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Search:** The query asks to find an item, so the agent calls `search_listings("vintage graphic tee", size="M", max_price=30.0)`. It returns 3 matching listings sorted by relevance, and FitFindr picks the top result: "Faded Band Tee — $22, Depop, Good condition."

**Step 2 — Suggest outfit:** Because Step 1 returned a real item, the agent calls `suggest_outfit(new_item=<band tee>, wardrobe=<user's wardrobe>)`. It returns a styling suggestion: "Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape."

**Step 3 — Fit card:** With a complete outfit in hand, the agent calls `create_fit_card(outfit=<suggestion>, new_item=<band tee>)`, which returns a short, post-ready caption: "thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"

**Final output to user:** The user sees the matched listing (Faded Band Tee, $22, Depop, Good condition), the styling suggestion pairing it with their wide-leg jeans and platform boots, and the ready-to-post fit-card caption.

**Error path:** If `search_listings` returns nothing, FitFindr stops here and tells the user what to try differently (e.g., raise the price cap, adjust the size, or use broader keywords). It does **not** call `suggest_outfit` with empty input.
`