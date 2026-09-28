"""A tool call the model wrote as text instead of making it.

Live 2026-09-28 (Astro Tamil, Gemini 3.1 Flash Lite): the reply ended with the line
"show_options(of='packages')", which went to the customer as text and no menu was sent.
"""
import asyncio
import json

from app.services import deal_actions, deal_turn

CTX = deal_actions.DealContext(
    config={"enabled": True, "fields": [], "service_noun": "consultation",
            "packages": [{"key": "one_question", "name": "One Question", "amount_paise": 4900}]},
    db=object(), lead_id="lead-1", tenant_id="t-1", phone="+91000",
)
BASE = [{"role": "system", "content": "s"}, {"role": "user", "content": "evlo charge?"}]
MENU = {"kind": "buttons", "options": ["49 Rs", "99 Rs"], "buttons": []}


class Model:
    """One model reply with no real tool calls; records what reaches apply_tool_calls."""

    def __init__(self, monkeypatch, draft: str, outcome: deal_actions.Outcome = deal_actions.Outcome()):
        self.draft = draft
        self.outcome = outcome
        self.applied: list[dict] = []
        monkeypatch.setattr(deal_actions, "apply_tool_calls", self._apply)
        monkeypatch.setattr(deal_turn, "_state_line", lambda ctx: "DEAL STATE stub")

    async def _apply(self, tool_calls, ctx, **kwargs):
        self.applied.extend(tool_calls)
        return self.outcome

    async def llm_with_tools(self, messages, tools, max_tokens, tenant_id):
        return self.draft, []

    async def llm(self, messages, max_tokens, tenant_id):
        return self.draft

    def run(self):
        return asyncio.run(deal_turn.converse_once(
            BASE, [], CTX, tenant_id="t-1", llm_with_tools=self.llm_with_tools, llm=self.llm,
        ))


def _names(calls: list[dict]) -> list[str]:
    return [c["function"]["name"] for c in calls]


def test_written_show_options_becomes_a_real_call_and_leaves_the_text(monkeypatch):
    model = Model(
        monkeypatch,
        "Consultation charges ₹49-la irundhu start aagudhu.\n\nshow_options(of='packages')",
        deal_actions.Outcome(menu=MENU),
    )
    text, calls, outcome = model.run()

    assert "show_options" not in text
    assert text == "Consultation charges ₹49-la irundhu start aagudhu."
    assert _names(model.applied) == ["show_options"]
    assert json.loads(model.applied[0]["function"]["arguments"]) == {"of": "packages"}
    assert outcome.menu == MENU


def test_backticked_call_with_double_quotes_is_caught(monkeypatch):
    model = Model(monkeypatch, 'Here are the options\n`show_options(of="packages")`', deal_actions.Outcome(menu=MENU))
    text, _calls, outcome = model.run()
    assert "show_options" not in text and outcome.menu == MENU


def test_unreadable_arguments_are_still_removed_from_the_text(monkeypatch):
    model = Model(monkeypatch, "Charges start at 49.\nshow_options(of=packages)")
    text, _calls, _outcome = model.run()
    assert "show_options" not in text
    assert model.applied == []


def test_lines_that_are_not_offered_tools_stay(monkeypatch):
    model = Model(monkeypatch, "Try this: print(hello)")
    text, _calls, _outcome = model.run()
    assert text == "Try this: print(hello)"
