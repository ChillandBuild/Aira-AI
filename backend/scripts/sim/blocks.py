"""Split an assembled reply system prompt into its named blocks and size them.

Pure text helpers -- no I/O, no DB. The headers below are the literal strings
ai_reply.py writes when it concatenates the prompt; if a block is renamed there,
it falls into the preceding block here rather than being lost, so the totals stay
honest even when this list drifts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Literal header strings, in no particular order -- matched by position, not order.
# Each is the first line ai_reply.py appends for that section.
BLOCK_HEADERS: tuple[str, ...] = (
    "CHANNEL:",
    "BUSINESS DESCRIPTION:",
    "APP LINK (reference only):",
    "NEVER write a placeholder",
    "CAMPAIGN CONTEXT:",
    "KNOWLEDGE BASE:",
    "LEAD CONTEXT:",
    "PHONE CALL HISTORY:",
    "LANGUAGE RULE",
    "LANGUAGE STYLE",
    "CUSTOMER'S LATEST MESSAGE",
    "ESCALATION CONTEXT:",
    "CATALOG:",
    "You may recommend up to",
    "PAID INTAKE",
    "INTAKE IN PROGRESS",
)

# Everything before the first recognised header is the developer-owned master prompt.
MASTER_LABEL = "MASTER PROMPT"

# Rough conversion only. Gemini does not expose a local tokenizer, and the point of
# this number is relative weight between blocks, not billing accuracy.
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class Block:
    label: str
    chars: int

    @property
    def approx_tokens(self) -> int:
        return self.chars // CHARS_PER_TOKEN


def split_blocks(prompt: str) -> list[Block]:
    """Cut `prompt` at every known header. Sizes always sum to len(prompt)."""
    marks: list[tuple[int, str]] = []
    for header in BLOCK_HEADERS:
        for match in re.finditer(re.escape(header), prompt):
            marks.append((match.start(), header))
    marks.sort()

    # Drop headers nested inside an earlier block's body (e.g. the word CATALOG:
    # appearing again inside a client's description) -- only the first wins.
    deduped: list[tuple[int, str]] = []
    seen: set[str] = set()
    for pos, header in marks:
        if header in seen:
            continue
        seen.add(header)
        deduped.append((pos, header))

    blocks: list[Block] = []
    first = deduped[0][0] if deduped else len(prompt)
    if first > 0:
        blocks.append(Block(MASTER_LABEL, first))
    for i, (pos, header) in enumerate(deduped):
        end = deduped[i + 1][0] if i + 1 < len(deduped) else len(prompt)
        blocks.append(Block(header.rstrip(":"), end - pos))
    return blocks


def format_table(prompt: str) -> str:
    """One-block-per-line breakdown, largest share first, for the run report."""
    blocks = sorted(split_blocks(prompt), key=lambda b: b.chars, reverse=True)
    total = len(prompt) or 1
    lines = [f"TOTAL {total:,} chars (~{total // CHARS_PER_TOKEN:,} tokens)"]
    for block in blocks:
        share = 100 * block.chars / total
        lines.append(f"  {block.chars:7,} ch  {share:5.1f}%  {block.label}")
    return "\n".join(lines)
