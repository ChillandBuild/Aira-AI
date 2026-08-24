# Nested Intake Packages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a package contain sub-options nested to unlimited depth, plus optional addons on a leaf package, plus an active/inactive toggle at any depth — replacing today's flat package list in the WhatsApp paid-intake flow.

**Architecture:** Packages stay a JSON blob inside `app_settings.value` (`key='intake_config'`) — each entry becomes a recursive node (`options` = children, presence means non-leaf; `addons` = leaf-only extras; `active` = visibility). The bot's conversation state machine gains one pure recursive resolver (`_resolve_choice`) that auto-descends through single-child chains at any depth and stops at either a leaf (auto-select) or a menu (ask the lead) — replacing today's root-only special case. A new `awaiting_addon_choice` status handles the optional addon step after a leaf is chosen. The frontend gets a recursive tree editor on its own settings page.

**Tech Stack:** FastAPI (Python), Supabase/Postgres, Next.js 14 (TypeScript/React). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-23-nested-packages-and-settings-nav-design.md` (sections 2-6 — this plan implements the nested-packages engine only; the settings navigation restructure is a separate plan, `docs/superpowers/plans/2026-08-24-settings-navigation-restructure.md`, and this plan's Task 8 depends on that plan's `intake-config/page.tsx` existing first)

## Global Constraints

- Leaf = a package node with no `options` key (or an empty list). Existing flat packages are already valid leaves — no data migration needed, only logic changes.
- Non-leaf `amount_paise` is display-only, defaults to `0`, and is never charged — only a leaf's price (plus any addons) is ever charged.
- `active` defaults to `true`. An inactive node hides its entire subtree from both the bot and the config editor.
- Package/addon keys must be unique across the *entire* tree, not just among siblings.
- Prices are always rendered in Python/TypeScript, never composed by an LLM — existing, load-bearing rule in this codebase (`intake.py:305-308`, `intake_copy.py:11-13`) — every new price-rendering function here follows it.
- Test style: this codebase's backend tests are `unittest.TestCase` classes run via pytest, with `mock_patch`/`AsyncMock` for the Gemini call and `MagicMock` for the Supabase client (see `backend/tests/test_intake_packages.py`) — new tests follow that pattern.

---

## Task 1: Migration — session snapshot columns + status values

**Files:**
- Create: `backend/supabase/migrations/186_intake_nested_packages.sql` (184 and 185 are already taken by `184_quick_reply_blocks.sql` and `185_chat_handover_resolver.sql` — check `ls backend/supabase/migrations | tail -5` again before running this step, in case another migration lands between now and execution)

**Interfaces:**
- Produces: `intake_sessions.package_path`, `.selected_addons`, `.total_amount_paise`, `.package_draft_path`, `.addon_draft_selection` columns; `'awaiting_addon_choice'` added to the `status` CHECK constraint.

- [ ] **Step 1: Write the migration**

```sql
-- 186_intake_nested_packages.sql
-- Packages can now nest (sub-options at unlimited depth) and carry optional
-- addons on a leaf. These columns snapshot the lead's actual path through the
-- tree and the final charged total, same reasoning as package_key/package_name/
-- package_amount_paise in 176: editing packages later must never rewrite what a
-- past lead was actually offered or charged.

BEGIN;

ALTER TABLE intake_sessions
  ADD COLUMN IF NOT EXISTS package_path jsonb,
  ADD COLUMN IF NOT EXISTS selected_addons jsonb,
  ADD COLUMN IF NOT EXISTS total_amount_paise integer,
  ADD COLUMN IF NOT EXISTS package_draft_path jsonb,
  ADD COLUMN IF NOT EXISTS addon_draft_selection jsonb;

ALTER TABLE intake_sessions
  DROP CONSTRAINT IF EXISTS intake_sessions_status_check;

ALTER TABLE intake_sessions
  ADD CONSTRAINT intake_sessions_status_check CHECK (status = ANY (ARRAY[
    'offer_pending'::text,
    'awaiting_package_choice'::text,
    'awaiting_addon_choice'::text,
    'collecting'::text,
    'awaiting_confirmation'::text,
    'awaiting_payment'::text,
    'paid'::text,
    'resolved'::text,
    'cancelled'::text
  ]));

COMMIT;
```

- [ ] **Step 2: Apply locally and verify**

Run: `cd backend && supabase db push` (check `backend/supabase/config.toml` if unsure which local-migration command this repo uses; do not apply directly to production).
Expected: migration applies cleanly, `\d intake_sessions` shows the 5 new columns and the updated CHECK constraint listing `awaiting_addon_choice`.

- [ ] **Step 3: Commit**

```bash
git add backend/supabase/migrations/186_intake_nested_packages.sql
git commit -m "feat: add nested-package snapshot columns to intake_sessions"
```

---

## Task 2: `package_list_block` — skip price on non-leaf nodes

**Files:**
- Modify: `backend/app/services/intake.py:305-315`
- Test: `backend/tests/test_intake_packages.py` (append to `PackageListMessageTests`)

**Interfaces:**
- Produces: `package_list_block(packages: list[dict]) -> str` — same signature, new behavior for nodes carrying an `options` key.

- [ ] **Step 1: Write the failing test**

```python
# append inside class PackageListMessageTests in backend/tests/test_intake_packages.py
    def test_omits_price_for_a_non_leaf_package(self):
        packages = [
            {"key": "basic", "name": "Basic", "amount_paise": 0, "description": "Pick a level", "options": [
                {"key": "basic_q", "name": "One Question", "amount_paise": 10000, "description": ""},
            ]},
        ]
        text = package_list_message(packages, "consultation")
        self.assertIn("Basic\n", text)
        self.assertNotIn("Basic —", text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_intake_packages.py::PackageListMessageTests::test_omits_price_for_a_non_leaf_package -v`
Expected: FAIL — current code always writes `f"• {p['name']} — {_rupees(p['amount_paise'])}"` regardless of `options`.

- [ ] **Step 3: Implement**

```python
# replace backend/app/services/intake.py:305-315
def package_list_block(packages: list[dict]) -> str:
    """Rendered in Python, never by the LLM: these are prices the customer will
    be held to, and a hallucinated figure is a real liability. The surrounding
    intro/question are composed in the tenant's language by intake_copy.

    A non-leaf entry (has `options`) shows no price -- its true price depends on
    which leaf under it gets picked, so `amount_paise` on a non-leaf is display-only
    and would be misleading here."""
    lines = []
    for p in packages:
        if p.get("options"):
            line = f"• {p['name']}"
        else:
            line = f"• {p['name']} — {_rupees(p['amount_paise'])}"
        if p.get("description"):
            line += f"\n  {p['description']}"
        lines.append(line)
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_intake_packages.py::PackageListMessageTests -v`
Expected: PASS, including the existing leaf-price tests (unchanged behavior for leaves).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/intake.py backend/tests/test_intake_packages.py
git commit -m "feat: omit price for non-leaf packages in the bot's package list"
```

---

## Task 3: Recursive resolver — `_active_children`, `_resolve_choice`, `_menu_at_path`, `_find_leaf`

**Files:**
- Modify: `backend/app/services/intake.py` (add after `package_list_message`, before `_PACKAGE_MATCH_SYSTEM_PROMPT`, i.e. after line 324)
- Test: `backend/tests/test_intake_packages.py` (new test classes)

**Interfaces:**
- Produces:
  - `_active_children(nodes: list[dict]) -> list[dict]`
  - `_resolve_choice(level: list[dict], path: list[dict]) -> tuple[str, dict | list[dict], list[dict]]` — outcome is `"leaf"` (returns the resolved node), `"choose"` (returns the list of active options to present), or `"empty"` (returns `[]`).
  - `_menu_at_path(packages: list[dict], path: list[dict]) -> list[dict]` — re-derives the menu the lead is currently looking at, by walking from root using the keys already confirmed in `path`.
  - `_find_leaf(packages: list[dict], key: str, path: list[dict] | None = None) -> tuple[dict, list[dict]] | None` — depth-first search for a leaf by key anywhere in the tree, returning it with its breadcrumb.
- Consumed by: Task 5 (`route_intake`), Task 6 (`change_session_package`).

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_intake_packages.py, above `if __name__ == "__main__":`
from app.services.intake import _active_children, _find_leaf, _menu_at_path, _resolve_choice


NESTED_PACKAGES = [
    {"key": "basic", "name": "Basic", "amount_paise": 0, "description": "", "active": True, "options": [
        {"key": "basic_q", "name": "One Question", "amount_paise": 10000, "description": "", "active": True},
        {"key": "basic_detail", "name": "Detailed Consultation", "amount_paise": 30000, "description": "", "active": True,
         "addons": [{"key": "pdf", "name": "PDF summary", "amount_paise": 20000, "description": "", "active": True}]},
    ]},
    {"key": "premium", "name": "Premium", "amount_paise": 50000, "description": "", "active": True},
]


class ActiveChildrenTests(unittest.TestCase):
    def test_filters_out_inactive_nodes(self):
        nodes = [{"key": "a", "active": True}, {"key": "b", "active": False}, {"key": "c"}]
        result = _active_children(nodes)
        self.assertEqual([n["key"] for n in result], ["a", "c"])


class ResolveChoiceTests(unittest.TestCase):
    def test_two_active_roots_asks_the_lead(self):
        outcome, result, path = _resolve_choice(NESTED_PACKAGES, [])
        self.assertEqual(outcome, "choose")
        self.assertEqual([n["key"] for n in result], ["basic", "premium"])
        self.assertEqual(path, [])

    def test_single_active_root_with_no_children_is_a_leaf(self):
        outcome, result, path = _resolve_choice([NESTED_PACKAGES[1]], [])
        self.assertEqual(outcome, "leaf")
        self.assertEqual(result["key"], "premium")
        self.assertEqual(path, [{"key": "premium", "name": "Premium"}])

    def test_single_active_root_with_children_auto_descends(self):
        outcome, result, path = _resolve_choice([NESTED_PACKAGES[0]], [])
        self.assertEqual(outcome, "choose")
        self.assertEqual([n["key"] for n in result], ["basic_q", "basic_detail"])
        self.assertEqual(path, [{"key": "basic", "name": "Basic"}])

    def test_auto_descends_through_a_single_active_child_to_a_leaf(self):
        single_child_chain = [{"key": "only", "name": "Only", "active": True, "options": [
            {"key": "leaf", "name": "Leaf", "amount_paise": 5000, "active": True},
        ]}]
        outcome, result, path = _resolve_choice(single_child_chain, [])
        self.assertEqual(outcome, "leaf")
        self.assertEqual(result["key"], "leaf")
        self.assertEqual(path, [{"key": "only", "name": "Only"}, {"key": "leaf", "name": "Leaf"}])

    def test_zero_active_options_is_empty(self):
        outcome, result, path = _resolve_choice([{"key": "a", "active": False}], [])
        self.assertEqual(outcome, "empty")
        self.assertEqual(result, [])


class MenuAtPathTests(unittest.TestCase):
    def test_root_path_returns_top_level(self):
        self.assertEqual([n["key"] for n in _menu_at_path(NESTED_PACKAGES, [])], ["basic", "premium"])

    def test_walks_into_a_matched_key(self):
        menu = _menu_at_path(NESTED_PACKAGES, [{"key": "basic", "name": "Basic"}])
        self.assertEqual([n["key"] for n in menu], ["basic_q", "basic_detail"])

    def test_unknown_key_in_path_returns_empty(self):
        self.assertEqual(_menu_at_path(NESTED_PACKAGES, [{"key": "nope", "name": "?"}]), [])


class FindLeafTests(unittest.TestCase):
    def test_finds_a_nested_leaf_and_its_path(self):
        found = _find_leaf(NESTED_PACKAGES, "basic_detail")
        self.assertIsNotNone(found)
        leaf, path = found
        self.assertEqual(leaf["key"], "basic_detail")
        self.assertEqual(path, [{"key": "basic", "name": "Basic"}, {"key": "basic_detail", "name": "Detailed Consultation"}])

    def test_finds_a_root_level_leaf(self):
        found = _find_leaf(NESTED_PACKAGES, "premium")
        self.assertEqual(found[1], [{"key": "premium", "name": "Premium"}])

    def test_unknown_key_returns_none(self):
        self.assertIsNone(_find_leaf(NESTED_PACKAGES, "nope"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_intake_packages.py::ActiveChildrenTests tests/test_intake_packages.py::ResolveChoiceTests tests/test_intake_packages.py::MenuAtPathTests tests/test_intake_packages.py::FindLeafTests -v`
Expected: FAIL — `ImportError: cannot import name '_active_children'` (none of these functions exist yet).

- [ ] **Step 3: Implement, inserted into `backend/app/services/intake.py` right after `package_list_message` (after line 324)**

```python
def _active_children(nodes: list[dict]) -> list[dict]:
    return [n for n in nodes if n.get("active", True)]


def _resolve_choice(level: list[dict], path: list[dict]) -> tuple[str, dict | list[dict], list[dict]]:
    """Resolve what the bot should do at a given menu level, auto-descending
    through any chain of single-active-option levels -- this is the recursive
    generalization of the old root-only "if len(packages) == 1: auto-select" rule.

    Returns one of:
      ("leaf", node, path)      -- a single purchasable package was resolved
      ("choose", [nodes], path) -- 2+ active options, ask the lead to pick
      ("empty", [], path)       -- zero active options at this level (misconfigured)
    `path` is the breadcrumb [{key, name}, ...] from root to here."""
    active = _active_children(level)
    if not active:
        return ("empty", [], path)
    if len(active) == 1:
        only = active[0]
        new_path = path + [{"key": only["key"], "name": only["name"]}]
        if only.get("options"):
            return _resolve_choice(only["options"], new_path)
        return ("leaf", only, new_path)
    return ("choose", active, path)


def _menu_at_path(packages: list[dict], path: list[dict]) -> list[dict]:
    """Re-derive the menu the lead is currently looking at, by walking the live
    config from root using the keys already confirmed in `path`. Always re-derived
    rather than cached, so an operator editing packages mid-conversation can't
    leave the lead looking at a stale menu."""
    level = packages
    for step in path:
        match = next((n for n in level if n.get("key") == step["key"]), None)
        level = match["options"] if match and match.get("options") else []
    return level


def _find_leaf(packages: list[dict], key: str, path: list[dict] | None = None) -> tuple[dict, list[dict]] | None:
    """Depth-first search for a leaf package by key anywhere in the tree,
    returning it with its breadcrumb. Used when a session already has a
    package_key and the bot needs to look up that leaf's current addons, or
    when an operator repoints a session at any leaf regardless of depth."""
    path = path or []
    for node in packages:
        node_path = path + [{"key": node["key"], "name": node["name"]}]
        if node.get("options"):
            found = _find_leaf(node["options"], key, node_path)
            if found:
                return found
        elif node["key"] == key:
            return (node, node_path)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_intake_packages.py::ActiveChildrenTests tests/test_intake_packages.py::ResolveChoiceTests tests/test_intake_packages.py::MenuAtPathTests tests/test_intake_packages.py::FindLeafTests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/intake.py backend/tests/test_intake_packages.py
git commit -m "feat: add recursive package-tree resolver functions"
```

---

## Task 4: Addon matching + addon list rendering + `_package_patch` extension

**Files:**
- Modify: `backend/app/services/intake.py` (add `addon_list_block`, `match_addons` after `match_package` at line 369; extend `_package_patch` at lines 411-418)
- Modify: `backend/app/services/intake_copy.py` (add `"addons"` wrapper purpose)
- Test: `backend/tests/test_intake_packages.py` (new test classes)

**Interfaces:**
- Produces: `addon_list_block(addons: list[dict]) -> str`, `match_addons(message: str, addons: list[dict], tenant_id: str) -> list[dict]`, `_package_patch(package: dict, path: list[dict] | None = None, total_amount_paise: int | None = None) -> dict`.
- Consumed by: Task 5.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_intake_packages.py
from app.services.intake import _package_patch, addon_list_block, match_addons

ADDONS = [
    {"key": "pdf", "name": "PDF summary", "amount_paise": 20000, "description": ""},
    {"key": "call", "name": "Follow-up call", "amount_paise": 15000, "description": ""},
]


class AddonListBlockTests(unittest.TestCase):
    def test_renders_names_and_plus_prices(self):
        text = addon_list_block(ADDONS)
        self.assertIn("PDF summary — +₹200", text)
        self.assertIn("Follow-up call — +₹150", text)


class MatchAddonsTests(unittest.TestCase):
    def test_no_addons_configured_returns_empty_without_calling_llm(self):
        with mock_patch("app.services.intake.gemini_chat_completion_json") as llm:
            result = asyncio.run(match_addons("yes please", [], "t-1"))
        self.assertEqual(result, [])
        llm.assert_not_called()

    def test_decline_words_short_circuit_without_calling_the_llm(self):
        with mock_patch("app.services.intake.gemini_chat_completion_json") as llm:
            result = asyncio.run(match_addons("no thanks", ADDONS, "t-1"))
        self.assertEqual(result, [])
        llm.assert_not_called()

    def test_llm_selects_multiple_addons(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(return_value={"keys": ["pdf", "call"]}),
        ):
            result = asyncio.run(match_addons("both please", ADDONS, "t-1"))
        self.assertEqual({a["key"] for a in result}, {"pdf", "call"})

    def test_unknown_keys_from_the_llm_are_dropped_not_guessed(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(return_value={"keys": ["pdf", "made_up"]}),
        ):
            result = asyncio.run(match_addons("the summary one", ADDONS, "t-1"))
        self.assertEqual([a["key"] for a in result], ["pdf"])

    def test_llm_failure_returns_no_addons_not_a_crash(self):
        with mock_patch(
            "app.services.intake.gemini_chat_completion_json",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = asyncio.run(match_addons("uhh", ADDONS, "t-1"))
        self.assertEqual(result, [])


class PackagePatchTests(unittest.TestCase):
    def test_defaults_have_no_path_or_total(self):
        patch = _package_patch({"key": "basic", "name": "Basic", "amount_paise": 10000})
        self.assertEqual(patch, {
            "package_key": "basic", "package_name": "Basic", "package_amount_paise": 10000,
        })

    def test_includes_path_and_total_when_given(self):
        path = [{"key": "basic", "name": "Basic"}]
        patch = _package_patch({"key": "basic", "name": "Basic", "amount_paise": 10000}, path=path, total_amount_paise=30000)
        self.assertEqual(patch["package_path"], path)
        self.assertEqual(patch["total_amount_paise"], 30000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_intake_packages.py::AddonListBlockTests tests/test_intake_packages.py::MatchAddonsTests tests/test_intake_packages.py::PackagePatchTests -v`
Expected: FAIL — `addon_list_block`/`match_addons` don't exist; `_package_patch` doesn't accept `path`/`total_amount_paise` yet.

- [ ] **Step 3: Implement `addon_list_block` and `match_addons`, inserted right after `match_package` (after line 369)**

```python
def addon_list_block(addons: list[dict]) -> str:
    """Same non-LLM-rendered-price principle as package_list_block -- see its
    docstring."""
    lines = []
    for a in addons:
        line = f"• {a['name']} — +{_rupees(a['amount_paise'])}"
        if a.get("description"):
            line += f"\n  {a['description']}"
        lines.append(line)
    return "\n".join(lines)


_ADDON_DECLINE_WORDS = frozenset({"no", "skip", "none", "no thanks", "nope", "not needed"})

_ADDON_MATCH_SYSTEM_PROMPT = """You match a customer's reply to zero or more addons from a
fixed list. You are given the addons (key and name) and the customer's message.

Respond with JSON only: {"keys": ["<matching addon keys>"]} -- an empty list if the customer
declined, said no/skip/none, or didn't clearly choose any of the listed addons.

Rules:
- Every key in the list MUST be one of the keys given. Never invent a key.
- If ambiguous, return an empty list rather than guessing.
- JSON only, no other text."""


async def match_addons(message: str, addons: list[dict], tenant_id: str) -> list[dict]:
    """Match a lead's free-text reply to zero or more configured addons.
    Multi-select, unlike match_package -- an empty result is a valid, common
    outcome (the lead declined all addons), not a failure to re-ask about."""
    if not addons:
        return []

    if message.strip().lower() in _ADDON_DECLINE_WORDS:
        return []

    addon_list = "\n".join(f"- {a['key']}: {a['name']}" for a in addons)
    try:
        data = await gemini_chat_completion_json(
            system_prompt=_ADDON_MATCH_SYSTEM_PROMPT,
            user_prompt=f"Addons:\n{addon_list}\n\nCustomer message: {message}",
            temperature=0.0,
            max_tokens=100,
            tenant_id=tenant_id,
            purpose="intake_addon_match",
        )
    except Exception as e:
        logger.warning(f"Intake addon match failed, treating as no addons chosen: {e}")
        return []

    keys = set(data.get("keys") or [])
    return [a for a in addons if a["key"] in keys]
```

- [ ] **Step 4: Extend `_package_patch`, replacing `backend/app/services/intake.py:411-418`**

```python
def _package_patch(package: dict, path: list[dict] | None = None, total_amount_paise: int | None = None) -> dict:
    """Snapshot the chosen package onto the session row. Repricing or renaming a
    package later must not rewrite what a past lead was actually offered."""
    patch = {
        "package_key": package["key"],
        "package_name": package["name"],
        "package_amount_paise": package["amount_paise"],
    }
    if path is not None:
        patch["package_path"] = path
    if total_amount_paise is not None:
        patch["total_amount_paise"] = total_amount_paise
    return patch
```

- [ ] **Step 5: Add the `"addons"` wrapper purpose to `intake_copy.py`**

```python
# backend/app/services/intake_copy.py:104-107 -- add "addons" alongside "packages"
_WRAPPER_FALLBACKS = {
    "summary": ("Here's what I've got:", "Is that correct?"),
    "packages": ("Here are our options:", "Which one would you like?"),
    "addons": ("Want to add any of these?", "Reply with the ones you'd like, or say no thanks."),
}
```

```python
# backend/app/services/intake_copy.py:109-120 -- add "addons" alongside "packages"
_WRAPPER_TASKS = {
    "summary": (
        "You are showing the customer the details you collected, so they can confirm "
        "them before paying. Write a short intro line and a short closing question "
        "asking whether the details are correct."
    ),
    "packages": (
        "You are showing the customer the list of paid options. Write a short intro "
        "line and a short closing question asking which one they want. Do not mention "
        "any price -- the list with prices is inserted between your two lines."
    ),
    "addons": (
        "You are showing the customer optional add-ons available on top of the package "
        "they just picked. Write a short intro line and a short closing question asking "
        "which add-ons they want, or none. Do not mention any price -- the list with "
        "prices is inserted between your two lines."
    ),
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_intake_packages.py::AddonListBlockTests tests/test_intake_packages.py::MatchAddonsTests tests/test_intake_packages.py::PackagePatchTests -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/intake.py backend/app/services/intake_copy.py backend/tests/test_intake_packages.py
git commit -m "feat: add addon matching, addon list rendering, and package_path/total snapshotting"
```

---

## Task 5: Wire the recursive flow into `route_intake`

**Files:**
- Modify: `backend/app/services/intake.py:372-379` (`_ACTIVE_STATUSES`/`_PACKAGE_CHANGEABLE_STATUSES`)
- Modify: `backend/app/services/intake.py:543-611` (`offer_pending` and `awaiting_package_choice` blocks, replaced)
- Modify: `backend/app/services/intake.py` (add `awaiting_addon_choice` block after the replaced `awaiting_package_choice` block)
- Test: `backend/tests/test_intake_packages.py` (new integration test class) — first check whether another test file already drives `route_intake` end-to-end and reuse its mock shape

**Interfaces:**
- Consumes: `_resolve_choice`, `_active_children`, `_menu_at_path`, `_find_leaf` (Task 3), `match_addons`, `addon_list_block`, extended `_package_patch` (Task 4), non-leaf-aware `package_list_block` (Task 2).
- Produces: `route_intake` now handles arbitrarily nested packages and the new `awaiting_addon_choice` status.

- [ ] **Step 1: Check which existing test file drives `route_intake` end-to-end**

Run: `grep -rl "route_intake" backend/tests/`
Read whichever file(s) come back to see the existing mocking pattern for a full turn (mocked `db`, mocked `gather_context`/`resolve_language_mode`/`compose_wrapped`/`compose_line`, etc.) before Step 2 — reuse that exact fixture shape. If none exists, add the integration test class to `backend/tests/test_intake_packages.py`.

- [ ] **Step 2: Write failing integration tests for the multi-level drill-down + addon flow, using whichever mocking harness Step 1 found**

Using `NESTED_PACKAGES` from Task 3 (Basic → One Question / Detailed Consultation, Detailed Consultation has a PDF addon), write test cases covering:

1. `offer_pending` + affirmative reply → 2 active root packages → sends the root menu (assert non-leaf "Basic" has no price, leaf "Premium" shows its price).
2. `awaiting_package_choice` at root, lead says "Basic" → resolves into Basic's 2 children (both active → "choose") → reply lists "One Question" and "Detailed Consultation"; session's `package_draft_path` becomes `[{"key": "basic", "name": "Basic"}]`.
3. `awaiting_package_choice` at the Basic level, lead says "Detailed" → resolves to the `basic_detail` leaf, which has an active addon → session moves to `awaiting_addon_choice`; `package_key`/`package_name`/`package_amount_paise`/`package_path` are snapshotted; the addon menu is sent.
4. `awaiting_addon_choice`, lead says "yes" (mock `match_addons` to return the PDF addon) → `selected_addons` and `total_amount_paise` (30000 + 20000 = 50000) land on the session; flow proceeds into field collection (`ask_field` for the configured field, since `collected_data` starts empty).

Write these against the exact session/db mocking pattern found in Step 1 — do not invent a different harness shape than what the rest of this codebase's `route_intake` tests already use.

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `cd backend && pytest tests/test_intake_packages.py -k NestedPackageConversation -v` (adjust path if Step 1 found a different file)
Expected: FAIL — current `route_intake` still has the old root-only logic and no `awaiting_addon_choice` branch.

- [ ] **Step 4: Update the status tuples, replacing `backend/app/services/intake.py:372-379`**

```python
_ACTIVE_STATUSES = (
    "offer_pending", "awaiting_package_choice", "awaiting_addon_choice", "collecting",
    "awaiting_confirmation", "awaiting_payment", "paid",
)

_PACKAGE_CHANGEABLE_STATUSES = (
    "awaiting_package_choice", "awaiting_addon_choice", "collecting", "awaiting_confirmation", "awaiting_payment",
)
```

- [ ] **Step 5: Add `_finalize_leaf` as a nested helper inside `route_intake`, right after the `_say_summary` closure (after `backend/app/services/intake.py:530`)**

```python
        async def _finalize_leaf(leaf: dict, path: list[dict]) -> None:
            active_addons = _active_children(leaf.get("addons") or [])
            if active_addons:
                _update_session(session["id"], _package_patch(leaf, path) | {"status": "awaiting_addon_choice"}, db)
                await _send_and_log(
                    phone,
                    await compose_wrapped(
                        "addons",
                        tenant_id=tenant_id,
                        language_mode=language_mode,
                        customer_message=body,
                        block=addon_list_block(active_addons),
                        thread=thread,
                    ),
                    tenant_id, lead_id, db,
                )
                return
            collected = await extract_fields(body, config["fields"], session.get("collected_data") or {}, tenant_id)
            missing = missing_field_labels(config["fields"], collected)
            patch = _package_patch(leaf, path, total_amount_paise=leaf["amount_paise"]) | {
                "collected_data": collected, "field_schema": config["fields"],
            }
            if missing:
                _update_session(session["id"], patch | {"status": "collecting"}, db)
                await _say("ask_field", field_label=missing[0], collected=collected)
            else:
                _update_session(session["id"], patch | {"status": "awaiting_confirmation"}, db)
                await _say_summary(collected)
```

- [ ] **Step 6: Replace the `offer_pending` block, `backend/app/services/intake.py:543-579`**

```python
        if status == "offer_pending":
            if not _is_affirmative(body):
                _update_session(session["id"], {"status": "cancelled"}, db)
                return False
            packages = normalize_packages(config)
            outcome, result, path = _resolve_choice(packages, [])
            if outcome == "empty":
                logger.error(f"Intake session {session['id']} has no active packages configured despite being enabled")
                await _say("no_packages")
                return True
            if outcome == "leaf":
                await _finalize_leaf(result, path)
                return True
            _update_session(session["id"], {"status": "awaiting_package_choice", "package_draft_path": path}, db)
            await _send_and_log(
                phone,
                await compose_wrapped(
                    "packages",
                    tenant_id=tenant_id,
                    language_mode=language_mode,
                    customer_message=body,
                    block=package_list_block(result),
                    thread=thread,
                ),
                tenant_id, lead_id, db,
            )
            return True
```

- [ ] **Step 7: Replace the `awaiting_package_choice` block, `backend/app/services/intake.py:581-611`, and add the new `awaiting_addon_choice` block right after it**

```python
        if status == "awaiting_package_choice":
            packages = normalize_packages(config)
            draft_path = session.get("package_draft_path") or []
            current_level = _menu_at_path(packages, draft_path) or packages
            active_here = _active_children(current_level)
            chosen = await match_package(body, active_here, tenant_id)
            if chosen is None:
                intro = await compose_line(
                    "package_reask",
                    tenant_id=tenant_id,
                    language_mode=language_mode,
                    customer_message=body,
                    thread=thread,
                    knowledge=knowledge,
                )
                await _send_and_log(
                    phone,
                    f"{intro}\n\n{package_list_block(active_here)}",
                    tenant_id, lead_id, db,
                )
                return True
            outcome, result, path = _resolve_choice([chosen], draft_path)
            if outcome == "empty":
                logger.error(f"Intake session {session['id']} package {chosen['key']} has no active options")
                await _say("no_packages")
                return True
            if outcome == "leaf":
                await _finalize_leaf(result, path)
                return True
            _update_session(session["id"], {"package_draft_path": path}, db)
            await _send_and_log(
                phone,
                await compose_wrapped(
                    "packages",
                    tenant_id=tenant_id,
                    language_mode=language_mode,
                    customer_message=body,
                    block=package_list_block(result),
                    thread=thread,
                ),
                tenant_id, lead_id, db,
            )
            return True

        if status == "awaiting_addon_choice":
            packages = normalize_packages(config)
            found = _find_leaf(packages, session.get("package_key"))
            active_addons = _active_children(found[0].get("addons") or []) if found else []
            chosen_addons = await match_addons(body, active_addons, tenant_id)
            addons_total = sum(a["amount_paise"] for a in chosen_addons)
            total = (session.get("package_amount_paise") or 0) + addons_total
            collected = await extract_fields(body, config["fields"], session.get("collected_data") or {}, tenant_id)
            missing = missing_field_labels(config["fields"], collected)
            patch = {
                "selected_addons": chosen_addons,
                "total_amount_paise": total,
                "collected_data": collected,
                "field_schema": config["fields"],
            }
            if missing:
                _update_session(session["id"], patch | {"status": "collecting"}, db)
                await _say("ask_field", field_label=missing[0], collected=collected)
            else:
                _update_session(session["id"], patch | {"status": "awaiting_confirmation"}, db)
                await _say_summary(collected)
            return True
```

- [ ] **Step 8: Run the full intake test suite**

Run: `cd backend && pytest tests/test_intake_packages.py tests/test_intake_attempts.py tests/test_intake_non_answers.py tests/test_intake_customer_name.py tests/test_intake_language.py tests/test_intake_affirmative.py -v`
Expected: PASS — every pre-existing single-package and flat-multi-package test still passes (they exercise `_resolve_choice` implicitly via `route_intake` now, and reduce to the old behavior when there's no nesting).

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/intake.py backend/tests/
git commit -m "feat: recursive package drill-down and addon step in route_intake"
```

---

## Task 6: `change_session_package` — recursive leaf lookup

**Files:**
- Modify: `backend/app/services/intake.py:1105-1135`
- Test: `backend/tests/test_intake_packages.py` (extend `ChangeSessionPackageTests`)

**Interfaces:**
- Consumes: `_find_leaf` (Task 3).
- Produces: `change_session_package` now finds a leaf at any depth, not just root-level, and refuses non-leaf keys.

- [ ] **Step 1: Write the failing tests**

```python
# append inside class ChangeSessionPackageTests in backend/tests/test_intake_packages.py
    def test_finds_a_nested_leaf_by_key(self):
        db = self._db_with_session("awaiting_payment")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": NESTED_PACKAGES, "service_noun": "reading",
        }):
            result = asyncio.run(change_session_package("s-1", "t-1", "basic_detail", db=db))
        self.assertIsNotNone(result)
        update_patch = db.table.return_value.update.call_args[0][0]
        self.assertEqual(update_patch["package_key"], "basic_detail")
        self.assertEqual(update_patch["package_amount_paise"], 30000)
        self.assertEqual(update_patch["package_path"], [
            {"key": "basic", "name": "Basic"}, {"key": "basic_detail", "name": "Detailed Consultation"},
        ])

    def test_refuses_a_non_leaf_key(self):
        db = self._db_with_session("awaiting_payment")
        with mock_patch("app.services.intake.get_intake_config", return_value={
            "packages": NESTED_PACKAGES, "service_noun": "reading",
        }):
            result = asyncio.run(change_session_package("s-1", "t-1", "basic", db=db))
        self.assertIsNone(result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_intake_packages.py::ChangeSessionPackageTests -v`
Expected: FAIL — current code does `next((p for p in normalize_packages(config) if p["key"] == package_key), None)`, a root-only search with no leaf check: it would miss `basic_detail` (not at root) and would wrongly succeed for `basic` (a non-leaf).

- [ ] **Step 3: Implement, replacing `backend/app/services/intake.py:1125-1133`**

```python
    config = get_intake_config(tenant_id, db=db)
    packages = normalize_packages(config)
    found = _find_leaf(packages, package_key)
    if found is None:
        return None
    chosen, path = found

    # The old Razorpay link stays live until Razorpay processes the cancel, so
    # confirm_intake_payment records the amount that actually arrives rather
    # than assuming this one. See D16.
    patch = _package_patch(chosen, path, total_amount_paise=chosen["amount_paise"]) | {"payment_link": None, "amount_paise": None}
```

(The rest of the function — the `db.table(...).update(...)` call and the return statement — is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_intake_packages.py::ChangeSessionPackageTests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/intake.py backend/tests/test_intake_packages.py
git commit -m "fix: change_session_package finds a leaf at any depth, refuses non-leaf keys"
```

---

## Task 7: Backend validation — recursive Pydantic model + tree-wide checks

**Files:**
- Modify: `backend/app/routes/app_settings.py:102-106` (`IntakePackageUpdate`)
- Modify: `backend/app/routes/app_settings.py:1643-1650` (validation block)
- Test: `backend/tests/test_intake_packages.py` (extend `IntakeConfigRouteTests`)

**Interfaces:**
- Produces: `IntakePackageUpdate` (recursive), `IntakeAddonUpdate`, `_walk_packages(nodes: list[dict])`, `_validate_packages(packages: list[dict]) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# append inside class IntakeConfigRouteTests in backend/tests/test_intake_packages.py
    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_saves_a_nested_package_tree(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 0, "description": "", "active": True, "options": [
                    {"key": "basic_q", "name": "One Question", "amount_paise": 10000, "description": "", "active": True},
                ]},
            ],
        })
        self.assertEqual(res.status_code, 200)
        saved = mock_save.call_args[0][1]
        self.assertEqual(saved["packages"][0]["options"][0]["key"], "basic_q")

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_non_leaf_amount_paise_is_not_validated(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 0, "description": "", "active": True, "options": [
                    {"key": "basic_q", "name": "One Question", "amount_paise": 10000, "description": "", "active": True},
                ]},
            ],
        })
        self.assertEqual(res.status_code, 200)

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_rejects_a_leaf_with_zero_amount(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [{"key": "basic", "name": "Basic", "amount_paise": 0, "description": "", "active": True}],
        })
        self.assertEqual(res.status_code, 400)
        mock_save.assert_not_called()

    @mock_patch("app.routes.app_settings.save_intake_config")
    @mock_patch("app.routes.app_settings.get_intake_config")
    def test_rejects_a_duplicate_key_between_a_sub_package_and_an_addon(self, mock_get, mock_save):
        mock_get.return_value = {"packages": [], "amount_paise": 0}
        res = self.client.patch("/api/v1/settings/intake-config", json={
            "packages": [
                {"key": "basic", "name": "Basic", "amount_paise": 10000, "description": "", "active": True,
                 "addons": [{"key": "basic", "name": "Dup", "amount_paise": 500, "description": "", "active": True}]},
            ],
        })
        self.assertEqual(res.status_code, 400)
        mock_save.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_intake_packages.py::IntakeConfigRouteTests -v`
Expected: FAIL — `IntakePackageUpdate` currently has no `options`/`addons`/`active` fields, and the zero-amount leaf check currently applies flatly without leaf-awareness.

- [ ] **Step 3: Replace `IntakePackageUpdate`, `backend/app/routes/app_settings.py:102-106`**

```python
class IntakeAddonUpdate(BaseModel):
    key: str
    name: str
    amount_paise: int = 0
    description: str = ""
    active: bool = True


class IntakePackageUpdate(BaseModel):
    key: str
    name: str
    amount_paise: int = 0
    description: str = ""
    active: bool = True
    options: list["IntakePackageUpdate"] | None = None
    addons: list[IntakeAddonUpdate] | None = None


IntakePackageUpdate.model_rebuild()
```

- [ ] **Step 4: Add `_walk_packages`/`_validate_packages` above `patch_intake_config`, and replace the validation block at `backend/app/routes/app_settings.py:1643-1650`**

```python
def _walk_packages(nodes: list[dict]):
    """Yield (node, is_leaf) for every package node in the tree, depth-first."""
    for n in nodes:
        options = n.get("options") or []
        yield n, not options
        yield from _walk_packages(options)


def _validate_packages(packages: list[dict]) -> None:
    keys: list[str] = []
    for node, is_leaf in _walk_packages(packages):
        keys.append(node["key"])
        if not node["name"].strip():
            raise HTTPException(status_code=400, detail="Package name is required")
        if is_leaf and node["amount_paise"] < 1:
            raise HTTPException(status_code=400, detail="Package amount must be >= 1 paise")
        for addon in node.get("addons") or []:
            keys.append(addon["key"])
            if not addon["name"].strip():
                raise HTTPException(status_code=400, detail="Addon name is required")
            if addon["amount_paise"] < 0:
                raise HTTPException(status_code=400, detail="Addon amount must be >= 0")
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="Duplicate package or addon keys")
```

```python
    # replaces backend/app/routes/app_settings.py:1643-1650
    if "packages" in patch:
        _validate_packages(patch["packages"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_intake_packages.py::IntakeConfigRouteTests -v`
Expected: PASS, including the 3 pre-existing tests in that class (flat packages are a tree of depth 1, so `_validate_packages` reduces to the old flat check for them).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/app_settings.py backend/tests/test_intake_packages.py
git commit -m "feat: recursive validation for nested package trees"
```

---

## Task 8: Frontend — recursive `PackageEditor` on its own settings page

**Files:**
- Create: `frontend/app/dashboard/settings/intake-config/packages/page.tsx`
- Create: `frontend/app/dashboard/settings/intake-config/packages/PackageEditor.tsx`
- Create: `frontend/app/dashboard/settings/intake-config/packages/packageKeys.ts`
- Create: `frontend/app/dashboard/settings/slugify.ts`
- Test: `frontend/app/dashboard/settings/intake-config/packages/packageKeys.test.ts`

**Interfaces:**
- Consumes: `GET`/`PATCH /api/v1/settings/intake-config` (same endpoint `IntakeConfigPanel.tsx` uses, editing only the `packages` key — the backend merges partial patches, confirmed at `app_settings.py:1655`).
- Produces: the tree editor UI. Task 9 links to this page from `IntakeConfigPanel.tsx`.

- [ ] **Step 1: Write the failing test for the pure key-uniqueness helper**

```ts
// frontend/app/dashboard/settings/intake-config/packages/packageKeys.test.ts
import { describe, it, expect } from "vitest";
import { collectAllKeys, uniqueKey } from "./packageKeys";

describe("collectAllKeys", () => {
  it("collects package keys at every depth plus addon keys", () => {
    const packages = [
      { key: "basic", name: "Basic", amount_paise: 0, description: "", active: true, options: [
        { key: "basic_q", name: "One Question", amount_paise: 10000, description: "", active: true },
      ]},
      { key: "premium", name: "Premium", amount_paise: 50000, description: "", active: true, addons: [
        { key: "pdf", name: "PDF", amount_paise: 20000, description: "", active: true },
      ]},
    ];
    expect(collectAllKeys(packages)).toEqual(new Set(["basic", "basic_q", "premium", "pdf"]));
  });
});

describe("uniqueKey", () => {
  it("returns the base key when it's free", () => {
    expect(uniqueKey("basic", new Set(["premium"]))).toBe("basic");
  });

  it("appends a numeric suffix on collision", () => {
    expect(uniqueKey("basic", new Set(["basic"]))).toBe("basic_2");
  });

  it("keeps incrementing past multiple collisions", () => {
    expect(uniqueKey("basic", new Set(["basic", "basic_2", "basic_3"]))).toBe("basic_4");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run app/dashboard/settings/intake-config/packages/packageKeys.test.ts`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```ts
// frontend/app/dashboard/settings/intake-config/packages/packageKeys.ts
interface KeyedNode {
  key: string;
  options?: KeyedNode[];
  addons?: { key: string }[];
}

export function collectAllKeys(packages: KeyedNode[]): Set<string> {
  const keys = new Set<string>();
  const visit = (nodes: KeyedNode[]) => {
    for (const n of nodes) {
      keys.add(n.key);
      if (n.options) visit(n.options);
      if (n.addons) n.addons.forEach(a => keys.add(a.key));
    }
  };
  visit(packages);
  return keys;
}

export function uniqueKey(base: string, existing: Set<string>): string {
  if (!existing.has(base)) return base;
  let n = 2;
  while (existing.has(`${base}_${n}`)) n++;
  return `${base}_${n}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run app/dashboard/settings/intake-config/packages/packageKeys.test.ts`
Expected: PASS.

- [ ] **Step 5: Extract `slugify` to a shared file (currently duplicated inline in `IntakeConfigPanel.tsx:44-46`)**

```ts
// frontend/app/dashboard/settings/slugify.ts
export function slugify(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "field";
}
```

In `IntakeConfigPanel.tsx`, replace the local `slugify` definition (lines 44-46) with `import { slugify } from "./slugify";`.

- [ ] **Step 6: Create the recursive `PackageEditor` component**

```tsx
// frontend/app/dashboard/settings/intake-config/packages/PackageEditor.tsx
"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { collectAllKeys, uniqueKey } from "./packageKeys";
import { slugify } from "../../slugify";

export interface IntakeAddon {
  key: string;
  name: string;
  amount_paise: number;
  description: string;
  active: boolean;
}

export interface IntakePackage {
  key: string;
  name: string;
  amount_paise: number;
  description: string;
  active: boolean;
  options?: IntakePackage[];
  addons?: IntakeAddon[];
}

interface PackageEditorProps {
  packages: IntakePackage[];
  onChange: (packages: IntakePackage[]) => void;
  canManage: boolean;
}

export function PackageEditor({ packages, onChange, canManage }: PackageEditorProps) {
  function addRootPackage() {
    const existing = collectAllKeys(packages);
    const key = uniqueKey("package", existing);
    onChange([...packages, { key, name: "", amount_paise: 0, description: "", active: true }]);
  }

  function updateAt(index: number, next: IntakePackage) {
    onChange(packages.map((p, i) => (i === index ? next : p)));
  }

  function removeAt(index: number) {
    onChange(packages.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-2">
      {packages.map((pkg, index) => (
        <PackageNode
          key={pkg.key}
          node={pkg}
          depth={0}
          allKeys={collectAllKeys(packages)}
          onChange={(next) => updateAt(index, next)}
          onRemove={() => removeAt(index)}
          canManage={canManage}
        />
      ))}
      {packages.length === 0 && (
        <p className="font-body text-xs text-ink-muted italic">
          No packages yet — add at least one before enabling.
        </p>
      )}
      {canManage && (
        <button
          type="button"
          onClick={addRootPackage}
          className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700"
        >
          <Plus size={14} /> Add package
        </button>
      )}
    </div>
  );
}

function PackageNode({
  node, depth, allKeys, onChange, onRemove, canManage,
}: {
  node: IntakePackage; depth: number; allKeys: Set<string>;
  onChange: (next: IntakePackage) => void; onRemove: () => void; canManage: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const isLeaf = !node.options || node.options.length === 0;
  const hasAddons = !!node.addons && node.addons.length > 0;

  function commitName(name: string) {
    const others = new Set(allKeys);
    others.delete(node.key);
    onChange({ ...node, name, key: uniqueKey(slugify(name) || "package", others) });
  }

  function addSubPackage() {
    const key = uniqueKey("package", allKeys);
    const options = [...(node.options ?? []), { key, name: "", amount_paise: 0, description: "", active: true }];
    onChange({ ...node, options });
  }

  function updateOption(i: number, next: IntakePackage) {
    onChange({ ...node, options: (node.options ?? []).map((o, idx) => (idx === i ? next : o)) });
  }

  function removeOption(i: number) {
    const options = (node.options ?? []).filter((_, idx) => idx !== i);
    onChange({ ...node, options: options.length ? options : undefined });
  }

  function addAddon() {
    const key = uniqueKey("addon", allKeys);
    const addons = [...(node.addons ?? []), { key, name: "", amount_paise: 0, description: "", active: true }];
    onChange({ ...node, addons });
  }

  function updateAddon(i: number, patch: Partial<IntakeAddon>) {
    const addons = (node.addons ?? []).map((a, idx) => (idx === i ? { ...a, ...patch } : a));
    onChange({ ...node, addons });
  }

  function removeAddon(i: number) {
    const addons = (node.addons ?? []).filter((_, idx) => idx !== i);
    onChange({ ...node, addons: addons.length ? addons : undefined });
  }

  return (
    <div className="rounded-2xl border border-border bg-surface-subtle p-3 space-y-2" style={{ marginLeft: depth * 20 }}>
      <div className="flex items-center gap-2">
        {(!isLeaf || hasAddons) && (
          <button type="button" onClick={() => setExpanded(e => !e)} className="text-ink-muted">
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        )}
        <input
          type="text"
          value={node.name}
          onChange={(e) => onChange({ ...node, name: e.target.value })}
          onBlur={(e) => commitName(e.target.value)}
          placeholder="Package name (e.g. Basic)"
          disabled={!canManage}
          className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
        />
        {isLeaf && (
          <input
            type="number"
            min={1}
            value={node.amount_paise ? node.amount_paise / 100 : ""}
            onChange={(e) => onChange({ ...node, amount_paise: Math.round(Number(e.target.value) * 100) })}
            placeholder="₹"
            disabled={!canManage}
            className="w-24 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
          />
        )}
        <label className="flex items-center gap-1 text-xs font-body text-ink-muted whitespace-nowrap">
          <input type="checkbox" checked={node.active} disabled={!canManage} onChange={(e) => onChange({ ...node, active: e.target.checked })} />
          Active
        </label>
        {canManage && (
          <button type="button" onClick={onRemove} aria-label="Remove package" className="text-ink-muted hover:text-red-600">
            <Trash2 size={16} />
          </button>
        )}
      </div>

      <input
        type="text"
        value={node.description}
        onChange={(e) => onChange({ ...node, description: e.target.value })}
        placeholder="What's included"
        disabled={!canManage}
        className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
      />

      {canManage && (
        <div className="flex gap-3">
          {!hasAddons && (
            <button type="button" onClick={addSubPackage} className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700">
              <Plus size={12} /> Add sub-package
            </button>
          )}
          {isLeaf && !node.options && (
            <button type="button" onClick={addAddon} className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700">
              <Plus size={12} /> Add addon
            </button>
          )}
        </div>
      )}

      {expanded && node.options && node.options.length > 0 && (
        <div className="space-y-2 pt-1">
          {node.options.map((opt, i) => (
            <PackageNode
              key={opt.key}
              node={opt}
              depth={depth + 1}
              allKeys={allKeys}
              onChange={(next) => updateOption(i, next)}
              onRemove={() => removeOption(i)}
              canManage={canManage}
            />
          ))}
        </div>
      )}

      {expanded && hasAddons && (
        <div className="space-y-2 pt-1 pl-5 border-l-2 border-border">
          <div className="font-label text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Addons</div>
          {node.addons!.map((addon, i) => (
            <div key={addon.key} className="flex items-center gap-2">
              <input
                type="text"
                value={addon.name}
                onChange={(e) => updateAddon(i, { name: e.target.value })}
                onBlur={(e) => {
                  const others = new Set(allKeys);
                  others.delete(addon.key);
                  updateAddon(i, { key: uniqueKey(slugify(e.target.value) || "addon", others) });
                }}
                placeholder="Addon name"
                disabled={!canManage}
                className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
              />
              <input
                type="number"
                min={0}
                value={addon.amount_paise ? addon.amount_paise / 100 : ""}
                onChange={(e) => updateAddon(i, { amount_paise: Math.round(Number(e.target.value) * 100) })}
                placeholder="+₹"
                disabled={!canManage}
                className="w-20 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
              />
              <label className="flex items-center gap-1 text-xs font-body text-ink-muted">
                <input type="checkbox" checked={addon.active} disabled={!canManage} onChange={(e) => updateAddon(i, { active: e.target.checked })} />
                Active
              </label>
              {canManage && (
                <button type="button" onClick={() => removeAddon(i)} aria-label="Remove addon" className="text-ink-muted hover:text-red-600">
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          ))}
          {canManage && (
            <button type="button" onClick={addAddon} className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700">
              <Plus size={12} /> Add another addon
            </button>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Create the page, doing its own load/save scoped to `packages` only**

```tsx
// frontend/app/dashboard/settings/intake-config/packages/page.tsx
"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Package } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { useSettingsForm } from "../../SettingsFormContext";
import { SaveButton, SaveStatus, SectionFooter, SettingsSection } from "../../SettingsSection";
import { PackageEditor, type IntakePackage } from "./PackageEditor";

export default function PackagesSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  const [saved, setSaved] = useState<IntakePackage[]>([]);
  const [draft, setDraft] = useState<IntakePackage[]>([]);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, { headers: auth });
      if (res.ok) {
        const data = await res.json();
        setSaved(data.packages ?? []);
        setDraft(data.packages ?? []);
      }
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(saved);

  async function handleSave() {
    if (!canManageSettings) return;
    setSaveState("saving");
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ packages: draft }),
      });
      if (!res.ok) throw new Error("Save failed");
      const data = await res.json();
      setSaved(data.packages ?? []);
      setDraft(data.packages ?? []);
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2000);
    } catch {
      setSaveState("idle");
    }
  }

  return (
    <div className="space-y-4">
      <Link href="/dashboard/settings/intake-config" className="inline-flex items-center gap-1.5 text-xs font-label font-semibold text-ink-muted hover:text-ink">
        <ArrowLeft size={14} /> Back to Intake Config
      </Link>

      <SettingsSection
        id="intake-packages"
        icon={Package}
        accent="violet"
        title="Packages"
        description="The lead picks one of these right after accepting the offer, before any details are collected. A package can contain sub-options nested to any depth, and a leaf package can offer optional addons."
        status={{ label: `${draft.length} package${draft.length === 1 ? "" : "s"}`, tone: draft.length > 0 ? "on" : "off" }}
        dirty={isDirty}
      >
        <PackageEditor packages={draft} onChange={setDraft} canManage={canManageSettings} />

        <SectionFooter status={<SaveStatus state={saveState} dirty={isDirty} idleLabel={`${draft.length} package${draft.length === 1 ? "" : "s"} configured`} />}>
          <SaveButton state={saveState} dirty={isDirty} disabled={!canManageSettings} onClick={handleSave} />
        </SectionFooter>
      </SettingsSection>
    </div>
  );
}
```

- [ ] **Step 8: Manual verification**

Run: `cd frontend && npm run dev`, navigate to `/dashboard/settings/intake-config/packages`.
Expected: add a root package "Basic", add a sub-package under it, add an addon under the sub-package — confirm "Add sub-package" disappears once an addon exists on that node, and vice versa. Toggle "Active" off on a node. Save, reload, confirm the tree persists exactly as built.

- [ ] **Step 9: Commit**

```bash
git add frontend/app/dashboard/settings/intake-config/packages/ frontend/app/dashboard/settings/slugify.ts frontend/app/dashboard/settings/IntakeConfigPanel.tsx
git commit -m "feat: recursive package tree editor page"
```

---

## Task 9: Replace the inline packages section in `IntakeConfigPanel.tsx` with a link

**Files:**
- Modify: `frontend/app/dashboard/settings/IntakeConfigPanel.tsx`

**Interfaces:**
- None — removes dead code, adds a link; `IntakeConfigPanel`'s save behavior for its remaining fields (`fields`, `offer_message`, `trigger_description`, `service_noun`, `enabled`) is unchanged.

- [ ] **Step 1: Remove the `IntakePackage` type (lines 17-22) and the `addPackage`/`updatePackage`/`removePackage`/`commitPackageName` functions (lines 110-131); replace the inline packages JSX block (lines 176-239) with a link row**

```tsx
// replaces IntakeConfigPanel.tsx:176-239
        <div className="flex items-center justify-between rounded-2xl border border-border bg-surface-subtle p-3">
          <div>
            <div className="font-label text-sm font-semibold text-ink">Packages</div>
            <div className="font-body text-xs text-ink-muted">
              {draft.packages.length} package{draft.packages.length === 1 ? "" : "s"} configured — nested sub-options and addons supported.
            </div>
          </div>
          <Link
            href="/dashboard/settings/intake-config/packages"
            className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700"
          >
            Manage Packages →
          </Link>
        </div>
```

Add `import Link from "next/link";` to the top of the file. `IntakeConfig`/`DEFAULT` (lines 24-42) are unchanged — `draft.packages.length` still reads from the same loaded config, only its editing UI moved out.

- [ ] **Step 2: Verify it builds**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 3: Lint check for now-unused imports**

Run: `cd frontend && npm run lint`
Expected: no unused-import warnings — `Plus`/`Trash2` are still used by the Fields section (`IntakeConfigPanel.tsx:259-291`), so neither import needs removing.

- [ ] **Step 4: Manual verification**

Run: `cd frontend && npm run dev`, navigate to `/dashboard/settings/intake-config`.
Expected: Packages section shows a one-line summary + "Manage Packages →" link instead of the full editor; clicking it navigates to the Task 8 page.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/settings/IntakeConfigPanel.tsx
git commit -m "refactor: move package editing out of IntakeConfigPanel into its own page"
```

---

## Self-Review Notes

- **Spec coverage:** data model + non-leaf display (Task 2, spec section 2), session snapshot columns (Task 1, spec section 3), bot flow incl. the worked example (Tasks 3-6, spec section 4), frontend editor (Tasks 8-9, spec section 5), testing (every task carries its own tests, matching spec section 6 item-for-item).
- **Placeholder scan:** one intentional exception, called out explicitly rather than hidden — Task 5 Step 2's integration test fixture depends on Step 1's discovery of the existing mock harness, since guessing the wrong shape would produce a test that can't run; every other step has complete, real code.
- **Type consistency:** `IntakePackage`/`IntakeAddon` (frontend, Task 8) mirror `IntakePackageUpdate`/`IntakeAddonUpdate` (backend, Task 7) field-for-field. `_resolve_choice`'s 3-outcome contract (`"leaf"`/`"choose"`/`"empty"`) is used identically at both call sites in Task 5. `_package_patch`'s new optional params match what Task 5 and Task 6 each pass.
- **Sequencing:** Task 8 depends on `intake-config/page.tsx` existing, which is the *other* plan's Task 6 — do not start Task 8 until that plan has shipped through at least its Task 6.
