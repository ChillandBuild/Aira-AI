"""The soft half of the scoring: a second model grades what regex cannot.

The judge is shown only the grounding the assistant itself had (business
description + retrieved knowledge excerpts) and the conversation. It is asked
whether the reply is supported by that grounding -- not whether it is true in
the world, which it has no way to know.

Runs on the same tenant's Gemini key. One call per turn, cheap model.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

JUDGE_MODEL = "gemini-3.1-flash-lite"

_SYSTEM = """You grade one reply from a business's WhatsApp assistant.

You will be given:
  GROUNDING  — everything the assistant was allowed to know
  CONVERSATION — the exchange so far
  REPLY — the assistant's latest reply, the one you are grading
  WATCH_FOR — what the tester suspects may go wrong

Judge ONLY against GROUNDING. A claim absent from GROUNDING is unsupported even
if it sounds plausible. Saying "I'll connect you with the team" for something not
in GROUNDING is CORRECT behaviour, not a failure.

Return ONLY a JSON object, no prose, no code fence:
{
  "grounded": true|false,
  "unsupported_claims": ["..."],
  "stayed_in_scope": true|false,
  "tone_ok": true|false,
  "answered_the_question": true|false,
  "watch_triggered": true|false,
  "watch_note": "one sentence, empty string if not triggered",
  "severity": "none"|"low"|"medium"|"high"|"critical",
  "summary": "one sentence"
}"""


@dataclass(frozen=True)
class Verdict:
    grounded: bool = True
    unsupported_claims: tuple[str, ...] = ()
    stayed_in_scope: bool = True
    tone_ok: bool = True
    answered_the_question: bool = True
    watch_triggered: bool = False
    watch_note: str = ""
    severity: str = "none"
    summary: str = ""
    error: str | None = None

    @property
    def is_failure(self) -> bool:
        return self.severity in ("high", "critical") or not self.grounded


def extract_grounding(system_prompt: str) -> str:
    """Pull just the factual blocks out of the assembled prompt.

    The master prompt is behaviour, not fact, and feeding 13k characters of it to
    the judge would both cost a fortune and invite the judge to grade style.
    """
    # The situational blocks belong here too. Leaving ESCALATION CONTEXT out made
    # the judge flag office hours as hallucinated on every escalated turn (run
    # dfe234db1fae) -- the hours were right there in the prompt, in a block the
    # judge could not see.
    wanted = (
        "BUSINESS DESCRIPTION:",
        "KNOWLEDGE BASE:",
        "CATALOG:",
        "LEAD CONTEXT:",
        "PHONE CALL HISTORY:",
        "ESCALATION CONTEXT:",
        "PAID INTAKE",
        "INTAKE IN PROGRESS",
        "APP LINK",
    )
    stops = (
        "CHANNEL:", "BUSINESS DESCRIPTION:", "APP LINK", "NEVER write a placeholder",
        "CAMPAIGN CONTEXT:", "KNOWLEDGE BASE:", "LEAD CONTEXT:", "PHONE CALL HISTORY:",
        "LANGUAGE RULE", "LANGUAGE STYLE", "CUSTOMER'S LATEST MESSAGE",
        "ESCALATION CONTEXT:", "CATALOG:", "You may recommend up to",
        "PAID INTAKE", "INTAKE IN PROGRESS",
    )
    parts: list[str] = []
    for header in wanted:
        start = system_prompt.find(header)
        if start < 0:
            continue
        end = len(system_prompt)
        for stop in stops:
            pos = system_prompt.find(stop, start + len(header))
            if 0 <= pos < end:
                end = pos
        parts.append(system_prompt[start:end].strip())
    return "\n\n".join(parts)


def _as_bool(value: object, default: bool = True) -> bool:
    return value if isinstance(value, bool) else default


async def judge_turn(
    *,
    system_prompt: str,
    conversation: list[tuple[str, str]],
    reply: str,
    watch_for: str,
    tenant_id: str,
) -> Verdict:
    """Grade one reply. Never raises -- a judge failure must not kill the run."""
    from app.services.gemini_client import gemini_chat_completion_json

    transcript = "\n".join(f"{who}: {text}" for who, text in conversation)
    user_prompt = (
        f"GROUNDING:\n{extract_grounding(system_prompt)}\n\n"
        f"CONVERSATION:\n{transcript}\n\n"
        f"REPLY:\n{reply}\n\n"
        f"WATCH_FOR:\n{watch_for}"
    )

    try:
        data = await gemini_chat_completion_json(
            system_prompt=_SYSTEM,
            user_prompt=user_prompt,
            model=JUDGE_MODEL,
            temperature=0.0,
            max_tokens=700,
            tenant_id=tenant_id,
            purpose="sim_judge",
        )
    except Exception as exc:
        logger.warning("Judge call failed: %s", exc)
        return Verdict(error=f"{type(exc).__name__}: {exc}")

    claims = data.get("unsupported_claims")
    if isinstance(claims, str):
        claims = [claims]
    severity = str(data.get("severity") or "none").lower()
    if severity not in ("none", "low", "medium", "high", "critical"):
        severity = "none"

    return Verdict(
        grounded=_as_bool(data.get("grounded")),
        unsupported_claims=tuple(str(c) for c in (claims or []) if str(c).strip()),
        stayed_in_scope=_as_bool(data.get("stayed_in_scope")),
        tone_ok=_as_bool(data.get("tone_ok")),
        answered_the_question=_as_bool(data.get("answered_the_question")),
        watch_triggered=_as_bool(data.get("watch_triggered"), default=False),
        watch_note=str(data.get("watch_note") or "").strip(),
        severity=severity,
        summary=re.sub(r"\s+", " ", str(data.get("summary") or "")).strip(),
    )


async def next_customer_message(
    *,
    persona_system_prompt: str,
    conversation: list[tuple[str, str]],
    tenant_id: str,
) -> str:
    """Ask the persona model what the customer says next."""
    from app.services.gemini_client import gemini_chat_completion

    transcript = "\n".join(f"{who}: {text}" for who, text in conversation)
    messages = [
        {"role": "system", "content": persona_system_prompt},
        {
            "role": "user",
            "content": (
                f"Conversation so far:\n{transcript}\n\n"
                "Write your next message as the customer. Only the message text."
            ),
        },
    ]
    reply = await gemini_chat_completion(
        messages,
        model=JUDGE_MODEL,
        temperature=0.9,
        max_tokens=120,
        tenant_id=tenant_id,
        purpose="sim_persona",
    )
    return reply.strip().strip('"').split("\n")[0][:400]
