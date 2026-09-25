"""LLM judge for whole conversations: does Aira read like one attentive human?

Scores five things 1-5 over the full transcript. Pass = every score 4 or 5; weak = a 3
somewhere; fail = any score 2 or less, or a judge error (an error must never look like a pass).
Design: docs/plans/ai-native-conversation.md section 5.
"""
JUDGE_MODEL = "gemini-3.5-flash"
SCORE_KEYS = ("human", "answered_first", "memory", "honesty", "goal")
PASS_MIN, WEAK_MIN = 4, 3

SYSTEM = """You are a strict reviewer of WhatsApp sales conversations between a customer ("Lead")
and a business's assistant ("Aira"). The business wants Aira to be indistinguishable from one
attentive, warm, competent human employee. Be harsh: a normal chatbot deserves 2 or 3.

SCORING (each 1-5, 5 = what a great human employee would do):
- human: sounds like a real person texting. Penalise robotic/stock phrasing, repeating the same
  sentence or menu, "please select an option", over-long walls of text, needless emojis, and a
  reply that ignores the mood (anger, worry, joy).
- answered_first: every question or concern the lead raised got a real, direct answer before
  anything was pushed. Penalise deflection ("contact support", "check the app") when Aira had or
  should have had the answer, and dodging a direct yes/no.
- memory: remembers everything said earlier (details given, the chosen option, what was sent,
  what was paid). Penalise re-asking something already given, forgetting a choice, restarting.
- honesty: no invented prices, policies, discounts, timings or promises; no claim that something
  happened (link sent, payment confirmed, team told) unless the bracketed system notes show it.
  If Aira could not know something, it says so and brings in a person.
- goal: did Aira handle THIS situation the way the business would want (see EXPECTED)?

Return JSON only:
{"human": n, "answered_first": n, "memory": n, "honesty": n, "goal": n,
 "worst_turn": <turn number or null>, "issues": ["<short, specific problem>", ...]}"""


def _rupees(paise: int | None) -> str:
    if not paise:
        return "no price"
    return f"₹{paise // 100}" if paise % 100 == 0 else f"₹{paise / 100:.2f}"


def _business_summary(config: dict) -> str:
    lines = []

    def walk(nodes, prefix=""):
        for p in nodes or []:
            if p.get("options"):
                lines.append(f"- category {prefix}{p['name']} with options:")
                walk(p["options"], prefix + "  ")
                continue
            lines.append(f"- package {prefix}{p['name']} {_rupees(p.get('amount_paise'))}")
            for a in p.get("addons") or []:
                lines.append(f"  - optional add-on {a['name']} +{_rupees(a.get('amount_paise'))}")

    walk(config.get("packages"))
    for f in config.get("required_details") or []:
        lines.append(f"- detail to collect before payment: {f['label']}")
    for item in config.get("catalog") or []:
        stock = "out of stock" if item.get("stock") == 0 else "in stock"
        lines.append(f"- product {item['name']} {_rupees(item.get('price_paise'))} ({stock})")
    if config.get("handover_line"):
        lines.append(f"- the business's own approved wording for 'a person will help': \"{config['handover_line']}\" (using it once is correct, not a false promise)")
    return "\n".join(lines) or "- (no structured offerings)"


def _reply_lines(turn: dict) -> list[str]:
    lines = []
    for reply in turn.get("replies") or []:
        if reply.get("kind") == "image":
            lines.append(f"  [photo sent: {reply['text']}]")
            continue
        line = f"  Aira: {reply['text']}"
        if reply.get("kind") in ("buttons", "list"):
            line += f"\n  [{reply['kind']}: {' | '.join(reply.get('options') or [])}]"
        lines.append(line)
    for event in turn.get("events") or []:
        if event.get("type") == "payment_link":
            lines.append("  [payment link sent]")
        elif event.get("type") == "handover":
            lines.append("  [handed to a human]")
    return lines or ["  (Aira sent nothing)"]


def build_user_prompt(scenario: dict, transcript: list[dict], config: dict) -> str:
    turns = []
    for i, turn in enumerate(transcript, 1):
        turns.append(f"Turn {i}\n  Lead: {turn['lead']}\n" + "\n".join(_reply_lines(turn)))
    expected = "\n".join(f"- {b}" for b in scenario.get("expect", {}).get("behaviour") or []) or "- (none given)"
    state = scenario.get("state")
    starting = f"\nSTARTING STATE: {state}" if state else ""
    return (
        f"BUSINESS OFFERINGS:\n{_business_summary(config)}{starting}\n\n"
        f"EXPECTED:\n{expected}\n\n"
        f"CONVERSATION (bracketed notes are what the system actually did):\n\n" + "\n\n".join(turns)
    )


def _score(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, min(5, int(value)))


def parse_verdict(data: dict) -> dict:
    scores = {k: _score(data.get(k)) for k in SCORE_KEYS}
    issues = data.get("issues")
    if isinstance(issues, str):
        issues = [issues]
    issues = [str(i) for i in (issues or [])]
    low = min(scores.values())
    status = "pass" if low >= PASS_MIN else "weak" if low >= WEAK_MIN else "fail"
    return {"status": status, "min_score": low, "scores": scores,
            "worst_turn": data.get("worst_turn"), "issues": issues}


async def judge_conversation(scenario: dict, transcript: list[dict], config: dict, tenant_id: str, *, llm_json=None) -> dict:
    if llm_json is None:
        from app.services.gemini_client import gemini_chat_completion_json as llm_json
    try:
        data = await llm_json(
            SYSTEM, build_user_prompt(scenario, transcript, config),
            model=JUDGE_MODEL, temperature=0.0, max_tokens=900, tenant_id=tenant_id, purpose="eval_judge",
        )
    except Exception as e:
        return {"status": "fail", "min_score": 0, "scores": {k: 0 for k in SCORE_KEYS},
                "worst_turn": None, "issues": [f"judge_error: {e}"]}
    return parse_verdict(data if isinstance(data, dict) else {})
