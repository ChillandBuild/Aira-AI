"""The LLM judge for conversation evals (evals/conversations/judge.py): prompt building and
verdict parsing are pure; the model call is injected."""
import asyncio

from evals.conversations import judge

TRANSCRIPT = [
    {"lead": "hii", "replies": [{"text": "Vanakkam! Enna help venum?", "kind": "text", "options": []}], "events": []},
    {"lead": "49 Rs", "replies": [{"text": "Super, idho link", "kind": "text", "options": []}],
     "events": [{"type": "payment_link", "url": "https://rzp.io/l/1", "missing_required": []}]},
    {"lead": "show me", "replies": [{"text": "Pick one", "kind": "buttons", "options": ["49 Rs", "99Rs"]}], "events": [
        {"type": "handover", "reason": "x"}]},
]
SCENARIO = {"id": "s1", "expect": {"behaviour": ["Sends the link after the tap."]}}
CONFIG = {"kind": "service", "packages": [{"key": "a", "name": "One Question", "amount_paise": 4900}]}


class TestPrompt:
    def test_includes_every_turn_attachments_and_expectations(self):
        text = judge.build_user_prompt(SCENARIO, TRANSCRIPT, CONFIG)
        assert "Lead: hii" in text and "Aira: Vanakkam!" in text
        assert "[buttons: 49 Rs | 99Rs]" in text
        assert "[payment link sent]" in text and "[handed to a human]" in text
        assert "Sends the link after the tap." in text
        assert "One Question" in text and "₹49" in text

    def test_turns_are_numbered_from_one(self):
        text = judge.build_user_prompt(SCENARIO, TRANSCRIPT, CONFIG)
        assert "Turn 1" in text and "Turn 3" in text


class TestVerdict:
    def test_all_fours_and_fives_pass(self):
        v = judge.parse_verdict({"human": 5, "answered_first": 4, "memory": 5, "honesty": 5, "goal": 4, "issues": []})
        assert v["status"] == "pass" and v["min_score"] == 4

    def test_any_score_of_three_is_weak(self):
        v = judge.parse_verdict({"human": 3, "answered_first": 5, "memory": 5, "honesty": 5, "goal": 5, "issues": ["x"]})
        assert v["status"] == "weak"

    def test_any_score_of_two_or_less_fails(self):
        v = judge.parse_verdict({"human": 5, "answered_first": 5, "memory": 2, "honesty": 5, "goal": 5})
        assert v["status"] == "fail"

    def test_missing_or_garbage_scores_count_as_zero_not_pass(self):
        v = judge.parse_verdict({"human": "great", "issues": "not a list"})
        assert v["status"] == "fail" and v["scores"]["human"] == 0 and v["issues"] == ["not a list"]

    def test_scores_are_clamped_to_one_to_five(self):
        v = judge.parse_verdict({"human": 9, "answered_first": -1, "memory": 5, "honesty": 5, "goal": 5})
        assert v["scores"]["human"] == 5 and v["scores"]["answered_first"] == 0


class TestJudge:
    def test_judge_error_is_a_failure_not_a_pass(self):
        async def boom(*a, **k):
            raise RuntimeError("quota")

        v = asyncio.run(judge.judge_conversation(SCENARIO, TRANSCRIPT, CONFIG, "t", llm_json=boom))
        assert v["status"] == "fail" and "judge_error" in v["issues"][0]

    def test_calls_the_model_and_parses(self):
        async def fake(system, user, **kw):
            assert "SCORING" in system and "Turn 1" in user
            return {"human": 5, "answered_first": 5, "memory": 5, "honesty": 5, "goal": 5, "issues": []}

        v = asyncio.run(judge.judge_conversation(SCENARIO, TRANSCRIPT, CONFIG, "t", llm_json=fake))
        assert v["status"] == "pass"


def test_business_summary_lists_nested_options_and_addons():
    config = {"packages": [{"key": "lt", "name": "Long Term", "options": [
        {"key": "y1", "name": "1 Year", "amount_paise": 6000000}]},
        {"key": "c", "name": "Crash", "amount_paise": 1500000, "addons": [{"key": "m", "name": "Material", "amount_paise": 200000}]}]}
    text = judge.build_user_prompt({"expect": {}}, [], config)
    assert "1 Year ₹60000" in text and "Material +₹2000" in text
