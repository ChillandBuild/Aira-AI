# TeleCMI Call Scoring Phase 1 (Sort + Mark) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the TeleCMI call scorer (8 criteria, 0–10) with the client's CallIQ method, Steps 1–2: calls are sorted into four groups, and every real conversation is marked out of 100 on 10 fixed checks with a quoted proof per check.

**Architecture:** The stereo recording is split into telecaller (right) and customer (left) tracks. Each track is transcribed separately, so speakers and times are certain. Talk share (words) and interruptions (track overlap) are computed without AI. AI step A finds the 6 "real discussion" signs, and the system validates their quotes and counts them to pick the group. For real conversations, AI step B chooses a level for checks 1–9, and the system applies caps and computes all marks. Check 10 (wrap-up) is marked when the wrap-up is saved, or set to Missing after 2 hours. Warnings go to a new `call_alerts` table shown as an admin "Needs attention" list.

**Tech Stack:** FastAPI + Supabase (Python 3.12, unittest-style tests run with `python -m pytest`), Gemini via `app.services.gemini_client`, APScheduler, Next.js 14 + TypeScript + Tailwind.

**Spec:** `docs/superpowers/specs/2026-09-25-telecmi-call-scoring-phase1-design.md`

## Global Constraints

- TeleCMI only (`provider == "telecmi"`). SIM (`sim_basic`) code paths and the manual outcome marking must behave exactly as before.
- Telecaller = right channel (`TELECALLER_CHANNEL = 1`), customer = left channel.
- Group thresholds: very short `< 30` s of answered talk (`duration_seconds`); real conversation `>= 2` valid signs.
- Marks: opening 5, courtesy 10, questions 15, listening 10, product_info 15, doubts 10, clarity 10, next_step 10, decision 8, crm_update 7 (total 100). Level shares: excellent 1.0, good 0.75, partial 0.5, poor 0.25, missing 0.
- The AI only chooses levels; the system computes marks. Round the total to 1 decimal **only at the end**.
- All AI calls in this feature run at temperature 0.
- The wrap-up cut-off is 2 hours; after it, check 10 = missing.
- Quotes sent to the browser are clipped to 240 chars. The full transcript stays masked (`mask_transcript`, first/last line only).
- Warnings go to admins (tenant `owner`/`admin`), never "manager". Instant notifications are sent only for `rude` and `wrong_info`, max 1 per telecaller per hour. There is one morning summary at 09:00 IST.
- Removal is total: no dead code, no rollback copies (old criteria, tone, 7+3 scorer, no-answer flag).
- Backend tests run from `backend/`: `python -m pytest`. Frontend must pass **both** `npm run lint` and `npm run typecheck`.
- Commits use explicit pathspecs (`git commit -- <paths>`). Commit only; **no push** without the user's go-ahead.
- Migration `207` (column drops) is applied only **after** the new backend is deployed. Production must never select a dropped column.

## Review Focus

1. **Mono or unreadable recording** (TeleCMI sends a single-channel or non-WAV file): expect the mixed audio to be transcribed with the word-clue prompt, interruptions `None`, and the call still sorted and marked. Pinned in Task 4.
2. **The AI returns a quote that is not in the transcript, or attributes it to the wrong speaker**: expect that sign/proof to be ignored (sign) or flagged `proof_missing` (check). The group must never be decided by the AI's own claim. Pinned in Tasks 3 and 5.
3. **The wrap-up is saved before the recording is processed** (the telecaller is fast, the recording is slow): expect check 10 to be marked right after step B finishes, not lost. Pinned in Task 7.
4. **The wrap-up is changed after the score is final** (telecaller corrects the outcome an hour later): expect check 10 to be re-marked and the total recomputed; checks 1–9 unchanged. Pinned in Task 7.
5. **A call with fewer than 50 words, or near-silent tracks** (customer barely spoke): expect talk share `None` (no cap) and interruptions from tracks only, with no crash on empty segment lists. Pinned in Tasks 1 and 2.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/services/scoring_rules.py` (new) | Every Phase 1 threshold/constant in one place |
| `backend/app/services/call_tracks.py` (new) | Stereo split, voice-activity segments, interruption counting (no AI) |
| `backend/app/services/call_lines.py` (new) | `Line` model, transcript format/parse, `clock()` |
| `backend/app/services/call_metrics.py` (new) | Talk share, level caps, tips (no AI) |
| `backend/app/services/call_quotes.py` (new) | Find an AI quote in the transcript (speaker-aware, tolerant) |
| `backend/app/services/call_transcribe.py` (new) | Per-track transcription + merge + time snapping; mono fallback; swapped-track hint |
| `backend/app/services/call_sorting.py` (new) | AI step A, sign validation, group, early-exit check, call summary |
| `backend/app/services/call_marking.py` (new) | AI step B, caps, marks, top-2, check 10 (wrap-up) |
| `backend/app/services/call_alerts.py` (new) | Raise/list/count/seen alerts, instant-alert rate limit, morning summary, lead-source check |
| `backend/app/services/call_scorer.py` (rewrite) | Pure group/score-status rule + `finalize_call_score` |
| `backend/app/services/call_ai_pipeline.py` (modify) | Orchestrates the new flow |
| `backend/app/services/call_summarizer.py` (delete) | Replaced by `call_transcribe.py` + `call_sorting.py` + `call_marking.py` |
| `backend/app/services/call_audio.py` (modify) | Expose `decode_wav`, `split_pcm`; delete `audio_for_evaluation` |
| `backend/app/services/gemini_client.py` (modify) | `temperature` parameter; drop the unused `audio` param from `gemini_analysis_json` |
| `backend/app/routes/calls.py` (modify) | Card fields, wrap-up → check 10, alert routes, remove flag routes |
| `backend/app/routes/app_settings.py` (modify) | Remove `score_criteria` |
| `backend/app/services/telecaller_performance.py` (modify) | Check averages instead of criteria; volume on the 0–100 scale |
| `backend/app/main.py` (modify) | Wrap-up cut-off sweep + morning summary jobs |
| `backend/supabase/migrations/205_call_scoring_v4.sql` (new) | Add columns + `call_alerts` |
| `backend/supabase/migrations/207_drop_call_flags.sql` (new) | Drop old flag/breakdown columns (after deploy) |
| `frontend/lib/api.ts` (modify) | v4 types, alert API, remove flag API |
| `frontend/components/CallAi.tsx` (rewrite) | New call card |
| `frontend/app/dashboard/telecalling/components/sections/NeedsAttention.tsx` (new) | Admin list; replaces `FlaggedCalls.tsx` (deleted) |
| `frontend/components/sidebar.tsx` (modify) | Unseen-alerts badge on Dialer |
| `frontend/app/dashboard/settings/TelecallingConfigPanel.tsx` (modify) | Remove criteria picker |
| Score screens (modify) | `/10` → `/100` |

---

### Task 0: Branch

- [ ] **Step 1: Create the feature branch**

```bash
cd /c/Users/vskee/Desktop/Aira-Ai && git checkout -b feat/telecmi-scoring-v4
```

---

### Task 1: Rules + two-track audio analysis (no AI)

**Files:**
- Create: `backend/app/services/scoring_rules.py`
- Create: `backend/app/services/call_tracks.py`
- Modify: `backend/app/services/call_audio.py` (add public `decode_wav`, `split_pcm`)
- Test: `backend/tests/test_call_tracks.py`

**Interfaces:**
- Produces: `scoring_rules.*` constants; `call_audio.decode_wav(data) -> tuple[bytes, int, int] | None`; `call_audio.split_pcm(pcm, sample_rate, channels) -> list[AudioChunk]`; `call_tracks.NotStereo`; `call_tracks.split_stereo(audio_bytes) -> tuple[bytes, bytes, int]` returning `(telecaller_pcm16, customer_pcm16, sample_rate)`; `call_tracks.speech_segments(pcm16: bytes, sample_rate: int) -> list[tuple[float, float]]`; `call_tracks.count_interruptions(telecaller_segs, customer_segs) -> int`; `call_tracks.per_5_min(count: int | None, duration_s: float | None) -> float | None`.

- [ ] **Step 1: Write `scoring_rules.py`**

```python
"""Every Phase 1 call-scoring threshold. Phase 6 turns these into admin settings."""

RULES_VERSION = "v1"

# Step 1 — sorting
MIN_SCORED_SECONDS = 30
MIN_SIGNS = 2

# Two-track audio (TeleCMI stereo: right = telecaller, left = customer)
TELECALLER_CHANNEL = 1
FRAME_SECONDS = 0.1
SPEECH_MIN_LEVEL = 300          # mean |sample| a frame must reach to count as speech
NOISE_FLOOR_MULTIPLIER = 4      # speech must be this many times the track's own quiet level
MIN_SPEECH_RUN_S = 0.2
MERGE_GAP_S = 0.3
OVERLAP_MIN_S = 1.0
TELECALLER_RUN_MIN_S = 1.0
SNAP_WINDOW_S = 3.0

# Talk share / interruptions (defaults from the method document)
TALK_SHARE_MIN_WORDS = 50
TALK_SHARE_PASSIVE = 30
TALK_SHARE_HEALTHY_MAX = 65
TALK_SHARE_HIGH_MAX = 75
INTERRUPTIONS_GOOD_MAX = 1
INTERRUPTIONS_SOMETIMES_MAX = 3

# Step 2 — marking
CHECK_MARKS = {
    "opening": 5, "courtesy": 10, "questions": 15, "listening": 10, "product_info": 15,
    "doubts": 10, "clarity": 10, "next_step": 10, "decision": 8, "crm_update": 7,
}
LEVEL_SHARE = {"excellent": 1.0, "good": 0.75, "partial": 0.5, "poor": 0.25, "missing": 0.0}
LEVEL_ORDER = ("missing", "poor", "partial", "good", "excellent")
WRAPUP_CUTOFF_HOURS = 2
QUOTE_MAX_CHARS = 240

# Warnings
ALERT_RATE_LIMIT_PER_HOUR = 1
LEAD_SOURCE_MIN_CALLS = 10
LEAD_SOURCE_BAD_RATE = 0.30
MORNING_SUMMARY_HOUR_IST = 9
```

- [ ] **Step 2: Write the failing tests** (`backend/tests/test_call_tracks.py`)

```python
"""Two-track audio analysis: stereo split, speech segments, interruptions."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_tracks as ct

RATE = 8000


def _tone(seconds: float, level: int) -> list[int]:
    n = int(seconds * RATE)
    return [level if i % 2 else -level for i in range(n)]


def _wav(left: list[int], right: list[int] | None = None) -> bytes:
    channels = 1 if right is None else 2
    if right is None:
        samples = left
    else:
        samples = [s for pair in zip(left, right) for s in pair]
    data = struct.pack(f"<{len(samples)}h", *samples)
    fmt = struct.pack("<HHIIHH", 1, channels, RATE, RATE * 2 * channels, 2 * channels, 16)
    return b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data


def _pcm(samples: list[int]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


class SplitStereoTests(unittest.TestCase):
    def test_right_channel_is_telecaller(self):
        left = _tone(1, 100)
        right = _tone(1, 2000)
        tele, cust, rate = ct.split_stereo(_wav(left, right))
        self.assertEqual(rate, RATE)
        self.assertEqual(struct.unpack_from("<h", tele, 2)[0], 2000)
        self.assertEqual(struct.unpack_from("<h", cust, 2)[0], 100)

    def test_mono_raises_not_stereo(self):
        with self.assertRaises(ct.NotStereo):
            ct.split_stereo(_wav(_tone(1, 100)))

    def test_non_wav_raises_not_stereo(self):
        with self.assertRaises(ct.NotStereo):
            ct.split_stereo(b"ID3not-a-wav")


class SpeechSegmentTests(unittest.TestCase):
    def test_finds_speech_between_silence(self):
        samples = _tone(1, 5) + _tone(2, 3000) + _tone(1, 5)
        segs = ct.speech_segments(_pcm(samples), RATE)
        self.assertEqual(len(segs), 1)
        self.assertAlmostEqual(segs[0][0], 1.0, delta=0.11)
        self.assertAlmostEqual(segs[0][1], 3.0, delta=0.11)

    def test_steady_hiss_is_not_speech(self):
        samples = _tone(5, 400)
        self.assertEqual(ct.speech_segments(_pcm(samples), RATE), [])

    def test_speech_over_hiss_is_found(self):
        samples = _tone(2, 400) + _tone(1, 4000) + _tone(2, 400)
        segs = ct.speech_segments(_pcm(samples), RATE)
        self.assertEqual(len(segs), 1)

    def test_short_gap_is_merged(self):
        samples = _tone(1, 3000) + _tone(0.2, 5) + _tone(1, 3000) + _tone(1, 5)
        self.assertEqual(len(ct.speech_segments(_pcm(samples), RATE)), 1)

    def test_empty_audio(self):
        self.assertEqual(ct.speech_segments(b"", RATE), [])


class InterruptionTests(unittest.TestCase):
    def test_counts_long_overlap_while_customer_speaks(self):
        self.assertEqual(ct.count_interruptions([(3.0, 6.0)], [(0.0, 5.0)]), 1)

    def test_short_overlap_not_counted(self):
        self.assertEqual(ct.count_interruptions([(4.5, 8.0)], [(0.0, 5.0)]), 0)

    def test_backchannel_not_counted(self):
        # telecaller says "hmm" for 0.6s inside the customer's turn
        self.assertEqual(ct.count_interruptions([(2.0, 2.6)], [(0.0, 5.0)]), 0)

    def test_customer_interrupting_telecaller_not_counted(self):
        self.assertEqual(ct.count_interruptions([(0.0, 5.0)], [(3.0, 6.0)]), 0)

    def test_no_segments(self):
        self.assertEqual(ct.count_interruptions([], []), 0)

    def test_per_5_min(self):
        self.assertEqual(ct.per_5_min(4, 600), 2.0)
        self.assertIsNone(ct.per_5_min(None, 600))
        self.assertIsNone(ct.per_5_min(2, 0))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `cd backend && python -m pytest tests/test_call_tracks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.call_tracks'`

- [ ] **Step 4: Add the public helpers to `call_audio.py`**

Add right after `_decode_wav` (keep `_decode_wav` itself; `split_audio` uses it):

```python
def decode_wav(data: bytes) -> tuple[bytes, int, int] | None:
    """Public: (interleaved PCM16 little-endian, sample_rate, channels), or None if not a usable WAV."""
    return _decode_wav(data)
```

Add right after `split_audio`:

```python
def split_pcm(pcm: bytes, sample_rate: int, channels: int) -> list[AudioChunk]:
    """Transcribable MP3 pieces from raw PCM16, using the same length rules as split_audio."""
    total = len(pcm) / (sample_rate * 2 * channels)
    limit = CHUNK_SECONDS if total > SINGLE_PASS_SECONDS else total
    return _split_wav(pcm, sample_rate, channels, max(limit, 1))
```

- [ ] **Step 5: Write `call_tracks.py`**

```python
"""TeleCMI records each person on their own channel: right = telecaller, left = customer.

Everything here is plain signal counting — no AI, same answer every run.
"""
from array import array

from app.services.call_audio import decode_wav
from app.services.scoring_rules import (
    FRAME_SECONDS, MERGE_GAP_S, MIN_SPEECH_RUN_S, NOISE_FLOOR_MULTIPLIER, OVERLAP_MIN_S,
    SPEECH_MIN_LEVEL, TELECALLER_CHANNEL, TELECALLER_RUN_MIN_S,
)

Segment = tuple[float, float]


class NotStereo(Exception):
    """The recording isn't a two-channel WAV, so the speakers can't be separated by channel."""


def split_stereo(audio_bytes: bytes) -> tuple[bytes, bytes, int]:
    """(telecaller_pcm16, customer_pcm16, sample_rate) from a stereo WAV."""
    decoded = decode_wav(audio_bytes)
    if not decoded or decoded[2] != 2:
        raise NotStereo("recording is not a two-channel WAV")
    pcm, rate, _ = decoded
    samples = array("h")
    samples.frombytes(pcm)
    tele = samples[TELECALLER_CHANNEL::2]
    cust = samples[1 - TELECALLER_CHANNEL::2]
    return tele.tobytes(), cust.tobytes(), rate


def _frame_levels(pcm16: bytes, sample_rate: int) -> list[float]:
    samples = array("h")
    samples.frombytes(pcm16[: len(pcm16) - (len(pcm16) % 2)])
    size = max(1, int(sample_rate * FRAME_SECONDS))
    return [
        sum(abs(s) for s in samples[i:i + size]) / len(samples[i:i + size])
        for i in range(0, len(samples), size)
    ]


def speech_segments(pcm16: bytes, sample_rate: int) -> list[Segment]:
    """Stretches where this track's speaker is talking, in seconds.

    The threshold adapts to the track's own quiet level, so steady line hiss
    never reads as speech.
    """
    levels = _frame_levels(pcm16, sample_rate)
    if not levels:
        return []
    floor = sorted(levels)[len(levels) // 10]
    threshold = max(SPEECH_MIN_LEVEL, floor * NOISE_FLOOR_MULTIPLIER)

    runs: list[list[float]] = []
    for i, level in enumerate(levels):
        if level < threshold:
            continue
        start, end = i * FRAME_SECONDS, (i + 1) * FRAME_SECONDS
        if runs and start - runs[-1][1] <= MERGE_GAP_S:
            runs[-1][1] = end
        else:
            runs.append([start, end])
    return [(round(s, 2), round(e, 2)) for s, e in runs if e - s >= MIN_SPEECH_RUN_S]


def count_interruptions(telecaller: list[Segment], customer: list[Segment]) -> int:
    """Times the telecaller started talking while the customer was still speaking.

    Counted only when both talked together for OVERLAP_MIN_S and the telecaller kept
    going for TELECALLER_RUN_MIN_S — so a quick "hmm / ok" is listening, not interrupting.
    """
    count = 0
    for t_start, t_end in telecaller:
        if t_end - t_start < TELECALLER_RUN_MIN_S:
            continue
        for c_start, c_end in customer:
            if c_start < t_start < c_end and min(t_end, c_end) - t_start >= OVERLAP_MIN_S:
                count += 1
                break
    return count


def per_5_min(count: int | None, duration_s: float | None) -> float | None:
    if count is None or not duration_s:
        return None
    return round(count / (duration_s / 60) * 5, 2)
```

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `cd backend && python -m pytest tests/test_call_tracks.py tests/test_call_audio.py -v`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/scoring_rules.py backend/app/services/call_tracks.py backend/app/services/call_audio.py backend/tests/test_call_tracks.py
git commit -m "feat(calls): two-track speech segments and interruption counting" -- backend/app/services/scoring_rules.py backend/app/services/call_tracks.py backend/app/services/call_audio.py backend/tests/test_call_tracks.py
```

---

### Task 2: Transcript lines, talk share, caps, tips (no AI)

**Files:**
- Create: `backend/app/services/call_lines.py`
- Create: `backend/app/services/call_metrics.py`
- Test: `backend/tests/test_call_metrics.py`

**Interfaces:**
- Produces: `call_lines.Line(start: float, speaker: Literal["telecaller","customer"], text: str)` (frozen dataclass); `call_lines.clock(seconds: float) -> str` (`"01:12"`); `call_lines.format_transcript(lines) -> str`; `call_lines.parse_transcript(text) -> list[Line]`; `call_metrics.talk_share(lines) -> float | None`; `call_metrics.listening_cap(talk_share, ipm) -> str`; `call_metrics.courtesy_cap(ipm) -> str`; `call_metrics.lower_level(a, b) -> str`; `call_metrics.tips(talk_share, ipm) -> list[str]`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_call_metrics.py`)

```python
"""Transcript lines, talk share by words, and the level caps from the method document."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.call_lines import Line, clock, format_transcript, parse_transcript
from app.services import call_metrics as cm


def _words(n: int, word: str = "word") -> str:
    return " ".join([word] * n)


class LineFormatTests(unittest.TestCase):
    def test_round_trip(self):
        lines = [Line(72.4, "customer", "We have two branches actually."), Line(75.0, "telecaller", "Okay sir.")]
        text = format_transcript(lines)
        self.assertEqual(text.splitlines()[0], "[01:12] Customer: We have two branches actually.")
        self.assertEqual(parse_transcript(text), [Line(72.0, "customer", "We have two branches actually."), Line(75.0, "telecaller", "Okay sir.")])

    def test_legacy_lines_without_time(self):
        self.assertEqual(parse_transcript("Telecaller: Hello."), [Line(0.0, "telecaller", "Hello.")])

    def test_clock(self):
        self.assertEqual(clock(0), "00:00")
        self.assertEqual(clock(160.9), "02:40")


class TalkShareTests(unittest.TestCase):
    def test_document_example_65(self):
        lines = [Line(0, "telecaller", _words(650)), Line(1, "customer", _words(350))]
        self.assertEqual(cm.talk_share(lines), 65.0)

    def test_fillers_ignored(self):
        lines = [Line(0, "telecaller", _words(30) + " hmm uh aah"), Line(1, "customer", _words(30)), Line(2, "customer", "ok ok")]
        self.assertEqual(cm.talk_share(lines), 50.0)

    def test_tamil_words_count_as_words(self):
        lines = [Line(0, "telecaller", "சரி சார் நான் அனுப்புறேன் " * 10), Line(1, "customer", "ok thanks " * 10)]
        self.assertAlmostEqual(cm.talk_share(lines), 66.67, places=2)

    def test_under_50_words_is_none(self):
        self.assertIsNone(cm.talk_share([Line(0, "telecaller", _words(20)), Line(1, "customer", _words(20))]))


class CapTests(unittest.TestCase):
    def test_listening_caps(self):
        self.assertEqual(cm.listening_cap(64, 0.5), "excellent")
        self.assertEqual(cm.listening_cap(64, 1.25), "good")      # document full example
        self.assertEqual(cm.listening_cap(70, 0.5), "good")
        self.assertEqual(cm.listening_cap(80, 0.5), "partial")
        self.assertEqual(cm.listening_cap(60, 4), "partial")
        self.assertEqual(cm.listening_cap(80, 4), "poor")
        self.assertEqual(cm.listening_cap(None, None), "excellent")

    def test_courtesy_cap(self):
        self.assertEqual(cm.courtesy_cap(3), "excellent")
        self.assertEqual(cm.courtesy_cap(3.5), "good")
        self.assertEqual(cm.courtesy_cap(None), "excellent")

    def test_lower_level(self):
        self.assertEqual(cm.lower_level("excellent", "good"), "good")
        self.assertEqual(cm.lower_level("poor", "good"), "poor")

    def test_tips(self):
        self.assertEqual(cm.tips(60, 0.5), [])
        self.assertIn("Let the customer speak more. Aim to talk less than 65% of the time.", cm.tips(72, 0.5))
        self.assertIn("Let the customer finish before you reply.", cm.tips(60, 2))
        self.assertIn("Guide the conversation more: ask questions and explain the next step.", cm.tips(25, 0))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd backend && python -m pytest tests/test_call_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `call_lines.py`**

```python
"""One transcript line: when it started, who said it, what was said."""
import re
from dataclasses import dataclass
from typing import Literal

Speaker = Literal["telecaller", "customer"]
_LABEL = {"telecaller": "Telecaller", "customer": "Customer"}
_LINE_RE = re.compile(r"^(?:\[(\d+):(\d{2})\]\s*)?(Telecaller|Customer):\s*(.*)$")


@dataclass(frozen=True)
class Line:
    start: float
    speaker: Speaker
    text: str


def clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def format_transcript(lines: list[Line]) -> str:
    return "\n".join(f"[{clock(l.start)}] {_LABEL[l.speaker]}: {l.text}" for l in lines)


def parse_transcript(text: str | None) -> list[Line]:
    out: list[Line] = []
    for raw in (text or "").splitlines():
        m = _LINE_RE.match(raw.strip())
        if not m:
            continue
        minutes, secs, label, body = m.groups()
        start = float(int(minutes) * 60 + int(secs)) if minutes is not None else 0.0
        out.append(Line(start, "telecaller" if label == "Telecaller" else "customer", body.strip()))
    return out
```

- [ ] **Step 4: Write `call_metrics.py`**

```python
"""Talk share (by words) and the caps the two numbers put on Listening and Courtesy."""
from app.services.call_lines import Line
from app.services.scoring_rules import (
    INTERRUPTIONS_GOOD_MAX, INTERRUPTIONS_SOMETIMES_MAX, LEVEL_ORDER, TALK_SHARE_HEALTHY_MAX,
    TALK_SHARE_HIGH_MAX, TALK_SHARE_MIN_WORDS, TALK_SHARE_PASSIVE,
)

_FILLERS = {
    "hmm", "hm", "hmmm", "mm", "mmm", "uh", "uhh", "um", "umm", "aah", "ah", "aa", "haan",
    "ம்ம்", "ம்", "ஆ", "ஆஆ", "ஹ்ம்",
}
_OK = {"ok", "okay"}
_STRIP = ".,!?…\"'()[]:;-—"


def _count_words(text: str) -> int:
    tokens = [t.strip(_STRIP).lower() for t in text.split()]
    tokens = [t for t in tokens if t and t not in _FILLERS]
    if tokens and all(t in _OK for t in tokens):
        return 0  # "ok ok" on its own is a filler
    return len(tokens)


def talk_share(lines: list[Line]) -> float | None:
    """Telecaller's share of all words spoken, 0-100. None when too few words to mean anything."""
    tele = sum(_count_words(l.text) for l in lines if l.speaker == "telecaller")
    cust = sum(_count_words(l.text) for l in lines if l.speaker == "customer")
    total = tele + cust
    if total < TALK_SHARE_MIN_WORDS:
        return None
    return round(tele / total * 100, 2)


def lower_level(a: str, b: str) -> str:
    return a if LEVEL_ORDER.index(a) <= LEVEL_ORDER.index(b) else b


def listening_cap(share: float | None, ipm: float | None) -> str:
    high_share = share is not None and share > TALK_SHARE_HIGH_MAX
    mid_share = share is not None and share > TALK_SHARE_HEALTHY_MAX
    high_int = ipm is not None and ipm > INTERRUPTIONS_SOMETIMES_MAX
    mid_int = ipm is not None and ipm > INTERRUPTIONS_GOOD_MAX
    if high_share and high_int:
        return "poor"
    if high_share or high_int:
        return "partial"
    if mid_share or mid_int:
        return "good"
    return "excellent"


def courtesy_cap(ipm: float | None) -> str:
    return "good" if ipm is not None and ipm > INTERRUPTIONS_SOMETIMES_MAX else "excellent"


def tips(share: float | None, ipm: float | None) -> list[str]:
    out = []
    if share is not None and share > TALK_SHARE_HEALTHY_MAX:
        out.append(f"Let the customer speak more. Aim to talk less than {TALK_SHARE_HEALTHY_MAX}% of the time.")
    if share is not None and share < TALK_SHARE_PASSIVE:
        out.append("Guide the conversation more: ask questions and explain the next step.")
    if ipm is not None and ipm > INTERRUPTIONS_GOOD_MAX:
        out.append("Let the customer finish before you reply.")
    return out
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `cd backend && python -m pytest tests/test_call_metrics.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/call_lines.py backend/app/services/call_metrics.py backend/tests/test_call_metrics.py
git commit -m "feat(calls): transcript lines, talk share and listening/courtesy caps" -- backend/app/services/call_lines.py backend/app/services/call_metrics.py backend/tests/test_call_metrics.py
```

---

### Task 3: Quote finder

**Files:**
- Create: `backend/app/services/call_quotes.py`
- Test: `backend/tests/test_call_quotes.py`

**Interfaces:**
- Consumes: `call_lines.Line`
- Produces: `call_quotes.find_quote(quote: str | None, lines: list[Line], speakers: tuple[str, ...] = ("telecaller", "customer")) -> Line | None`; `call_quotes.clip(text: str | None) -> str | None`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_call_quotes.py`)

```python
"""An AI quote only counts if it's really in the transcript, from the right person."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.call_lines import Line
from app.services.call_quotes import clip, find_quote

LINES = [
    Line(5.0, "telecaller", "Our plan includes GST billing and stock tracking."),
    Line(12.0, "customer", "How much is the yearly plan?"),
    Line(20.0, "customer", "ஸ்கோரிங் இப்பதான் நான் அந்த டூல் காலிங் மட்டும் பண்ற மாதிரி"),
]


class FindQuoteTests(unittest.TestCase):
    def test_exact_substring(self):
        self.assertEqual(find_quote("How much is the yearly plan", LINES).start, 12.0)

    def test_punctuation_and_case_ignored(self):
        self.assertEqual(find_quote("our plan includes GST billing, and stock tracking", LINES).start, 5.0)

    def test_fabricated_quote_rejected(self):
        self.assertIsNone(find_quote("We offer a free trial for 30 days", LINES))

    def test_wrong_speaker_rejected(self):
        self.assertIsNone(find_quote("How much is the yearly plan", LINES, speakers=("telecaller",)))

    def test_small_spelling_difference_tolerated(self):
        self.assertEqual(find_quote("ஸ்கோரிங் இப்ப தான் நான் அந்த டூல் காலிங் மட்டும்", LINES).start, 20.0)

    def test_empty_quote(self):
        self.assertIsNone(find_quote("", LINES))
        self.assertIsNone(find_quote(None, LINES))

    def test_clip(self):
        self.assertEqual(len(clip("x" * 500)), 240)
        self.assertIsNone(clip(None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd backend && python -m pytest tests/test_call_quotes.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `call_quotes.py`**

```python
"""Match an AI-supplied quote back to a real transcript line.

Matching ignores case, punctuation and spacing, and tolerates small spelling
differences (the AI often re-spells Tamil slightly), but a quote that isn't
substantially present in one line from an allowed speaker is rejected.
"""
import unicodedata
from difflib import SequenceMatcher

from app.services.call_lines import Line
from app.services.scoring_rules import QUOTE_MAX_CHARS

_MATCH_RATIO = 0.85


def _norm(text: str) -> str:
    kept = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text.lower())
    return "".join(kept.split())


def clip(text: str | None) -> str | None:
    if text is None:
        return None
    return text if len(text) <= QUOTE_MAX_CHARS else text[: QUOTE_MAX_CHARS - 1].rstrip() + "…"


def find_quote(quote: str | None, lines: list[Line], speakers: tuple[str, ...] = ("telecaller", "customer")) -> Line | None:
    q = _norm(quote or "")
    if len(q) < 2:
        return None
    for line in lines:
        if line.speaker not in speakers:
            continue
        body = _norm(line.text)
        if q in body:
            return line
        match = SequenceMatcher(None, q, body, autojunk=False).find_longest_match(0, len(q), 0, len(body))
        if match.size / len(q) >= _MATCH_RATIO:
            return line
        if SequenceMatcher(None, q, body, autojunk=False).ratio() >= _MATCH_RATIO and len(q) >= len(body) * 0.6:
            return line
    return None
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && python -m pytest tests/test_call_quotes.py -v`
Expected: PASS. If `test_small_spelling_difference_tolerated` fails, the difference is the inserted space inside `இப்ப தான்`. `_norm` removes all whitespace, so it must match as a substring. Fix `_norm`, not the test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/call_quotes.py backend/tests/test_call_quotes.py
git commit -m "feat(calls): speaker-aware quote matching for AI proof" -- backend/app/services/call_quotes.py backend/tests/test_call_quotes.py
```

---

### Task 4: Per-track transcription

**Files:**
- Create: `backend/app/services/call_transcribe.py`
- Modify: `backend/app/services/gemini_client.py` (`temperature` param on `gemini_transcribe_audio` and `gemini_analysis_json`; remove the `audio` param from `gemini_analysis_json`)
- Test: `backend/tests/test_call_transcribe.py`

**Interfaces:**
- Consumes: `call_tracks.split_stereo`, `speech_segments`, `NotStereo`; `call_audio.split_audio`, `split_pcm`, `resplit_chunk`, `AudioChunk`; `call_lines.Line`; `gemini_client.gemini_transcribe_audio(..., temperature=0.0)`
- Produces: `call_transcribe.TranscriptionIncomplete`; `call_transcribe.TrackTranscript(lines: list[Line], telecaller_segments: list[Segment], customer_segments: list[Segment], stereo: bool)`; `async call_transcribe.transcribe_tracks(audio: bytes, mime_type: str, tenant_id: str | None) -> TrackTranscript`; `call_transcribe.parse_track_text(text: str, speaker: str, offset: float) -> list[Line]`; `call_transcribe.snap(lines, segments) -> list[Line]`; `call_transcribe.tracks_look_swapped(lines, company_name: str | None) -> bool`.

- [ ] **Step 1: Add `temperature` to the Gemini helpers**

In `gemini_client.py`, `gemini_transcribe_audio`: add the parameter `temperature: float = 0.1,` after `purpose`, and use `"temperature": temperature,` in `generation_config`.

In `gemini_analysis_json`: remove the `audio` parameter and its loop. The content becomes `[{"type": "text", "text": user_prompt}]`. Add `temperature: float = 0.2,` after `purpose` and use it in `generation_config`. Update the docstring to: `"""JSON completion with prompt-only JSON discipline and a single retry."""`. First confirm nothing else passes `audio=`:

Run: `cd backend && grep -rn "gemini_analysis_json" app | grep -v "def gemini_analysis_json"`
Expected: only `call_summarizer.py` (deleted in Task 8) and the new modules.

- [ ] **Step 2: Write the failing tests** (`backend/tests/test_call_transcribe.py`)

```python
"""Per-track transcription: certain speakers, times from the audio, mono fallback."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_transcribe as tr
from app.services.call_audio import AudioChunk
from app.services.call_lines import Line
from app.services.call_tracks import NotStereo


class ParseTrackTextTests(unittest.TestCase):
    def test_times_are_offset_by_piece_start(self):
        lines = tr.parse_track_text("[00:05] Hello sir\n[01:10] Thank you", "telecaller", offset=300.0)
        self.assertEqual(lines, [Line(305.0, "telecaller", "Hello sir"), Line(370.0, "telecaller", "Thank you")])

    def test_untimed_text_kept_at_offset(self):
        self.assertEqual(tr.parse_track_text("Hello", "customer", 0.0), [Line(0.0, "customer", "Hello")])

    def test_blank_lines_skipped(self):
        self.assertEqual(tr.parse_track_text("\n\n", "customer", 0.0), [])


class SnapTests(unittest.TestCase):
    def test_snaps_to_nearest_segment_start_within_window(self):
        lines = [Line(10.0, "telecaller", "a")]
        self.assertEqual(tr.snap(lines, [(8.4, 12.0), (30.0, 31.0)])[0].start, 8.4)

    def test_keeps_ai_time_when_nothing_close(self):
        lines = [Line(10.0, "telecaller", "a")]
        self.assertEqual(tr.snap(lines, [(30.0, 31.0)])[0].start, 10.0)


class SwappedTracksTests(unittest.TestCase):
    def test_company_name_only_on_customer_track(self):
        lines = [Line(0, "customer", "Hello, I'm calling from Aira Softwares"), Line(3, "telecaller", "Yes tell me")]
        self.assertTrue(tr.tracks_look_swapped(lines, "Aira Softwares"))

    def test_normal_call_not_swapped(self):
        lines = [Line(0, "telecaller", "Calling from Aira Softwares"), Line(3, "customer", "Yes")]
        self.assertFalse(tr.tracks_look_swapped(lines, "Aira Softwares"))

    def test_no_clues_anywhere_not_swapped(self):
        self.assertFalse(tr.tracks_look_swapped([Line(0, "telecaller", "hello")], None))


class TranscribeTracksTests(unittest.IsolatedAsyncioTestCase):
    async def test_stereo_merges_both_tracks_in_time_order(self):
        async def fake(data, mime, prompt, **kw):
            return ("[00:02] Hello" if data == b"T" else "[00:01] Who is this?\n[00:05] Okay"), True

        with patch.object(tr, "split_stereo", return_value=(b"tele", b"cust", 8000)), \
             patch.object(tr, "speech_segments", return_value=[]), \
             patch.object(tr, "split_pcm", side_effect=lambda pcm, r, c: [AudioChunk(b"T" if pcm == b"tele" else b"C", "audio/mpeg", 0.0, 10.0)]), \
             patch.object(tr, "gemini_transcribe_audio", AsyncMock(side_effect=fake)):
            result = await tr.transcribe_tracks(b"wav", "audio/wav", tenant_id="t")
        self.assertTrue(result.stereo)
        self.assertEqual([(l.start, l.speaker) for l in result.lines], [(1.0, "customer"), (2.0, "telecaller"), (5.0, "customer")])

    async def test_mono_falls_back_to_labelled_single_pass(self):
        gemini = AsyncMock(return_value=("[00:01] Telecaller: Calling from Aira\n[00:04] Customer: Yes", True))
        with patch.object(tr, "split_stereo", side_effect=NotStereo("mono")), \
             patch.object(tr, "split_audio", return_value=[AudioChunk(b"M", "audio/mpeg", 0.0, 10.0)]), \
             patch.object(tr, "gemini_transcribe_audio", gemini):
            result = await tr.transcribe_tracks(b"mp3", "audio/mpeg", tenant_id="t")
        self.assertFalse(result.stereo)
        self.assertEqual([l.speaker for l in result.lines], ["telecaller", "customer"])
        self.assertIn("company name", gemini.call_args.args[2])

    async def test_cut_off_piece_that_cannot_split_raises(self):
        with patch.object(tr, "split_stereo", return_value=(b"tele", b"cust", 8000)), \
             patch.object(tr, "speech_segments", return_value=[]), \
             patch.object(tr, "split_pcm", return_value=[AudioChunk(b"T", "audio/mpeg", 0.0, 10.0)]), \
             patch.object(tr, "resplit_chunk", return_value=None), \
             patch.object(tr, "gemini_transcribe_audio", AsyncMock(return_value=("[00:01] Hel", False))):
            with self.assertRaises(tr.TranscriptionIncomplete):
                await tr.transcribe_tracks(b"wav", "audio/wav", tenant_id="t")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `cd backend && python -m pytest tests/test_call_transcribe.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Write `call_transcribe.py`**

```python
"""Transcribe each voice track on its own, so every line's speaker is certain.

TeleCMI records the telecaller on the right channel and the customer on the left.
Guessing speakers from a mixed recording swapped them on a real call (2026-09-25),
so the tracks are split, transcribed separately, and merged by time. A recording
without two channels falls back to one labelled pass that identifies the telecaller
by what they say (company name, "calling from", explaining the product).
"""
import logging
import re
from dataclasses import dataclass, field, replace

from app.services.call_audio import AudioChunk, resplit_chunk, split_audio, split_pcm
from app.services.call_lines import Line, clock, parse_transcript
from app.services.call_tracks import NotStereo, Segment, speech_segments, split_stereo
from app.services.gemini_client import gemini_transcribe_audio
from app.services.scoring_rules import SNAP_WINDOW_S

logger = logging.getLogger(__name__)

_TIMED_RE = re.compile(r"^\[(\d+):(\d{2})\]\s*(.*)$")
_CLUE_PHRASES = ("calling from", "call from", "i am calling", "i'm calling", "பேசுறேன்", "பேசுகிறேன்", "கம்பெனி")


class TranscriptionIncomplete(Exception):
    """A piece of the recording kept coming back cut off and could not be cut smaller."""


@dataclass
class TrackTranscript:
    lines: list[Line]
    telecaller_segments: list[Segment] = field(default_factory=list)
    customer_segments: list[Segment] = field(default_factory=list)
    stereo: bool = True


_TRACK_PROMPT = (
    "This audio is ONE side of a phone call: only one person's voice is on it. "
    "Transcribe everything this person says, completely and verbatim, in the language and "
    "script they used (Tamil, Hindi, English or a mix). Do not translate or summarise.\n"
    "Put each utterance on its own line, starting with its start time in the audio as [mm:ss], "
    "e.g. '[00:07] Hello sir'. If a stretch is unclear, write [inaudible]. If nobody speaks, "
    "return nothing. Return only the transcript."
)

_MIXED_PROMPT = (
    "Transcribe this phone call recording completely and verbatim, in the language and script "
    "each speaker used (Tamil, Hindi, English or a mix). Do not translate or summarise.\n"
    "Put each speaker turn on its own line as '[mm:ss] Telecaller: …' or '[mm:ss] Customer: …'. "
    "Decide who the telecaller is by what they say: the telecaller says the company name, says "
    "they are calling from somewhere, introduces themselves, refers to the customer's enquiry, "
    "or explains the product and its price. The customer is the one asking about it.\n"
    "If a stretch is unclear, write [inaudible]. If there is no speech, return nothing. "
    "Return only the transcript."
)


def _later_piece(prompt: str, chunk: AudioChunk) -> str:
    if chunk.start_seconds <= 0:
        return prompt
    return prompt + (
        f"\nThis audio is a later piece of the same call, starting {clock(chunk.start_seconds)} into it. "
        "Give times relative to the start of THIS piece."
    )


def parse_track_text(text: str, speaker: str, offset: float) -> list[Line]:
    out = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        m = _TIMED_RE.match(raw)
        if m:
            out.append(Line(offset + int(m.group(1)) * 60 + int(m.group(2)), speaker, m.group(3).strip()))
        else:
            out.append(Line(offset, speaker, raw))
    return [l for l in out if l.text]


def snap(lines: list[Line], segments: list[Segment]) -> list[Line]:
    """Move each line's AI-given time to the nearest real speech start on its own track."""
    starts = [s for s, _ in segments]
    out = []
    for line in lines:
        near = min(starts, key=lambda s: abs(s - line.start), default=None)
        if near is not None and abs(near - line.start) <= SNAP_WINDOW_S:
            line = replace(line, start=float(near))
        out.append(line)
    return out


async def _transcribe_pieces(pieces: list[AudioChunk], prompt: str, tenant_id: str | None) -> list[tuple[str, float]]:
    pending = list(pieces)
    out: list[tuple[str, float]] = []
    while pending:
        chunk = pending.pop(0)
        text, complete = await gemini_transcribe_audio(
            chunk.data, chunk.mime_type, _later_piece(prompt, chunk), tenant_id=tenant_id, temperature=0.0,
        )
        if not complete:
            smaller = resplit_chunk(chunk)
            if not smaller:
                raise TranscriptionIncomplete(f"transcript cut off in the piece starting at {clock(chunk.start_seconds)}")
            pending[:0] = smaller
            continue
        out.append((text, chunk.start_seconds))
    return out


async def transcribe_tracks(audio: bytes, mime_type: str, tenant_id: str | None) -> TrackTranscript:
    try:
        tele_pcm, cust_pcm, rate = split_stereo(audio)
    except NotStereo:
        logger.warning("Call recording is not stereo; falling back to one labelled transcription pass")
        parts = await _transcribe_pieces(split_audio(audio, mime_type), _MIXED_PROMPT, tenant_id)
        lines: list[Line] = []
        for text, offset in parts:
            lines.extend(replace(l, start=l.start + offset) for l in parse_transcript(text))
        return TrackTranscript(sorted(lines, key=lambda l: l.start), stereo=False)

    tele_segs = speech_segments(tele_pcm, rate)
    cust_segs = speech_segments(cust_pcm, rate)
    if not tele_segs and cust_segs:
        logger.warning("Telecaller track is silent while the customer track has speech: check TELECALLER_CHANNEL")

    lines = []
    for pcm, speaker, segs in ((tele_pcm, "telecaller", tele_segs), (cust_pcm, "customer", cust_segs)):
        for text, offset in await _transcribe_pieces(split_pcm(pcm, rate, 1), _TRACK_PROMPT, tenant_id):
            lines.extend(snap(parse_track_text(text, speaker, offset), segs))
    order = {"telecaller": 0, "customer": 1}
    lines.sort(key=lambda l: (l.start, order[l.speaker]))
    return TrackTranscript(lines, tele_segs, cust_segs, stereo=True)


def _has_clue(text: str, company: str | None) -> bool:
    low = text.lower()
    if company and company.strip() and company.strip().lower() in low:
        return True
    return any(p in low for p in _CLUE_PHRASES)


def tracks_look_swapped(lines: list[Line], company_name: str | None) -> bool:
    """True when "who's calling" clues appear only on the customer's track."""
    cust = any(_has_clue(l.text, company_name) for l in lines if l.speaker == "customer")
    tele = any(_has_clue(l.text, company_name) for l in lines if l.speaker == "telecaller")
    return cust and not tele
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `cd backend && python -m pytest tests/test_call_transcribe.py tests/test_call_tracks.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/call_transcribe.py backend/app/services/gemini_client.py backend/tests/test_call_transcribe.py
git commit -m "feat(calls): transcribe each voice track separately with exact times" -- backend/app/services/call_transcribe.py backend/app/services/gemini_client.py backend/tests/test_call_transcribe.py
```

---

### Task 5: Step 1, sorting (AI step A)

**Files:**
- Create: `backend/app/services/call_sorting.py`
- Test: `backend/tests/test_call_sorting.py`

**Interfaces:**
- Consumes: `call_lines.Line, clock, format_transcript`; `call_quotes.find_quote, clip`; `gemini_client.gemini_analysis_json(system_prompt, user_prompt, tenant_id=..., temperature=0.0, purpose=...)`; `scoring_rules.MIN_SIGNS`
- Produces: `SIGN_SPEAKERS: dict[int, tuple[str, ...]]`; `validate_signs(raw: list, lines) -> list[dict]` (each `{sign, speaker, quote, time}`); `group_for(valid_count: int) -> str`; `SortResult(group: str, signs: list[dict], summary: dict, early_exit_check: dict | None, language_barrier: bool, language_barrier_quote: str | None, rude_quote: str | None)`; `async sort_call(lines, tenant_id) -> SortResult`. `early_exit_check` = `{"polite": bool, "rude_quote": str|None, "enquiry_confirmed_early": bool, "expected_crm": str, "crm_matches": None}`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_call_sorting.py`)

```python
"""Step 1: the system, not the AI, decides the group by counting quote-backed signs."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_sorting as cs
from app.services.call_lines import Line

# The method document's Example 2 (real conversation, ~95 seconds).
REAL = [
    Line(2, "customer", "I need billing software for two shops."),
    Line(8, "telecaller", "Our plan includes GST billing and stock tracking."),
    Line(15, "customer", "How much?"),
    Line(40, "customer", "A bit costly, I'll think."),
    Line(60, "telecaller", "I'll send a demo link and call Friday at 11."),
]
# Example 1 (early exit, ~2 minutes).
EARLY = [
    Line(1, "telecaller", "Calling about your enquiry."),
    Line(4, "customer", "Who is this? Where did you get my number?"),
    Line(9, "customer", "I never enquired, don't call."),
]


def _ai(signs, **extra):
    base = {
        "summary": {"brief": "b", "next_action": "n"},
        "signs": signs,
        "polite": True, "rude_quote": None,
        "enquiry_confirmed_early": True, "expected_crm": "not_enquired",
        "language_barrier": False, "language_barrier_quote": None,
    }
    base.update(extra)
    return base


class ValidateSignsTests(unittest.TestCase):
    def test_all_six_signs_on_document_example(self):
        raw = [
            {"sign": 1, "quote": "I need billing software for two shops"},
            {"sign": 2, "quote": "Our plan includes GST billing"},
            {"sign": 3, "quote": "How much?"},
            {"sign": 4, "quote": "How much?"},
            {"sign": 5, "quote": "A bit costly, I'll think"},
            {"sign": 6, "quote": "I'll send a demo link and call Friday at 11"},
        ]
        valid = cs.validate_signs(raw, REAL)
        self.assertEqual([s["sign"] for s in valid], [1, 2, 3, 4, 5, 6])
        self.assertEqual(valid[0]["time"], "00:02")
        self.assertEqual(valid[1]["speaker"], "telecaller")

    def test_sign_from_wrong_speaker_is_dropped(self):
        # sign 1 (need) must come from the customer
        self.assertEqual(cs.validate_signs([{"sign": 1, "quote": "Our plan includes GST billing"}], REAL), [])

    def test_made_up_quote_is_dropped(self):
        self.assertEqual(cs.validate_signs([{"sign": 3, "quote": "It costs 999 per month"}], REAL), [])

    def test_duplicate_sign_counted_once(self):
        raw = [{"sign": 3, "quote": "How much?"}, {"sign": 3, "quote": "How much?"}]
        self.assertEqual(len(cs.validate_signs(raw, REAL)), 1)

    def test_garbage_entries_ignored(self):
        self.assertEqual(cs.validate_signs([{"sign": 9, "quote": "How much?"}, "x", {"quote": "How much?"}], REAL), [])

    def test_group_threshold(self):
        self.assertEqual(cs.group_for(0), "early_exit")
        self.assertEqual(cs.group_for(1), "early_exit")
        self.assertEqual(cs.group_for(2), "real_conversation")


class SortCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_claiming_signs_without_proof_is_early_exit(self):
        ai = _ai([{"sign": 1, "quote": "I want your product"}, {"sign": 3, "quote": "What's the price"}])
        with patch.object(cs, "gemini_analysis_json", AsyncMock(return_value=ai)):
            result = await cs.sort_call(EARLY, tenant_id="t")
        self.assertEqual(result.group, "early_exit")
        self.assertEqual(result.early_exit_check["expected_crm"], "not_enquired")
        self.assertIsNone(result.early_exit_check["crm_matches"])

    async def test_real_conversation_has_no_early_exit_check(self):
        ai = _ai([{"sign": 3, "quote": "How much?"}, {"sign": 5, "quote": "A bit costly"}])
        with patch.object(cs, "gemini_analysis_json", AsyncMock(return_value=ai)) as gem:
            result = await cs.sort_call(REAL, tenant_id="t")
        self.assertEqual(result.group, "real_conversation")
        self.assertIsNone(result.early_exit_check)
        self.assertEqual(gem.call_args.kwargs["temperature"], 0.0)
        self.assertIn("[00:15] Customer: How much?", gem.call_args.kwargs["user_prompt"])

    async def test_rude_quote_must_be_telecallers(self):
        ai = _ai([], polite=False, rude_quote="Who is this?")  # customer's line, not the telecaller's
        with patch.object(cs, "gemini_analysis_json", AsyncMock(return_value=ai)):
            result = await cs.sort_call(EARLY, tenant_id="t")
        self.assertTrue(result.early_exit_check["polite"])
        self.assertIsNone(result.rude_quote)

    async def test_unknown_expected_crm_becomes_other(self):
        with patch.object(cs, "gemini_analysis_json", AsyncMock(return_value=_ai([], expected_crm="banana"))):
            result = await cs.sort_call(EARLY, tenant_id="t")
        self.assertEqual(result.early_exit_check["expected_crm"], "other")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd backend && python -m pytest tests/test_call_sorting.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `call_sorting.py`**

```python
"""Step 1 — is this a real sales conversation?

The AI only points at lines (the 6 signs). The system checks every quote against the
transcript and the allowed speaker, then counts. The group is never the AI's opinion.
The same request also returns the call summary and the early-exit basic check.
"""
from dataclasses import dataclass

from app.services.call_lines import Line, clock, format_transcript
from app.services.call_quotes import clip, find_quote
from app.services.gemini_client import gemini_analysis_json
from app.services.scoring_rules import MIN_SIGNS

SIGN_SPEAKERS: dict[int, tuple[str, ...]] = {
    1: ("customer",), 2: ("telecaller",), 3: ("telecaller", "customer"),
    4: ("customer",), 5: ("customer",), 6: ("telecaller", "customer"),
}
EXPECTED_CRM = ("wrong_number", "not_enquired", "callback", "language_barrier", "voicemail", "other")
_SUMMARY_KEYS = (
    "course", "product", "budget", "timeline", "next_action", "sentiment", "brief",
    "objections", "commitments", "open_questions",
)

_SYSTEM = (
    "You review telecalling calls. You get a transcript whose every line is labelled with its "
    "time and whether the Telecaller or the Customer said it. The labels are certain; trust them. "
    "The call may be in English, Tamil, Hindi or a mix; write every output value in English, "
    "but copy quotes exactly as they appear in the transcript, in the original script. "
    "Only use what is in the transcript. Never invent a quote."
)

_PROMPT = """Transcript:
{transcript}

Find the signs of a real sales discussion. For each sign you find, copy ONE exact line (or part of a line) that proves it.
1. The customer shared a need or situation (e.g. "I need software for my shop"). Must be the customer.
2. The telecaller explained the product, service or offer: features, benefits or how it works. Just saying the company name or "I'm calling about your enquiry" does NOT count. Must be the telecaller.
3. Price, cost, plan, discount or payment was discussed. Either person.
4. The customer asked a question about the product or service (delivery, features, timing, warranty). "Who is this?" or "where did you get my number?" do NOT count. Must be the customer.
5. The customer raised a concern or objection about the offer ("too costly", "I'll think about it", "already using another one"). "I never enquired", "wrong number" or "I'm busy" do NOT count. Must be the customer.
6. A clear next step: a callback for a specific purpose, a demo, a visit, a meeting, sending a quote or a payment link. A plain "call me later" does NOT count. Either person.
These NEVER count as signs, however long they go on: asking who is calling or where the number came from; wrong number or "I never enquired" with no further sales talk; "call me later", "I'm driving", "I'm busy"; not understanding each other's language; network problems, "hello? hello?", silence; voicemail, IVR or automated messages; casual talk unrelated to the product.

Also answer:
- polite: false only if the telecaller was rude, mocking, dismissive or abusive; then rude_quote = the telecaller's exact line.
- enquiry_confirmed_early: true if within the first 30 seconds the telecaller referred to the customer's enquiry (e.g. "You enquired about our product yesterday, right?").
- expected_crm: what the wrap-up should say if this was not a sales conversation: one of "wrong_number", "not_enquired", "callback", "language_barrier", "voicemail", "other".
- language_barrier: true only if the two people genuinely could not understand each other (mixed Tamil-English is normal); language_barrier_quote = a line showing it.
- summary: course, product, budget, timeline, next_action, sentiment ("positive"|"neutral"|"negative"), brief (2-3 sentences), objections, commitments, open_questions (null when not mentioned).

Return JSON only:
{{"signs": [{{"sign": 1, "quote": "..."}}], "polite": true, "rude_quote": null, "enquiry_confirmed_early": false, "expected_crm": "other", "language_barrier": false, "language_barrier_quote": null, "summary": {{...}}}}"""


@dataclass
class SortResult:
    group: str
    signs: list[dict]
    summary: dict
    early_exit_check: dict | None
    language_barrier: bool
    language_barrier_quote: str | None
    rude_quote: str | None


def validate_signs(raw, lines: list[Line]) -> list[dict]:
    seen: set[int] = set()
    valid = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        sign = item.get("sign")
        if sign not in SIGN_SPEAKERS or sign in seen:
            continue
        line = find_quote(item.get("quote"), lines, SIGN_SPEAKERS[sign])
        if not line:
            continue
        seen.add(sign)
        valid.append({"sign": sign, "speaker": line.speaker, "quote": clip(item["quote"]), "time": clock(line.start)})
    return sorted(valid, key=lambda s: s["sign"])


def group_for(valid_count: int) -> str:
    return "real_conversation" if valid_count >= MIN_SIGNS else "early_exit"


def _telecaller_quote(quote, lines: list[Line]) -> str | None:
    line = find_quote(quote, lines, ("telecaller",))
    return f"[{clock(line.start)}] {clip(quote)}" if line else None


async def sort_call(lines: list[Line], tenant_id: str | None) -> SortResult:
    data = await gemini_analysis_json(
        system_prompt=_SYSTEM,
        user_prompt=_PROMPT.format(transcript=format_transcript(lines)),
        tenant_id=tenant_id,
        temperature=0.0,
        purpose="call_sorting",
    )
    signs = validate_signs(data.get("signs"), lines)
    group = group_for(len(signs))
    summary = {k: v for k, v in (data.get("summary") or {}).items() if k in _SUMMARY_KEYS}
    rude_quote = None if data.get("polite") is not False else _telecaller_quote(data.get("rude_quote"), lines)
    barrier_line = find_quote(data.get("language_barrier_quote"), lines) if data.get("language_barrier") is True else None

    early = None
    if group == "early_exit":
        expected = data.get("expected_crm")
        early = {
            "polite": rude_quote is None,
            "rude_quote": rude_quote,
            "enquiry_confirmed_early": data.get("enquiry_confirmed_early") is True,
            "expected_crm": expected if expected in EXPECTED_CRM else "other",
            "crm_matches": None,
        }
    return SortResult(
        group=group,
        signs=signs,
        summary=summary,
        early_exit_check=early,
        language_barrier=barrier_line is not None,
        language_barrier_quote=f"[{clock(barrier_line.start)}] {clip(data.get('language_barrier_quote'))}" if barrier_line else None,
        rude_quote=rude_quote,
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && python -m pytest tests/test_call_sorting.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/call_sorting.py backend/tests/test_call_sorting.py
git commit -m "feat(calls): step 1 sorting by quote-validated sales signs" -- backend/app/services/call_sorting.py backend/tests/test_call_sorting.py
```

---

### Task 6: Step 2, marking checks 1–9 (AI step B) + marks maths

**Files:**
- Create: `backend/app/services/call_marking.py`
- Test: `backend/tests/test_call_marking.py`

**Interfaces:**
- Consumes: `Line, clock, format_transcript`; `find_quote, clip`; `call_metrics.listening_cap, courtesy_cap, lower_level, tips`; `scoring_rules.CHECK_MARKS, LEVEL_SHARE, LEVEL_ORDER`; `gemini_analysis_json`
- Produces: `CHECKS: list[dict]` (`{"key","label","stage","full"}` in display order); `check_marks(key, level) -> float`; `total_score(checks: list[dict]) -> float` (rounded 1dp; `level None` counts 0); `top_improve(checks) -> list[str]` (2 keys, ignoring `level None`); `apply_level(check: dict, ai_level: str, cap: str, cap_name: str | None) -> dict`; `MarkResult(checks: list[dict], rude_quote: str|None, wrong_info: list[dict], unverified_claims: list[str], proof_missing: list[str], tips: list[str])`; `async mark_call(lines, *, kb_context, previous_notes, talk_share, interruptions_per_5min, interruption_count, duration_seconds, tenant_id) -> MarkResult`. `checks` has all 10 keys; `crm_update` has `level None` (filled by Task 7). Each check dict: `{"key","full","level","ai_level","capped_by","marks","reason","quote","time","proof_missing"}`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_call_marking.py`)

```python
"""Step 2: the AI picks levels, the system does every mark, cap and total."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_marking as cm
from app.services.call_lines import Line

LINES = [
    Line(0, "telecaller", "Good morning sir, this is Priya from Aira Softwares, you enquired about billing software, is this a good time?"),
    Line(9, "customer", "Yes. We have two branches actually."),
    Line(15, "telecaller", "Our plan includes GST billing and stock tracking. It is 12000 per year."),
    Line(30, "customer", "A bit costly, I'll think."),
    Line(40, "telecaller", "Shall I book a demo for Friday at 11 AM?"),
    Line(45, "customer", "Okay, Friday 11 is fine."),
]


def _level_map(levels: dict) -> list[dict]:
    return [{"key": c["key"], "full": c["full"], "level": levels.get(c["key"])} for c in cm.CHECKS]


class MarksMathsTests(unittest.TestCase):
    def test_document_full_example_is_78_5(self):
        levels = {
            "opening": "excellent", "courtesy": "good", "questions": "good", "listening": "partial",
            "product_info": "good", "doubts": "excellent", "clarity": "good", "next_step": "excellent",
            "decision": "partial", "crm_update": "excellent",
        }
        checks = [dict(c, marks=cm.check_marks(c["key"], c["level"])) for c in _level_map(levels)]
        self.assertEqual(cm.total_score(checks), 78.5)
        self.assertEqual(cm.top_improve(checks), ["listening", "decision"])

    def test_marks_per_level(self):
        self.assertEqual(cm.check_marks("questions", "good"), 11.25)
        self.assertEqual(cm.check_marks("decision", "partial"), 4.0)
        self.assertEqual(cm.check_marks("crm_update", None), 0.0)

    def test_top_improve_tie_prefers_bigger_check(self):
        levels = {c["key"]: "excellent" for c in cm.CHECKS}
        levels.update({"opening": "partial", "questions": "partial", "clarity": "partial"})
        checks = [dict(c, marks=cm.check_marks(c["key"], c["level"])) for c in _level_map(levels)]
        self.assertEqual(cm.top_improve(checks), ["questions", "clarity"])

    def test_pending_crm_excluded_from_top_improve(self):
        levels = {c["key"]: "excellent" for c in cm.CHECKS}
        levels["crm_update"] = None
        levels["clarity"] = "good"
        checks = [dict(c, marks=cm.check_marks(c["key"], c["level"])) for c in _level_map(levels)]
        self.assertNotIn("crm_update", cm.top_improve(checks))

    def test_apply_level_caps_and_records_it(self):
        check = {"key": "listening", "full": 10}
        out = cm.apply_level(check, "excellent", "good", "interruptions")
        self.assertEqual((out["level"], out["ai_level"], out["capped_by"], out["marks"]), ("good", "excellent", "interruptions", 7.5))
        out = cm.apply_level(check, "partial", "good", "interruptions")
        self.assertIsNone(out["capped_by"])


def _ai(**overrides):
    checks = {
        "opening": {"level": "excellent", "reason": "all elements", "quote": "this is Priya from Aira Softwares"},
        "courtesy": {"level": "good", "reason": "polite", "quote": "Good morning sir"},
        "questions": {"level": "good", "reason": "asked need", "quote": "is this a good time"},
        "listening": {"level": "excellent", "reason": "confirmed", "quote": "We have two branches actually"},
        "product_info": {"level": "good", "reason": "correct", "quote": "GST billing and stock tracking"},
        "doubts": {"level": "excellent", "reason": "handled", "quote": "A bit costly"},
        "clarity": {"level": "good", "reason": "clear", "quote": "Our plan includes GST billing"},
        "next_step": {"level": "excellent", "reason": "demo fixed", "quote": "Friday 11 is fine"},
        "decision": {"level": "partial", "reason": "hinted", "quote": "Shall I book a demo"},
    }
    data = {"checks": checks, "rude": False, "rude_quote": None, "excused_interruptions": 0,
            "wrong_info": [], "unverified_claims": []}
    data.update(overrides)
    return data


class MarkCallTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, ai, talk_share=50.0, ipm=0.5, count=0):
        with patch.object(cm, "gemini_analysis_json", AsyncMock(return_value=ai)) as gem:
            result = await cm.mark_call(
                LINES, kb_context="Plan: 12000 per year", previous_notes="", talk_share=talk_share,
                interruptions_per_5min=ipm, interruption_count=count, duration_seconds=60, tenant_id="t",
            )
        return result, gem

    async def test_all_ten_checks_present_crm_pending(self):
        result, gem = await self._run(_ai())
        self.assertEqual([c["key"] for c in result.checks], [c["key"] for c in cm.CHECKS])
        crm = result.checks[-1]
        self.assertEqual((crm["key"], crm["level"], crm["marks"]), ("crm_update", None, None))
        self.assertEqual(gem.call_args.kwargs["temperature"], 0.0)

    async def test_quote_time_comes_from_transcript(self):
        result, _ = await self._run(_ai())
        listening = next(c for c in result.checks if c["key"] == "listening")
        self.assertEqual(listening["time"], "00:09")

    async def test_listening_capped_by_talk_share(self):
        result, _ = await self._run(_ai(), talk_share=80.0, ipm=0.5)
        listening = next(c for c in result.checks if c["key"] == "listening")
        self.assertEqual((listening["level"], listening["capped_by"]), ("partial", "talk_share"))
        self.assertTrue(result.tips)

    async def test_excused_interruption_lifts_courtesy_cap(self):
        ai = _ai(excused_interruptions=1)
        # 4 interruptions in 1 minute = 20/5min; excusing 1 still leaves 15 → cap stays
        result, _ = await self._run(ai, ipm=20.0, count=4)
        courtesy = next(c for c in result.checks if c["key"] == "courtesy")
        self.assertEqual(courtesy["level"], "good")

    async def test_made_up_quote_flags_proof_missing(self):
        ai = _ai()
        ai["checks"]["clarity"]["quote"] = "Let me explain our cloud features"
        result, _ = await self._run(ai)
        clarity = next(c for c in result.checks if c["key"] == "clarity")
        self.assertTrue(clarity["proof_missing"])
        self.assertEqual(clarity["level"], "good")  # the mark still counts
        self.assertIn("clarity", result.proof_missing)

    async def test_missing_level_needs_no_quote(self):
        ai = _ai()
        ai["checks"]["decision"] = {"level": "missing", "reason": "never asked", "quote": None}
        result, _ = await self._run(ai)
        decision = next(c for c in result.checks if c["key"] == "decision")
        self.assertFalse(decision["proof_missing"])

    async def test_wrong_info_forces_product_info_missing(self):
        ai = _ai(wrong_info=[{"quote": "It is 12000 per year", "kb_fact": "Plan is 15000 per year"}])
        result, _ = await self._run(ai)
        product = next(c for c in result.checks if c["key"] == "product_info")
        self.assertEqual((product["level"], product["capped_by"], product["marks"]), ("missing", "wrong_info", 0.0))
        self.assertEqual(result.wrong_info[0]["time"], "00:15")

    async def test_wrong_info_needs_a_real_telecaller_quote(self):
        ai = _ai(wrong_info=[{"quote": "Free for life", "kb_fact": "No free plan"}])
        result, _ = await self._run(ai)
        self.assertEqual(result.wrong_info, [])

    async def test_rude_from_ai_creates_rude_quote(self):
        ai = _ai(rude=True, rude_quote="Our plan includes GST billing")
        result, _ = await self._run(ai)
        self.assertTrue(result.rude_quote.startswith("[00:15]"))
        courtesy = next(c for c in result.checks if c["key"] == "courtesy")
        self.assertEqual(courtesy["level"], "missing")

    async def test_missing_check_in_ai_reply_raises(self):
        ai = _ai()
        del ai["checks"]["clarity"]
        with self.assertRaises(cm.CallMarkingError):
            await self._run(ai)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd backend && python -m pytest tests/test_call_marking.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `call_marking.py`**

```python
"""Step 2 — mark a real conversation out of 100 on 10 fixed checks.

The AI chooses only a level (+ reason + quote) per check. The system validates
every quote, applies the talk-share/interruption caps, forces product info to
Missing on a proven wrong statement, and computes every mark and the total.
Check 10 (CRM update) is left pending here and marked from the wrap-up.
"""
from dataclasses import dataclass, field

from app.services.call_lines import Line, clock, format_transcript
from app.services.call_metrics import courtesy_cap, listening_cap, lower_level, tips
from app.services.call_quotes import clip, find_quote
from app.services.gemini_client import gemini_analysis_json
from app.services.scoring_rules import CHECK_MARKS, LEVEL_ORDER, LEVEL_SHARE

CHECKS: list[dict] = [
    {"key": "opening", "label": "Opening", "stage": "connect"},
    {"key": "courtesy", "label": "Courtesy & empathy", "stage": "connect"},
    {"key": "questions", "label": "Asking questions", "stage": "understand"},
    {"key": "listening", "label": "Listening", "stage": "understand"},
    {"key": "product_info", "label": "Correct product information", "stage": "explain"},
    {"key": "doubts", "label": "Clearing doubts", "stage": "explain"},
    {"key": "clarity", "label": "Clarity", "stage": "explain"},
    {"key": "next_step", "label": "Next step", "stage": "close"},
    {"key": "decision", "label": "Asking for the decision", "stage": "close"},
    {"key": "crm_update", "label": "CRM update", "stage": "close"},
]
for _c in CHECKS:
    _c["full"] = CHECK_MARKS[_c["key"]]
AI_CHECKS = [c["key"] for c in CHECKS if c["key"] != "crm_update"]


class CallMarkingError(Exception):
    """The AI reply didn't give a valid level for every check."""


@dataclass
class MarkResult:
    checks: list[dict]
    rude_quote: str | None = None
    wrong_info: list[dict] = field(default_factory=list)
    unverified_claims: list[str] = field(default_factory=list)
    proof_missing: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)


def check_marks(key: str, level: str | None) -> float:
    return CHECK_MARKS[key] * LEVEL_SHARE[level] if level else 0.0


def total_score(checks: list[dict]) -> float:
    return round(sum(check_marks(c["key"], c.get("level")) for c in checks), 1)


def top_improve(checks: list[dict]) -> list[str]:
    marked = [c for c in checks if c.get("level")]
    marked.sort(key=lambda c: (check_marks(c["key"], c["level"]) / CHECK_MARKS[c["key"]], -CHECK_MARKS[c["key"]]))
    return [c["key"] for c in marked[:2]]


def apply_level(check: dict, ai_level: str, cap: str, cap_name: str | None) -> dict:
    level = lower_level(ai_level, cap)
    out = dict(check)
    out.update({
        "ai_level": ai_level,
        "level": level,
        "capped_by": cap_name if level != ai_level else None,
        "marks": round(check_marks(check["key"], level), 2),
    })
    return out


_SYSTEM = (
    "You are a strict, consistent quality reviewer for a telecalling team. You mark ONE real sales "
    "conversation using a fixed rubric. The transcript lines carry exact times and certain speaker "
    "labels. Judge only what the telecaller did, never whether the customer bought. Use only the "
    "transcript, the knowledge base, the previous notes and the two numbers given. No guessing. "
    "Write reasons in English; copy quotes exactly as they appear in the transcript."
)

_RUBRIC = """Mark checks 1-9. For each give level ("excellent"|"good"|"partial"|"poor"|"missing"), a one-line reason, and a short exact quote from the transcript that supports it (for "missing", quote the line showing the gap, or null and say in the reason what was not said).
1 opening: greeting, telecaller's name, company name, reminder of the enquiry/reason for the call, asking if it's a good time. excellent = all within ~30s; good = one missing; partial = two+ missing or rushed/unclear reason; poor = straight into selling without introducing; missing = no introduction or rude start.
2 courtesy: polite words, acknowledging feelings, patience, no pressure (no "decide now", no false urgency, no pushing after a no), respectful ending. excellent = all; good = misses one; partial = dry/scripted or slightly pushy once; poor = impatient or pushy several times (also: still pushing after the customer's 2nd "not interested" is poor at most); missing = rude, sarcastic, dismissive or abusive.
3 questions: open questions on need, budget, timing, decision-maker. excellent = need + at least 2 of the others; good = need + 1; partial = only 1-2 basic or yes/no questions; poor = assumed the need; missing = none. On a follow-up call where the need is already known (see previous notes), confirming the need counts as asking.
4 listening: repeating back/summarising, using the customer's answers, balanced talk. excellent = summarised/confirmed, built on answers; good = one missed chance to confirm; partial = some points ignored or talked too much; poor = mostly ignored answers or interrupted often; missing = talked over the customer or ignored everything.
5 product_info: compare with the knowledge base. excellent = all correct and linked to the customer's need; good = correct but general; partial = mostly correct but vague/missing details; poor = several gaps or couldn't answer basics; missing = gave wrong information. Something the knowledge base doesn't cover is NOT wrong: list it under unverified_claims. Only statements that clearly contradict the knowledge base are wrong: list each under wrong_info with the telecaller's exact quote and the knowledge-base fact.
6 doubts: excellent = answered every question/concern clearly and checked the customer was satisfied, or (if none were raised) explained common doubts upfront; good = answered but didn't check; partial = vague answers; poor = avoided or brushed off, or confusing; missing = ignored or argued.
7 clarity: excellent = simple, organised, customer never asked "what?"; good = a little repetition; partial = some confusing parts or overly long; poor = frequently confusing; missing = customer clearly couldn't follow.
8 next_step: excellent = specific next step agreed by the customer with date and time; good = agreed, no exact time; partial = vague ("I'll call you sometime"); poor = mentioned but not agreed; missing = none. A correctly disqualified customer ended politely counts as excellent.
9 decision: excellent = asked clearly at a suitable moment without pressure; good = asked weakly/indirectly; partial = only hinted; poor = asked too early or pushed; missing = never asked. For a correctly disqualified customer, politely keeping the door open counts as excellent.
Also: rude (true only if the telecaller was rude/abusive; rude_quote = their exact line); excused_interruptions = how many of the interruptions were the telecaller politely bringing a long off-topic customer back ("Sorry to cut in, sir…"), with the reason in the courtesy reason.

Return JSON only:
{"checks": {"opening": {"level": "...", "reason": "...", "quote": "..."}, ... all 9 keys ...}, "rude": false, "rude_quote": null, "excused_interruptions": 0, "wrong_info": [{"quote": "...", "kb_fact": "..."}], "unverified_claims": ["..."]}"""


def _numbers_block(share, ipm, count) -> str:
    share_txt = f"{share:.0f}% of the words were the telecaller's" if share is not None else "not measured (too few words)"
    int_txt = f"{count} times ({ipm:.2f} per 5 minutes)" if ipm is not None else "not measured"
    return (
        f"Talk share: {share_txt}. Interruptions (telecaller cut in while the customer was speaking): {int_txt}.\n"
        "These numbers guide listening and courtesy, but you must still read what was said.\n"
    )


def _quote_ok(level: str, quote, lines: list[Line]) -> tuple[bool, Line | None]:
    line = find_quote(quote, lines)
    if line:
        return True, line
    return level == "missing" and not quote, None


async def mark_call(
    lines: list[Line], *, kb_context: str | None, previous_notes: str | None, talk_share: float | None,
    interruptions_per_5min: float | None, interruption_count: int | None, duration_seconds: int | None,
    tenant_id: str | None,
) -> MarkResult:
    kb = kb_context or "none available (treat product claims you can't check as unverified, not wrong)"
    prompt = (
        f"Transcript:\n{format_transcript(lines)}\n\n"
        f"Knowledge base:\n{kb}\n\n"
        f"Previous notes on this lead:\n{previous_notes or 'none'}\n\n"
        f"{_numbers_block(talk_share, interruptions_per_5min, interruption_count)}\n{_RUBRIC}"
    )
    data = await gemini_analysis_json(
        system_prompt=_SYSTEM, user_prompt=prompt, tenant_id=tenant_id, temperature=0.0, purpose="call_marking",
    )
    raw = data.get("checks") if isinstance(data.get("checks"), dict) else {}

    excused = data.get("excused_interruptions")
    excused = excused if isinstance(excused, int) and not isinstance(excused, bool) and excused > 0 else 0
    ipm_for_caps = interruptions_per_5min
    if ipm_for_caps is not None and interruption_count and excused:
        remaining = max(0, interruption_count - excused)
        ipm_for_caps = round(ipm_for_caps * remaining / interruption_count, 2)

    rude_line = find_quote(data.get("rude_quote"), lines, ("telecaller",)) if data.get("rude") is True else None
    wrong = []
    for item in data.get("wrong_info") or []:
        if isinstance(item, dict):
            line = find_quote(item.get("quote"), lines, ("telecaller",))
            if line:
                wrong.append({"quote": clip(item["quote"]), "time": clock(line.start), "kb_fact": clip(item.get("kb_fact"))})

    lcap = listening_cap(talk_share, ipm_for_caps)
    lcap_name = None
    if lcap != "excellent":
        hi_share = talk_share is not None and talk_share > 65
        hi_int = ipm_for_caps is not None and ipm_for_caps > 1
        lcap_name = "talk_share_and_interruptions" if hi_share and hi_int else ("talk_share" if hi_share else "interruptions")

    checks, proof_missing = [], []
    for base in CHECKS:
        key = base["key"]
        slim = {"key": key, "full": base["full"]}
        if key == "crm_update":
            checks.append({**slim, "level": None, "ai_level": None, "capped_by": None, "marks": None,
                           "reason": None, "quote": None, "time": None, "proof_missing": False})
            continue
        item = raw.get(key)
        level = item.get("level") if isinstance(item, dict) else None
        if level not in LEVEL_ORDER:
            raise CallMarkingError(f"no valid level for check {key}")
        cap, cap_name = "excellent", None
        if key == "listening":
            cap, cap_name = lcap, lcap_name
        elif key == "courtesy":
            if rude_line:
                cap, cap_name = "missing", "rude"
            else:
                cap = courtesy_cap(ipm_for_caps)
                cap_name = "interruptions" if cap != "excellent" else None
        elif key == "product_info" and wrong:
            cap, cap_name = "missing", "wrong_info"
        check = apply_level(slim, level, cap, cap_name)
        ok, line = _quote_ok(level, item.get("quote"), lines)
        check.update({
            "reason": clip(item.get("reason")),
            "quote": clip(item.get("quote")) if line else None,
            "time": clock(line.start) if line else None,
            "proof_missing": not ok,
        })
        if not ok:
            proof_missing.append(key)
        checks.append(check)

    return MarkResult(
        checks=checks,
        rude_quote=f"[{clock(rude_line.start)}] {clip(data.get('rude_quote'))}" if rude_line else None,
        wrong_info=wrong,
        unverified_claims=[clip(c) for c in data.get("unverified_claims") or [] if isinstance(c, str)][:10],
        proof_missing=proof_missing,
        tips=tips(talk_share, interruptions_per_5min),
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && python -m pytest tests/test_call_marking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/call_marking.py backend/tests/test_call_marking.py
git commit -m "feat(calls): step 2 marking — 10 checks, caps and system-computed marks" -- backend/app/services/call_marking.py backend/tests/test_call_marking.py
```

---

### Task 7: Migration 205 + alerts service + check 10 (wrap-up)

**Files:**
- Create: `backend/supabase/migrations/205_call_scoring_v4.sql`
- Create: `backend/app/services/call_alerts.py`
- Modify: `backend/app/services/call_marking.py` (add check 10)
- Test: `backend/tests/test_call_alerts.py`, `backend/tests/test_call_crm_check.py`

**Interfaces:**
- Produces (alerts): `ALERT_TYPES`, `INSTANT_TYPES = ("rude", "wrong_info")`; `raise_alert(db, *, tenant_id, type, call_log_id=None, caller_id=None, quote=None, detail=None, now=None) -> bool` (False when deduped); `admin_user_ids(db, tenant_id) -> list[str]`; `run_lead_source_check(db, tenant_id, day_start_iso, day_end_iso) -> int`; `send_morning_summaries(db, now=None) -> int`.
- Produces (check 10): `crm_matches_expected(expected: str, wrapup: dict) -> bool | None`; `async mark_crm_update(db, call_log_id: str, *, now=None) -> bool` (True when it changed something). `wrapup_snapshot(db, row) -> dict | None`.

- [ ] **Step 1: Write the migration** (`backend/supabase/migrations/205_call_scoring_v4.sql`)

```sql
-- TeleCMI call scoring v4 (CallIQ Steps 1-2). Additive only; drops live in 207.
ALTER TABLE call_logs
  ADD COLUMN IF NOT EXISTS call_group text
    CHECK (call_group IN ('not_connected','very_short','early_exit','real_conversation')),
  ADD COLUMN IF NOT EXISTS talk_share numeric(5,2),
  ADD COLUMN IF NOT EXISTS interruption_count integer,
  ADD COLUMN IF NOT EXISTS interruptions_per_5min numeric(6,2),
  ADD COLUMN IF NOT EXISTS score_final boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS rules_version text,
  ADD COLUMN IF NOT EXISTS wrapup_callback_at timestamptz;

CREATE TABLE IF NOT EXISTS call_alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  call_log_id uuid REFERENCES call_logs(id) ON DELETE CASCADE,
  caller_id uuid REFERENCES callers(id) ON DELETE SET NULL,
  type text NOT NULL CHECK (type IN (
    'rude','wrong_info','crm_mismatch','no_proof','transcript_failed',
    'language_barrier','lead_source_quality','tracks_swapped'
  )),
  quote text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  notified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  seen_at timestamptz,
  seen_by uuid
);

CREATE UNIQUE INDEX IF NOT EXISTS call_alerts_call_type_uniq
  ON call_alerts (call_log_id, type) WHERE call_log_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS call_alerts_tenant_unseen_idx
  ON call_alerts (tenant_id, seen_at, created_at DESC);
CREATE INDEX IF NOT EXISTS call_alerts_caller_notified_idx
  ON call_alerts (caller_id, notified_at);

ALTER TABLE call_alerts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS call_alerts_tenant_member_select ON call_alerts;
CREATE POLICY call_alerts_tenant_member_select ON call_alerts
  FOR SELECT TO authenticated USING (is_tenant_member(tenant_id));
```

- [ ] **Step 2: Apply migration 205 live** (additive, safe before deploy)

Use Supabase MCP `apply_migration` on project `ayftynkgmfkaqmmnlmoc`, name `205_call_scoring_v4`, with the SQL above. Then verify:

```sql
select column_name from information_schema.columns where table_name='call_logs' and column_name in ('call_group','talk_share','score_final','wrapup_callback_at');
select relrowsecurity from pg_class where relname='call_alerts';
```
Expected: 4 rows; `true`.

- [ ] **Step 3: Write the failing alert tests** (`backend/tests/test_call_alerts.py`)

```python
"""Warnings: one row per call+type, instant pushes only for serious types, capped per hour."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_alerts as ca

NOW = datetime(2026, 9, 26, 5, 0, tzinfo=timezone.utc)


class _FakeDb:
    """Tiny in-memory stand-in for the three tables call_alerts touches."""

    def __init__(self, alerts=None, users=None, callers=None):
        self.rows = {"call_alerts": list(alerts or []), "tenant_users": list(users or []), "callers": list(callers or [])}

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, db, name):
        self.db, self.name, self.filters, self.payload, self.op = db, name, [], None, "select"

    def select(self, *a, **k): return self
    def insert(self, payload): self.op, self.payload = "insert", payload; return self
    def update(self, payload): self.op, self.payload = "update", payload; return self
    def eq(self, c, v): self.filters.append(lambda r: r.get(c) == v); return self
    def in_(self, c, vs): self.filters.append(lambda r: r.get(c) in vs); return self
    def gte(self, c, v): self.filters.append(lambda r: r.get(c) is not None and r.get(c) >= v); return self
    def lt(self, c, v): self.filters.append(lambda r: r.get(c) is not None and r.get(c) < v); return self
    def is_(self, c, v): self.filters.append(lambda r: r.get(c) is None); return self
    def not_(self): return self
    def limit(self, n): return self
    def order(self, *a, **k): return self

    def execute(self):
        rows = self.db.rows[self.name]
        if self.op == "insert":
            p = self.payload
            if p.get("call_log_id") and any(r.get("call_log_id") == p["call_log_id"] and r["type"] == p["type"] for r in rows):
                raise Exception("duplicate key value violates unique constraint")
            rows.append(dict(p))
            return MagicMock(data=[p])
        hit = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
        return MagicMock(data=hit, count=len(hit))


class RaiseAlertTests(unittest.TestCase):
    def _db(self, alerts=None):
        return _FakeDb(alerts, users=[{"tenant_id": "t", "user_id": "admin-1", "role": "owner"}],
                       callers=[{"id": "c1", "name": "Priya", "user_id": "u-priya"}])

    def test_duplicate_call_type_is_ignored(self):
        db = self._db()
        with patch.object(ca, "notify_user") as notify:
            self.assertTrue(ca.raise_alert(db, tenant_id="t", type="crm_mismatch", call_log_id="call-1", caller_id="c1", now=NOW))
            self.assertFalse(ca.raise_alert(db, tenant_id="t", type="crm_mismatch", call_log_id="call-1", caller_id="c1", now=NOW))
        self.assertEqual(len(db.rows["call_alerts"]), 1)
        notify.assert_not_called()  # not an instant type

    def test_instant_type_notifies_admin_once_per_hour_per_telecaller(self):
        db = self._db()
        with patch.object(ca, "notify_user") as notify:
            ca.raise_alert(db, tenant_id="t", type="rude", call_log_id="call-1", caller_id="c1", quote="q", now=NOW)
            ca.raise_alert(db, tenant_id="t", type="wrong_info", call_log_id="call-2", caller_id="c1", quote="q", now=NOW + timedelta(minutes=10))
            ca.raise_alert(db, tenant_id="t", type="rude", call_log_id="call-3", caller_id="c1", quote="q", now=NOW + timedelta(minutes=61))
        self.assertEqual(notify.call_count, 2)
        self.assertEqual(notify.call_args.args[1], "admin-1")
        self.assertEqual(len(db.rows["call_alerts"]), 3)

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError):
            ca.raise_alert(self._db(), tenant_id="t", type="banana", now=NOW)


class LeadSourceTests(unittest.TestCase):
    def test_threshold(self):
        self.assertTrue(ca.lead_source_is_bad(total=10, bad=3))
        self.assertFalse(ca.lead_source_is_bad(total=10, bad=2))
        self.assertFalse(ca.lead_source_is_bad(total=9, bad=9))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Write `call_alerts.py`**

```python
"""The admin's "Needs attention" list for call scoring.

Every warning is one row (deduped per call+type). Only `rude` and `wrong_info`
push a notification straight away, at most one per telecaller per hour; the rest
wait in the list and in the 09:00 IST morning summary, so admins aren't flooded.
"""
import logging
from datetime import datetime, timedelta, timezone

from app.services.notify import notify_user
from app.services.scoring_rules import (
    ALERT_RATE_LIMIT_PER_HOUR, LEAD_SOURCE_BAD_RATE, LEAD_SOURCE_MIN_CALLS,
)

logger = logging.getLogger(__name__)

ALERT_TYPES = (
    "rude", "wrong_info", "crm_mismatch", "no_proof", "transcript_failed",
    "language_barrier", "lead_source_quality", "tracks_swapped",
)
INSTANT_TYPES = ("rude", "wrong_info")
ALERT_LABELS = {
    "rude": "Rude or dismissive on a call",
    "wrong_info": "Wrong product information",
    "crm_mismatch": "Wrap-up doesn't match the call",
    "no_proof": "Mark without proof",
    "transcript_failed": "Call couldn't be transcribed",
    "language_barrier": "Language barrier",
    "lead_source_quality": "Lead source giving bad numbers",
    "tracks_swapped": "Voice tracks may be swapped",
}


def admin_user_ids(db, tenant_id: str) -> list[str]:
    rows = db.table("tenant_users").select("user_id,role").eq("tenant_id", tenant_id).in_("role", ["owner", "admin"]).execute()
    return [r["user_id"] for r in (rows.data or []) if r.get("user_id")]


def _caller_name(db, caller_id: str | None) -> str:
    if not caller_id:
        return "A telecaller"
    res = db.table("callers").select("name").eq("id", caller_id).limit(1).execute()
    return ((res.data or [{}])[0]).get("name") or "A telecaller"


def raise_alert(
    db, *, tenant_id: str, type: str, call_log_id: str | None = None, caller_id: str | None = None,
    quote: str | None = None, detail: dict | None = None, now: datetime | None = None,
) -> bool:
    if type not in ALERT_TYPES:
        raise ValueError(f"unknown alert type {type}")
    now = now or datetime.now(timezone.utc)
    row = {
        "tenant_id": tenant_id, "call_log_id": call_log_id, "caller_id": caller_id, "type": type,
        "quote": quote, "detail": detail or {}, "created_at": now.isoformat(),
    }
    try:
        db.table("call_alerts").insert(row).execute()
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            return False
        raise

    if type in INSTANT_TYPES and caller_id:
        since = (now - timedelta(hours=1)).isoformat()
        recent = (
            db.table("call_alerts").select("id").eq("caller_id", caller_id)
            .in_("type", list(INSTANT_TYPES)).gte("notified_at", since).execute()
        ).data or []
        if len(recent) < ALERT_RATE_LIMIT_PER_HOUR:
            name = _caller_name(db, caller_id)
            for user_id in admin_user_ids(db, tenant_id):
                notify_user(tenant_id, user_id, f"call_alert_{type}", ALERT_LABELS[type],
                            f"{name}: {quote or ALERT_LABELS[type]}", db=db,
                            push_url="/dashboard/telecalling#needs-attention")
            q = db.table("call_alerts").update({"notified_at": now.isoformat()}).eq("type", type)
            q = q.eq("call_log_id", call_log_id) if call_log_id else q.eq("created_at", row["created_at"])
            q.execute()
    return True


def lead_source_is_bad(total: int, bad: int) -> bool:
    return total >= LEAD_SOURCE_MIN_CALLS and bad / total >= LEAD_SOURCE_BAD_RATE


def run_lead_source_check(db, tenant_id: str, day_start_iso: str, day_end_iso: str) -> int:
    """Raise one lead_source_quality alert per source that gave 30%+ wrong/never-enquired numbers."""
    rows = (
        db.table("call_logs").select("call_group,evaluation,leads(source)")
        .eq("tenant_id", tenant_id).eq("provider", "telecmi")
        .in_("call_group", ["early_exit", "real_conversation"])
        .gte("created_at", day_start_iso).lt("created_at", day_end_iso).execute()
    ).data or []
    by_source: dict[str, list[int]] = {}
    for r in rows:
        source = ((r.get("leads") or {}).get("source")) or "unknown"
        early = (r.get("evaluation") or {}).get("early_exit_check") or {}
        bad = r.get("call_group") == "early_exit" and early.get("expected_crm") in ("wrong_number", "not_enquired")
        tally = by_source.setdefault(source, [0, 0])
        tally[0] += 1
        tally[1] += int(bad)
    raised = 0
    for source, (total, bad) in by_source.items():
        if lead_source_is_bad(total, bad):
            raise_alert(db, tenant_id=tenant_id, type="lead_source_quality",
                        quote=f"{source}: {bad} of {total} answered calls were wrong numbers or never enquired",
                        detail={"source": source, "total": total, "bad": bad, "day": day_start_iso[:10]})
            raised += 1
    return raised


def send_morning_summaries(db, now: datetime | None = None) -> int:
    """One notification per tenant admin with yesterday's (IST) alert counts. Skips empty days."""
    from app.services.telecaller_performance import ist_day_bounds

    now = now or datetime.now(timezone.utc)
    start, end = ist_day_bounds(now - timedelta(days=1))
    tenants = {r["tenant_id"] for r in (db.table("call_logs").select("tenant_id").eq("provider", "telecmi").gte("created_at", start).lt("created_at", end).execute()).data or []}
    sent = 0
    for tenant_id in tenants:
        run_lead_source_check(db, tenant_id, start, end)
        alerts = (db.table("call_alerts").select("type").eq("tenant_id", tenant_id).gte("created_at", start).lt("created_at", end).execute()).data or []
        if not alerts:
            continue
        counts: dict[str, int] = {}
        for a in alerts:
            counts[a["type"]] = counts.get(a["type"], 0) + 1
        text = ", ".join(f"{n} {ALERT_LABELS[t].lower()}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1]))
        for user_id in admin_user_ids(db, tenant_id):
            notify_user(tenant_id, user_id, "call_alerts_summary", "Yesterday's calls need attention",
                        f"{text}.", db=db, push_url="/dashboard/telecalling#needs-attention")
            sent += 1
    return sent
```

- [ ] **Step 5: Run the alert tests to confirm they pass**

Run: `cd backend && python -m pytest tests/test_call_alerts.py -v`
Expected: PASS (`ist_day_bounds(now)` at `telecaller_performance.py:21` accepts the shifted datetime).

- [ ] **Step 6: Write the failing check-10 tests** (`backend/tests/test_call_crm_check.py`)

```python
"""Check 10: marked from the wrap-up, Missing after 2 hours, re-marked when the wrap-up changes."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import call_marking as cm

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def _checks(crm_level=None):
    out = []
    for c in cm.CHECKS:
        level = "good" if c["key"] != "crm_update" else crm_level
        out.append({"key": c["key"], "full": c["full"], "level": level, "marks": cm.check_marks(c["key"], level)})
    return out


def _row(**kw):
    row = {
        "id": "call-1", "tenant_id": "t", "caller_id": "c1", "lead_id": "lead-1", "provider": "telecmi",
        "call_group": "real_conversation", "ai_status": "done",
        "created_at": (NOW - timedelta(minutes=30)).isoformat(), "feedback_at": None,
        "outcome": None, "manual_status": None, "notes": None, "wrapup_callback_at": None,
        "transcript": "[00:01] Telecaller: Hello\n[00:03] Customer: I need a demo",
        "evaluation": {"evaluation_version": 4, "group": "real_conversation", "checks": _checks(), "signs": []},
    }
    row.update(kw)
    return row


class CrmExpectedTests(unittest.TestCase):
    def test_mapping(self):
        self.assertTrue(cm.crm_matches_expected("wrong_number", {"manual_status": "wrong_number"}))
        self.assertFalse(cm.crm_matches_expected("wrong_number", {"outcome": "interested"}))
        self.assertTrue(cm.crm_matches_expected("not_enquired", {"outcome": "not_interested"}))
        self.assertTrue(cm.crm_matches_expected("callback", {"outcome": "callback", "callback_at": "2026-09-26T05:00:00+00:00"}))
        self.assertFalse(cm.crm_matches_expected("callback", {"outcome": "callback", "callback_at": None}))
        self.assertIsNone(cm.crm_matches_expected("language_barrier", {"outcome": "not_interested"}))
        self.assertIsNone(cm.crm_matches_expected("voicemail", {"outcome": None}))
        self.assertIsNone(cm.crm_matches_expected("other", {"outcome": "interested"}))


class MarkCrmUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, row, ai=None):
        db = MagicMock()
        writes = []
        db.table.return_value.update.side_effect = lambda payload: writes.append(payload) or db.table.return_value.update.return_value
        with patch.object(cm, "_load_row", return_value=row), \
             patch.object(cm, "wrapup_snapshot", side_effect=lambda db, r: None if not r.get("feedback_at") else {"outcome": r.get("outcome"), "manual_status": r.get("manual_status"), "notes": r.get("notes"), "callback_at": r.get("wrapup_callback_at"), "do_not_call": False}), \
             patch.object(cm, "gemini_analysis_json", AsyncMock(return_value=ai or {"level": "excellent", "reason": "matches"})) as gem, \
             patch.object(cm, "raise_alert") as alert, \
             patch.object(cm, "finalize_call_score") as fin:
            changed = await cm.mark_crm_update(db, "call-1", now=NOW)
        return changed, writes, gem, alert, fin

    async def test_no_wrapup_before_cutoff_does_nothing(self):
        changed, writes, gem, _, _ = await self._run(_row())
        self.assertFalse(changed)
        self.assertEqual(writes, [])
        gem.assert_not_called()

    async def test_no_wrapup_after_cutoff_is_missing_without_ai(self):
        row = _row(created_at=(NOW - timedelta(hours=2, minutes=1)).isoformat())
        changed, writes, gem, _, fin = await self._run(row)
        self.assertTrue(changed)
        gem.assert_not_called()
        crm = writes[0]["evaluation"]["checks"][-1]
        self.assertEqual((crm["level"], crm["marks"]), ("missing", 0.0))
        fin.assert_called_once()

    async def test_wrapup_marks_with_ai_and_leaves_other_checks(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="interested", notes="needs demo friday")
        changed, writes, gem, _, _ = await self._run(row, ai={"level": "good", "reason": "notes thin"})
        checks = writes[0]["evaluation"]["checks"]
        self.assertEqual(checks[-1]["level"], "good")
        self.assertEqual(checks[-1]["marks"], 5.25)
        self.assertEqual([c["level"] for c in checks[:-1]], ["good"] * 9)
        self.assertEqual(gem.call_args.kwargs["temperature"], 0.0)

    async def test_changed_wrapup_is_remarked(self):
        row = _row(feedback_at=NOW.isoformat(), outcome="callback", wrapup_callback_at=None)
        row["evaluation"]["checks"] = _checks(crm_level="excellent")
        row["evaluation"]["crm_wrapup"] = {"outcome": "interested", "manual_status": None, "notes": None, "callback_at": None, "do_not_call": False}
        changed, writes, gem, _, _ = await self._run(row, ai={"level": "poor", "reason": "callback without time"})
        self.assertTrue(changed)
        self.assertEqual(writes[0]["evaluation"]["checks"][-1]["level"], "poor")

    async def test_same_wrapup_not_remarked(self):
        snap = {"outcome": "interested", "manual_status": None, "notes": None, "callback_at": None, "do_not_call": False}
        row = _row(feedback_at=NOW.isoformat(), outcome="interested")
        row["evaluation"]["checks"] = _checks(crm_level="excellent")
        row["evaluation"]["crm_wrapup"] = snap
        changed, _, gem, _, _ = await self._run(row)
        self.assertFalse(changed)
        gem.assert_not_called()

    async def test_early_exit_mismatch_raises_alert_without_ai(self):
        row = _row(call_group="early_exit", feedback_at=NOW.isoformat(), outcome="interested",
                   evaluation={"evaluation_version": 4, "group": "early_exit",
                               "early_exit_check": {"expected_crm": "wrong_number", "crm_matches": None}})
        changed, writes, gem, alert, _ = await self._run(row)
        gem.assert_not_called()
        self.assertFalse(writes[0]["evaluation"]["early_exit_check"]["crm_matches"])
        self.assertEqual(alert.call_args.kwargs["type"], "crm_mismatch")

    async def test_ai_not_done_yet_waits(self):
        changed, writes, _, _, _ = await self._run(_row(ai_status="scoring", feedback_at=NOW.isoformat(), evaluation=None))
        self.assertFalse(changed)
        self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 7: Add check 10 to `call_marking.py`**

Append to `call_marking.py`, plus these imports at the top: `from datetime import datetime, timedelta, timezone`, `from app.services.call_alerts import raise_alert`, `from app.services.call_lines import parse_transcript`, `from app.services.call_scorer import finalize_call_score`, `from app.services.scoring_rules import WRAPUP_CUTOFF_HOURS`. This creates no import cycle: `call_scorer` imports only `scoring_rules` at module level and reaches `call_marking.total_score` lazily inside `compute_call_score`. `call_scorer` is rewritten in Task 8. Until then, create it in this task with just the Task 8 Step 3 content, so the import resolves. Task 8 then only adds its tests.

```python
# ── Check 10: CRM update, from the telecaller's wrap-up ─────────────────

_CRM_ROW_FIELDS = (
    "id,tenant_id,caller_id,lead_id,provider,call_group,ai_status,created_at,feedback_at,"
    "outcome,manual_status,notes,wrapup_callback_at,transcript,evaluation"
)

_CRM_PROMPT = """A telecaller just finished this sales call and saved a wrap-up. Mark check 10 (CRM update).

Transcript:
{transcript}

Wrap-up saved:
- outcome: {outcome}
- status: {manual_status}
- do not call: {do_not_call}
- callback date/time: {callback_at}
- notes: {notes}

Correct status guide (our system has no Hot/Warm/Cold: "interested" is right for both hot and warm customers):
- converted: the customer bought/booked.
- interested: ready soon or interested but needs time or information.
- callback: the customer asked to be called later; a date and time must be set.
- not_interested: low interest, not a fit, never enquired or clearly not interested.
- do not call: the customer clearly asked not to be contacted again.

Levels: "excellent" = status matches the call, the notes cover the key points (need, budget, next step) and the callback time is set if one was agreed; "good" = status correct, notes thin; "partial" = status slightly off; "poor" = status wrong; "missing" = nothing useful saved.
Return JSON only: {{"level": "...", "reason": "one line"}}"""


def crm_matches_expected(expected: str, wrapup: dict) -> bool | None:
    """Early-exit check 3. None when our wrap-up has no status for that situation."""
    if expected == "wrong_number":
        return wrapup.get("manual_status") == "wrong_number"
    if expected == "not_enquired":
        return wrapup.get("outcome") == "not_interested" or bool(wrapup.get("do_not_call"))
    if expected == "callback":
        return wrapup.get("outcome") == "callback" and bool(wrapup.get("callback_at"))
    return None


def _load_row(db, call_log_id: str) -> dict | None:
    res = db.table("call_logs").select(_CRM_ROW_FIELDS).eq("id", call_log_id).maybe_single().execute()
    return res.data if res else None


def wrapup_snapshot(db, row: dict) -> dict | None:
    if not row.get("feedback_at"):
        return None
    dnc = False
    if row.get("lead_id"):
        lead = db.table("leads").select("do_not_call").eq("id", row["lead_id"]).maybe_single().execute()
        dnc = bool(((lead.data if lead else None) or {}).get("do_not_call"))
    return {
        "outcome": row.get("outcome"), "manual_status": row.get("manual_status"), "notes": row.get("notes"),
        "callback_at": row.get("wrapup_callback_at"), "do_not_call": dnc,
    }


def _past_cutoff(row: dict, now: datetime) -> bool:
    created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
    return now - created >= timedelta(hours=WRAPUP_CUTOFF_HOURS)


async def mark_crm_update(db, call_log_id: str, *, now: datetime | None = None) -> bool:
    """Mark (or re-mark) check 10 / the early-exit CRM check. Safe to call any time."""
    now = now or datetime.now(timezone.utc)
    row = _load_row(db, call_log_id)
    evaluation = (row or {}).get("evaluation") or {}
    if not row or row.get("ai_status") != "done" or evaluation.get("evaluation_version") != 4:
        return False
    snap = wrapup_snapshot(db, row)
    group = evaluation.get("group")

    if group == "early_exit":
        early = dict(evaluation.get("early_exit_check") or {})
        if snap is None or evaluation.get("crm_wrapup") == snap:
            return False
        matches = crm_matches_expected(early.get("expected_crm", "other"), snap)
        early["crm_matches"] = matches
        new_eval = {**evaluation, "early_exit_check": early, "crm_wrapup": snap}
        db.table("call_logs").update({"evaluation": new_eval}).eq("id", call_log_id).execute()
        if matches is False:
            raise_alert(db, tenant_id=row["tenant_id"], type="crm_mismatch", call_log_id=call_log_id,
                        caller_id=row.get("caller_id"),
                        quote=f"Call looked like '{early.get('expected_crm')}', wrap-up says '{snap.get('manual_status') or snap.get('outcome')}'")
        finalize_call_score(db, call_log_id)
        return True

    checks = [dict(c) for c in evaluation.get("checks") or []]
    if not checks:
        return False
    crm = checks[-1]
    if snap is None:
        if crm.get("level") is not None or not _past_cutoff(row, now):
            return False
        crm.update({"level": "missing", "ai_level": None, "marks": 0.0,
                    "reason": f"No wrap-up saved within {WRAPUP_CUTOFF_HOURS} hours of the call."})
    else:
        if evaluation.get("crm_wrapup") == snap and crm.get("level") is not None:
            return False
        data = await gemini_analysis_json(
            system_prompt=_SYSTEM,
            user_prompt=_CRM_PROMPT.format(transcript=format_transcript(parse_transcript(row.get("transcript"))), **{k: snap.get(k) or "—" for k in snap}),
            tenant_id=row.get("tenant_id"), temperature=0.0, purpose="call_crm_check", max_tokens=400,
        )
        level = data.get("level")
        if level not in LEVEL_ORDER:
            raise CallMarkingError("no valid level for check crm_update")
        crm.update({"level": level, "ai_level": level, "marks": round(check_marks("crm_update", level), 2),
                    "reason": clip(data.get("reason"))})
        if level in ("poor", "missing"):
            raise_alert(db, tenant_id=row["tenant_id"], type="crm_mismatch", call_log_id=call_log_id,
                        caller_id=row.get("caller_id"), quote=clip(data.get("reason")))
    checks[-1] = crm
    new_eval = {**evaluation, "checks": checks, "top_improve": top_improve(checks), "crm_wrapup": snap}
    db.table("call_logs").update({"evaluation": new_eval}).eq("id", call_log_id).execute()
    finalize_call_score(db, call_log_id)
    return True
```

Also add a `max_tokens` pass-through: `gemini_analysis_json` already has `max_tokens: int = 3000`, so no change is needed.

- [ ] **Step 8: Run all the new tests to confirm they pass**

Run: `cd backend && python -m pytest tests/test_call_crm_check.py tests/test_call_alerts.py tests/test_call_marking.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/supabase/migrations/205_call_scoring_v4.sql backend/app/services/call_alerts.py backend/app/services/call_marking.py backend/tests/test_call_alerts.py backend/tests/test_call_crm_check.py
git commit -m "feat(calls): call_alerts list and check 10 from the wrap-up" -- backend/supabase/migrations/205_call_scoring_v4.sql backend/app/services/call_alerts.py backend/app/services/call_marking.py backend/tests/test_call_alerts.py backend/tests/test_call_crm_check.py
```

---

### Task 8: New scorer + pipeline wiring + removal of the old scorer

**Files:**
- Rewrite: `backend/app/services/call_scorer.py`
- Modify: `backend/app/services/call_ai_pipeline.py`
- Delete: `backend/app/services/call_summarizer.py`, `backend/tests/test_call_summarizer_v3.py`, `backend/tests/test_call_scorer_v3.py`
- Modify: `backend/app/services/call_audio.py` (delete `audio_for_evaluation`) + `backend/tests/test_call_audio.py` (delete its test)
- Modify: `backend/tests/test_call_ai_pipeline.py`, `backend/tests/test_audio_format.py:107`
- Test: `backend/tests/test_call_scorer_v4.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: `call_scorer.compute_call_score(*, status, duration, ai_status, evaluation) -> dict` with keys `call_group, score_status, score, score_final`; `call_scorer.finalize_call_score(db, call_log_id) -> dict | None`; `call_scorer.TERMINAL_STATUSES`; pipeline `run_call_ai`, `sweep_call_ai`, `sweep_crm_cutoff() -> int`, `queue_call_ai`, `retry_call_ai` (same names as today).

- [ ] **Step 1: Write the failing scorer tests** (`backend/tests/test_call_scorer_v4.py`)

```python
"""Group + score status for every TeleCMI call; the score is only ever the sum of the checks."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.call_marking import CHECKS, check_marks
from app.services.call_scorer import compute_call_score


def _eval(group="real_conversation", crm="excellent"):
    if group == "early_exit":
        return {"evaluation_version": 4, "group": "early_exit", "early_exit_check": {}}
    levels = {"opening": "excellent", "courtesy": "good", "questions": "good", "listening": "partial",
              "product_info": "good", "doubts": "excellent", "clarity": "good", "next_step": "excellent",
              "decision": "partial", "crm_update": crm}
    return {"evaluation_version": 4, "group": group,
            "checks": [{"key": c["key"], "level": levels[c["key"]], "marks": check_marks(c["key"], levels[c["key"]])} for c in CHECKS]}


def _score(**kw):
    args = {"status": "completed", "duration": 480, "ai_status": "done", "evaluation": _eval()}
    args.update(kw)
    return compute_call_score(**args)


class ComputeTests(unittest.TestCase):
    def test_not_connected(self):
        for status, duration in (("no_answer", 0), ("missed", 0), ("failed", 0), ("completed", 0)):
            r = _score(status=status, duration=duration, ai_status=None, evaluation=None)
            self.assertEqual((r["call_group"], r["score_status"], r["score"]), ("not_connected", "not_connected", None))

    def test_very_short_under_30s(self):
        r = _score(duration=29, ai_status=None, evaluation=None)
        self.assertEqual((r["call_group"], r["score_status"], r["score_final"]), ("very_short", "very_short", True))

    def test_in_progress_call(self):
        self.assertEqual(_score(status="initiated")["score_status"], "processing")

    def test_processing_and_failed(self):
        self.assertEqual(_score(ai_status="transcribing", evaluation=None)["score_status"], "processing")
        self.assertEqual(_score(ai_status="failed", evaluation=None)["score_status"], "failed")

    def test_old_v3_evaluation_is_processing_not_scored(self):
        self.assertEqual(_score(evaluation={"evaluation_version": 3})["score_status"], "processing")

    def test_early_exit_has_no_score(self):
        r = _score(evaluation=_eval("early_exit"))
        self.assertEqual((r["call_group"], r["score_status"], r["score"], r["score_final"]), ("early_exit", "early_exit", None, True))

    def test_real_conversation_full_score(self):
        r = _score()
        self.assertEqual((r["call_group"], r["score_status"], r["score"], r["score_final"]), ("real_conversation", "scored", 78.5, True))

    def test_pending_crm_is_provisional(self):
        r = _score(evaluation=_eval(crm=None))
        self.assertEqual((r["score_status"], r["score"], r["score_final"]), ("provisional", 71.5, False))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd backend && python -m pytest tests/test_call_scorer_v4.py -v`
Expected: FAIL (`compute_call_score()` got unexpected keyword / old signature)

- [ ] **Step 3: Rewrite `call_scorer.py` completely**

```python
"""Group and score for TeleCMI calls (CallIQ Steps 1-2).

not_connected / very_short get no AI at all. early_exit gets the basic check but
no score. real_conversation is the sum of the 10 checks out of 100 — provisional
until check 10 (the wrap-up) is marked. Recomputed from the stored row every time
an input changes, so arrival order doesn't matter.
"""
import logging

from app.services.scoring_rules import MIN_SCORED_SECONDS, RULES_VERSION

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "no_answer", "missed", "failed")
SCORED_PROVIDERS = ("telecmi",)
_ROW_FIELDS = "id,provider,status,duration_seconds,ai_status,evaluation"


def compute_call_score(*, status: str | None, duration: int | None, ai_status: str | None, evaluation: dict | None) -> dict:
    from app.services.call_marking import total_score

    result = {"call_group": None, "score_status": "processing", "score": None, "score_final": False}
    if status not in TERMINAL_STATUSES:
        return result
    seconds = duration or 0
    if status != "completed" or seconds == 0:
        return {**result, "call_group": "not_connected", "score_status": "not_connected", "score_final": True}
    if seconds < MIN_SCORED_SECONDS:
        return {**result, "call_group": "very_short", "score_status": "very_short", "score_final": True}
    if ai_status == "failed":
        return {**result, "score_status": "failed"}
    if ai_status != "done" or not evaluation or evaluation.get("evaluation_version") != 4:
        return result
    if evaluation.get("group") == "early_exit":
        return {**result, "call_group": "early_exit", "score_status": "early_exit", "score_final": True}
    checks = evaluation.get("checks") or []
    final = bool(checks) and all(c.get("level") for c in checks)
    return {
        "call_group": "real_conversation",
        "score_status": "scored" if final else "provisional",
        "score": total_score(checks),
        "score_final": final,
    }


def finalize_call_score(db, call_log_id: str) -> dict | None:
    """Recompute and store the group/score for one call. Safe to call any number of times."""
    res = db.table("call_logs").select(_ROW_FIELDS).eq("id", call_log_id).maybe_single().execute()
    row = res.data if res else None
    if not row or row.get("provider") not in SCORED_PROVIDERS:
        return None
    result = compute_call_score(
        status=row.get("status"), duration=row.get("duration_seconds"),
        ai_status=row.get("ai_status"), evaluation=row.get("evaluation"),
    )
    db.table("call_logs").update({**result, "rules_version": RULES_VERSION}).eq("id", call_log_id).execute()
    return result
```

- [ ] **Step 4: Run the scorer tests to confirm they pass**

Run: `cd backend && python -m pytest tests/test_call_scorer_v4.py -v`
Expected: PASS

- [ ] **Step 5: Rewire `call_ai_pipeline.py`**

1. Imports: replace the `call_scorer`/`call_summarizer` imports with:

```python
from app.services.call_alerts import raise_alert
from app.services.call_lines import format_transcript
from app.services.call_marking import mark_call, mark_crm_update, top_improve
from app.services.call_metrics import talk_share as compute_talk_share
from app.services.call_scorer import finalize_call_score
from app.services.call_sorting import sort_call
from app.services.call_tracks import count_interruptions, per_5_min
from app.services.call_transcribe import transcribe_tracks, tracks_look_swapped
from app.services.scoring_rules import MIN_SCORED_SECONDS, RULES_VERSION, WRAPUP_CUTOFF_HOURS
```

2. Set `MAX_ATTEMPTS = 2` (the method document: "try again once").
3. Delete `_selected_criteria`.
4. In `_claim`, add `status` to the select list.
5. Replace `_process` with:

```python
def _company_name(db, tenant_id: str | None) -> str | None:
    if not tenant_id:
        return None
    res = db.table("tenants").select("name").eq("id", tenant_id).maybe_single().execute()
    name = ((res.data if res else None) or {}).get("name")
    return name if isinstance(name, str) else None


def _previous_notes(db, lead_id: str | None, call_log_id: str) -> str:
    if not lead_id:
        return ""
    rows = (
        db.table("lead_notes").select("content,created_at").eq("lead_id", lead_id)
        .neq("call_log_id", call_log_id).order("created_at", desc=True).limit(5).execute()
    ).data or []
    return "\n".join(f"- {r['content']}" for r in rows if r.get("content"))


async def _process(db, row: dict, appid_override: str | None) -> None:
    from app.services.knowledge_service import get_knowledge_context

    call_log_id = row["id"]
    tenant_id = row.get("tenant_id")
    duration = row.get("duration_seconds") or 0
    if duration < MIN_SCORED_SECONDS:
        # Very short calls get no AI at all — not even a transcript.
        db.table("call_logs").update({"ai_status": "done", "ai_error": None, "ai_updated_at": _now()}).eq("id", call_log_id).execute()
        return

    audio, mime_type = await _load_audio(db, row, appid_override)
    tracks = await transcribe_tracks(audio, mime_type, tenant_id=tenant_id)
    if not tracks.lines:
        raise RuntimeError("the transcript came back empty")
    transcript = format_transcript(tracks.lines)
    share = compute_talk_share(tracks.lines)
    count = count_interruptions(tracks.telecaller_segments, tracks.customer_segments) if tracks.stereo else None
    ipm = per_5_min(count, duration)
    db.table("call_logs").update({
        "transcript": transcript, "talk_share": share,
        "interruption_count": count, "interruptions_per_5min": ipm,
    }).eq("id", call_log_id).execute()

    _set_stage(db, call_log_id, "scoring")
    caller_id = row.get("caller_id")
    if tracks.stereo and tracks_look_swapped(tracks.lines, _company_name(db, tenant_id)):
        raise_alert(db, tenant_id=tenant_id, type="tracks_swapped", call_log_id=call_log_id, caller_id=caller_id,
                    quote="The 'calling from…' words were heard on the customer's track.")

    sorting = await sort_call(tracks.lines, tenant_id=tenant_id)
    evaluation: dict = {
        "evaluation_version": 4, "rules_version": RULES_VERSION, "group": sorting.group,
        "signs": sorting.signs, "valid_sign_count": len(sorting.signs),
        "language_barrier": sorting.language_barrier,
    }
    rude_quote = sorting.rude_quote
    if sorting.group == "real_conversation":
        kb_context = await get_knowledge_context(tenant_id, query=transcript[:1500]) if tenant_id else ""
        marking = await mark_call(
            tracks.lines, kb_context=kb_context, previous_notes=_previous_notes(db, row.get("lead_id"), call_log_id),
            talk_share=share, interruptions_per_5min=ipm, interruption_count=count,
            duration_seconds=duration, tenant_id=tenant_id,
        )
        evaluation.update({
            "checks": marking.checks, "top_improve": top_improve(marking.checks), "tips": marking.tips,
            "wrong_info": marking.wrong_info, "unverified_claims": marking.unverified_claims,
        })
        rude_quote = rude_quote or marking.rude_quote
        for item in marking.wrong_info:
            raise_alert(db, tenant_id=tenant_id, type="wrong_info", call_log_id=call_log_id, caller_id=caller_id,
                        quote=f"[{item['time']}] {item['quote']}", detail={"kb_fact": item.get("kb_fact")})
        if marking.proof_missing:
            raise_alert(db, tenant_id=tenant_id, type="no_proof", call_log_id=call_log_id, caller_id=caller_id,
                        quote=f"No proof for: {', '.join(marking.proof_missing)}", detail={"checks": marking.proof_missing})
    else:
        evaluation["early_exit_check"] = sorting.early_exit_check
    if rude_quote:
        raise_alert(db, tenant_id=tenant_id, type="rude", call_log_id=call_log_id, caller_id=caller_id, quote=rude_quote)
    if sorting.language_barrier:
        raise_alert(db, tenant_id=tenant_id, type="language_barrier", call_log_id=call_log_id, caller_id=caller_id,
                    quote=sorting.language_barrier_quote)

    db.table("call_logs").update({
        "ai_summary": sorting.summary, "evaluation": evaluation, "ai_status": "done",
        "ai_error": None, "ai_updated_at": _now(),
    }).eq("id", call_log_id).execute()
    logger.info(f"Call {call_log_id} sorted as {sorting.group} ({len(sorting.signs)} signs)")

    if sorting.summary.get("next_action") and row.get("lead_id"):
        note_row = {
            "lead_id": row["lead_id"], "call_log_id": call_log_id,
            "content": f"AI Summary: {sorting.summary['next_action']}",
            "structured": sorting.summary, "is_pinned": False,
        }
        if tenant_id:
            note_row["tenant_id"] = tenant_id
        db.table("lead_notes").insert(note_row).execute()
```

6. In `run_call_ai`: in the `except` branch, when `final` is True also raise the alert:

```python
            if final:
                raise_alert(db, tenant_id=row.get("tenant_id"), type="transcript_failed", call_log_id=call_log_id,
                            caller_id=row.get("caller_id"), quote=error[:240])
```

After the `finalize_call_score` try-block, add:

```python
        try:
            await mark_crm_update(db, call_log_id)
        except Exception as e:
            logger.error(f"CRM check failed for call {call_log_id}: {e}")
```

In `sweep_call_ai`, where a row is marked failed after max attempts, add the same `transcript_failed` alert. The select there must include `tenant_id,caller_id`.

7. Add the cut-off sweep:

```python
async def sweep_crm_cutoff() -> int:
    """Check 10 for real conversations whose wrap-up never came (Missing after the cut-off),
    or whose wrap-up arrived while the AI was still running."""
    db = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=WRAPUP_CUTOFF_HOURS)).isoformat()
    rows = (
        db.table("call_logs").select("id")
        .eq("provider", "telecmi").eq("ai_status", "done").eq("score_final", False)
        .in_("call_group", ["real_conversation", "early_exit"])
        .lt("created_at", cutoff).limit(SWEEP_BATCH).execute()
    ).data or []
    changed = 0
    for r in rows:
        try:
            changed += int(await mark_crm_update(db, r["id"]))
        except Exception as e:
            logger.error(f"CRM cut-off sweep failed for {r['id']}: {e}")
    return changed
```

Early-exit calls are already `score_final=True` from `compute_call_score`, so this query naturally returns only provisional real conversations. `early_exit` is listed for clarity and costs nothing.

- [ ] **Step 6: Delete the old code and its tests**

```bash
cd /c/Users/vskee/Desktop/Aira-Ai && git rm -q backend/app/services/call_summarizer.py backend/tests/test_call_summarizer_v3.py backend/tests/test_call_scorer_v3.py
```

In `call_audio.py`, delete `audio_for_evaluation`. In `backend/tests/test_call_audio.py`, delete the test that calls it (around line 121). In `backend/tests/test_audio_format.py:107`, the assertion `"transcribe_call(audio, mime_type"` must become `"transcribe_tracks(audio, mime_type"`.

- [ ] **Step 7: Update `test_call_ai_pipeline.py`**

Replace the old `transcribe_call`/`analyze_call` patches in its `_process` helper with the new collaborators, and add these tests:

```python
from app.services.call_lines import Line
from app.services.call_transcribe import TrackTranscript
from app.services.call_sorting import SortResult
from app.services.call_marking import MarkResult, CHECKS


def _tracks():
    return TrackTranscript([Line(1, "telecaller", "Hello"), Line(3, "customer", "I need a demo")], [(1.0, 2.0)], [(3.0, 5.0)], True)


def _sort(group):
    early = None if group == "real_conversation" else {"polite": True, "rude_quote": None, "enquiry_confirmed_early": False, "expected_crm": "other", "crm_matches": None}
    return SortResult(group, [], {"next_action": "Call back"}, early, False, None, None)


class NewFlowTests(unittest.IsolatedAsyncioTestCase):
    async def _process(self, db, row, group):
        marking = MarkResult(checks=[{"key": c["key"], "full": c["full"], "level": "good" if c["key"] != "crm_update" else None} for c in CHECKS])
        with patch.object(pipe, "_load_audio", AsyncMock(return_value=(b"wav", "audio/wav"))), \
             patch.object(pipe, "transcribe_tracks", AsyncMock(return_value=_tracks())), \
             patch.object(pipe, "sort_call", AsyncMock(return_value=_sort(group))), \
             patch.object(pipe, "mark_call", AsyncMock(return_value=marking)) as mark, \
             patch.object(pipe, "raise_alert") as alert, \
             patch("app.services.knowledge_service.get_knowledge_context", AsyncMock(return_value="")):
            await pipe._process(db, row, None)
        return mark, alert

    async def test_very_short_call_is_never_transcribed(self):
        db = MagicMock()
        with patch.object(pipe, "transcribe_tracks", AsyncMock()) as tr:
            await pipe._process(db, {"id": "c", "tenant_id": "t", "duration_seconds": 20}, None)
        tr.assert_not_called()

    async def test_early_exit_skips_marking(self):
        mark, _ = await self._process(MagicMock(), {"id": "c", "tenant_id": "t", "duration_seconds": 90, "lead_id": None}, "early_exit")
        mark.assert_not_called()

    async def test_real_conversation_is_marked(self):
        mark, _ = await self._process(MagicMock(), {"id": "c", "tenant_id": "t", "duration_seconds": 90, "lead_id": None}, "real_conversation")
        mark.assert_called_once()
```

Remove any existing test that references `analyze_call`, `transcribe_call`, `_selected_criteria` or `EVALUATION = {"evaluation_version": 3 ...}`, and adapt the existing claim/retry/sweep tests to `MAX_ATTEMPTS = 2`.

- [ ] **Step 8: Run the whole backend suite**

Run: `cd backend && python -m pytest -q`
Expected: no failures except the known environmental ones recorded in `.agents/decisions/log.md` (`test_analytics_compare_routes`, `test_intake_csv` StreamingResponse issue). Anything touching call scoring must pass. `grep -rn "call_summarizer\|analyze_call\|SCORE_CRITERIA\|audio_for_evaluation" backend/app backend/tests` must return nothing except `telecaller_performance.py` and `app_settings.py` (Task 9 fixes those).

- [ ] **Step 9: Commit**

```bash
git add -A backend/app/services/call_scorer.py backend/app/services/call_ai_pipeline.py backend/app/services/call_audio.py backend/tests/test_call_scorer_v4.py backend/tests/test_call_ai_pipeline.py backend/tests/test_call_audio.py backend/tests/test_audio_format.py backend/app/services/call_summarizer.py backend/tests/test_call_summarizer_v3.py backend/tests/test_call_scorer_v3.py
git commit -m "feat(calls): wire v4 sorting+marking into the pipeline, remove the 7+3 scorer" -- backend/app/services/call_scorer.py backend/app/services/call_ai_pipeline.py backend/app/services/call_audio.py backend/tests/test_call_scorer_v4.py backend/tests/test_call_ai_pipeline.py backend/tests/test_call_audio.py backend/tests/test_audio_format.py backend/app/services/call_summarizer.py backend/tests/test_call_summarizer_v3.py backend/tests/test_call_scorer_v3.py
```

---

### Task 9: Routes, settings, performance, scheduler

**Files:**
- Modify: `backend/app/routes/calls.py`, `backend/app/routes/app_settings.py`, `backend/app/routes/analytics.py:780-781`, `backend/app/routes/leads.py:1207`, `backend/app/services/telecaller_performance.py`, `backend/app/main.py`
- Test: `backend/tests/test_calls_scoring_routes.py` (rewrite flag tests → alert tests), `backend/tests/test_telecaller_performance.py` (add cases; create if absent)

**Interfaces:**
- Produces routes: `GET /api/v1/calls/alerts?type=&caller_id=&seen=false&page=1&limit=20` → `{"data": [...], "total": int, "page": int, "limit": int}` where each row = alert fields + `callers: {name}` + `call_logs: {id, created_at, duration_seconds, lead_id, leads: {name, phone}}`; `GET /api/v1/calls/alerts/count` → `{"count": int}`; `POST /api/v1/calls/alerts/{alert_id}/seen` → the updated row. All three use `require_permission("team.manage")`.

- [ ] **Step 1: Card fields.** In `calls.py:34-35`, `analytics.py:780-781` and `leads.py:1207`, remove `score_breakdown`, `flag_status`, `flag_reason`, `flagged_at`, `flag_resolved_at` from the select strings. Add `call_group,talk_share,interruption_count,interruptions_per_5min,score_final`.

- [ ] **Step 2: Wrap-up.** In `set_outcome` (`calls.py`):
  - Remove the `flag_status` column from its select, and delete the whole "A flag raised by the no-answer safety gate…" 409 block.
  - After `if payload.callback_time ...` data is known, add `log_updates["wrapup_callback_at"] = payload.callback_time.isoformat()` when `payload.callback_time is not None`.
  - Replace `scoring = finalize_call_score(db, call_log_id) if effective_outcome is not None else None` with:

```python
    scoring = finalize_call_score(db, call_log_id) if effective_outcome is not None else None
    if is_telecmi and "feedback_at" in log_updates:
        background_tasks.add_task(mark_crm_update_task, call_log_id)
```

  Add `background_tasks: BackgroundTasks` to `set_outcome`'s signature, and a module-level helper:

```python
async def mark_crm_update_task(call_log_id: str) -> None:
    try:
        await mark_crm_update(get_supabase(), call_log_id)
    except Exception as e:
        logger.error(f"CRM check failed for call {call_log_id}: {e}")
```

  and `from app.services.call_marking import mark_crm_update`.

- [ ] **Step 3: Replace the flag routes.** Delete `flagged_calls`, `FlagResolution` and `resolve_flag`. In their place (same position, before any `/{call_log_id}` GET route) add:

```python
@router.get("/alerts")
async def list_call_alerts(
    type: str | None = Query(None),
    caller_id: UUID | None = Query(None),
    seen: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    ctx: dict = Depends(require_permission("team.manage")),
):
    """The admin's Needs-attention list."""
    db = get_supabase()
    query = (
        db.table("call_alerts")
        .select("id,type,quote,detail,created_at,seen_at,caller_id,call_log_id,callers(name),"
                "call_logs(id,created_at,duration_seconds,lead_id,leads(name,phone))", count="exact")
        .eq("tenant_id", ctx["tenant_id"])
    )
    query = query.not_.is_("seen_at", "null") if seen else query.is_("seen_at", "null")
    if type:
        query = query.eq("type", type)
    if caller_id:
        query = query.eq("caller_id", str(caller_id))
    offset = (page - 1) * limit
    rows = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return {"data": rows.data or [], "total": rows.count or 0, "page": page, "limit": limit}


@router.get("/alerts/count")
async def count_call_alerts(ctx: dict = Depends(require_permission("team.manage"))):
    db = get_supabase()
    res = db.table("call_alerts").select("id", count="exact").eq("tenant_id", ctx["tenant_id"]).is_("seen_at", "null").limit(1).execute()
    return {"count": res.count or 0}


@router.post("/alerts/{alert_id}/seen")
async def mark_call_alert_seen(alert_id: UUID, ctx: dict = Depends(require_permission("team.manage"))):
    db = get_supabase()
    res = (
        db.table("call_alerts")
        .update({"seen_at": datetime.now(timezone.utc).isoformat(), "seen_by": ctx.get("user_id")})
        .eq("id", str(alert_id)).eq("tenant_id", ctx["tenant_id"]).execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Alert not found")
    return res.data[0]
```

- [ ] **Step 4: Route tests.** In `backend/tests/test_calls_scoring_routes.py`, delete the flag tests (lines referencing `flag_status`/`resolve_flag`/`/flagged`). Add, in the file's existing style (it calls route functions with a mocked `get_supabase`):

```python
    async def test_alert_seen_is_tenant_scoped(self):
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        with patch.object(calls, "get_supabase", return_value=db):
            with self.assertRaises(HTTPException) as err:
                await calls.mark_call_alert_seen(uuid4(), ctx={"tenant_id": "t", "user_id": "u"})
        self.assertEqual(err.exception.status_code, 404)
```

Then add one `set_outcome` test by copying the file's existing successful `set_outcome` test (same mocked `db` fixture) into `test_telecmi_wrapup_queues_crm_check`. Change it so the row is `{"provider": "telecmi", "status": "completed", "duration_seconds": 250, "lead_id": None}` and it passes a `MagicMock()` as `background_tasks`. Assert `background_tasks.add_task.assert_called_once_with(calls.mark_crm_update_task, <call_log_id>)`.

- [ ] **Step 5: Remove the criteria setting.** In `app_settings.py`, delete the `score_criteria` field (line ~153) and the `if "score_criteria" in patch:` block (~1993-2000). Confirm no tenant stored it:

```sql
select count(*) from app_settings where key='telecalling_config' and value like '%score_criteria%';
```
Expected: `0` (it was 0 on 2026-09-25). If not 0, strip the key from those rows with an `update` via `execute_sql` before shipping.

- [ ] **Step 6: Performance on the 100 scale.** In `telecaller_performance.py`:
  - Replace the `SCORE_CRITERIA` import with `from app.services.call_marking import CHECKS`.
  - In `summarize_calls`, replace the criteria loop with check averages as a share of full marks (0–100):

```python
            for check in evaluation.get("checks") or []:
                if check.get("level") and check.get("full"):
                    key = check["key"]
                    criteria_sums[key] = criteria_sums.get(key, 0.0) + check_marks(key, check["level"]) / check["full"] * 100
                    criteria_counts[key] = criteria_counts.get(key, 0) + 1
```

  and replace the existing `criteria_avg = …` line after the loop with:

```python
    criteria_avg = {c["key"]: round(criteria_sums[c["key"]] / criteria_counts[c["key"]], 1) for c in CHECKS if c["key"] in criteria_counts}
```
  (import `check_marks` too). Only rows with `score_status == "scored"` feed `avg_score`, so check what the existing `scored_calls` filter uses and switch it to `score_status in ("scored",)`.
  - In `rank_winner`, change `volume = s["total_calls"] / busiest * 10` to `* 100`.
  - Test (`backend/tests/test_telecaller_performance.py`): `rank_winner` with two callers (avg 80 and 70, calls 10 and 20, min_scored 1) → points `0.7*80+0.3*50 = 71.0` vs `0.7*70+0.3*100 = 79.0`, so the second caller wins.

- [ ] **Step 7: Scheduler.** In `main.py`, add next to `_sweep_call_ai`:

```python
async def _sweep_crm_cutoff() -> None:
    _heartbeats["crm-cutoff-sweep"] = datetime.now(timezone.utc)
    try:
        from app.services.call_ai_pipeline import sweep_crm_cutoff
        await sweep_crm_cutoff()
    except Exception as e:
        logger.error(f"CRM cut-off sweep error: {e}")


async def _send_call_alert_summaries() -> None:
    _heartbeats["call-alert-summary"] = datetime.now(timezone.utc)
    try:
        from app.db.supabase import get_supabase
        from app.services.call_alerts import send_morning_summaries
        send_morning_summaries(get_supabase())
    except Exception as e:
        logger.error(f"Call alert summary error: {e}")
```

and in `lifespan`:

```python
    _scheduler.add_job(_sweep_crm_cutoff, trigger="interval", minutes=10, id="crm-cutoff-sweep",
                       replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.add_job(_send_call_alert_summaries, trigger="cron", hour=MORNING_SUMMARY_HOUR_IST, minute=0,
                       timezone="Asia/Kolkata", id="call-alert-summary", replace_existing=True)
```

(import `MORNING_SUMMARY_HOUR_IST` from `app.services.scoring_rules`), and append `+ crm-cutoff-sweep(10m) + call-alert-summary(09:00 IST)` to the startup log line.

- [ ] **Step 8: Run the backend suite**

Run: `cd backend && python -m pytest -q`
Expected: same pass state as Task 8 Step 8. Then run `grep -rn "flag_status\|score_breakdown\|score_criteria\|SCORE_CRITERIA" backend/app`. Expected: no matches.

- [ ] **Step 9: Commit**

```bash
git commit -m "feat(calls): alert routes, wrap-up triggers check 10, 100-point performance, scheduler jobs" -- backend/app/routes/calls.py backend/app/routes/app_settings.py backend/app/routes/analytics.py backend/app/routes/leads.py backend/app/services/telecaller_performance.py backend/app/main.py backend/tests/test_calls_scoring_routes.py backend/tests/test_telecaller_performance.py
```

(`git add` any new test file first.)

---

### Task 10: Frontend types + call card

**Files:**
- Modify: `frontend/lib/api.ts`
- Rewrite: `frontend/components/CallAi.tsx`
- Modify: consumers of removed exports: `FlaggedCalls.tsx` (deleted in Task 11), `TelecallingConfigPanel.tsx` (criteria section removed here), `QaReviewFeed.tsx`/`RecentCallsTab.tsx`/`notes/components/shared.tsx` (unchanged imports: `CallAiDetail`, `CallScorePill`, `anyProcessing`, `scoreColor`, `MaskedTranscript` all keep their names)

**Interfaces:**
- Produces TS types: `CallGroup`, `CheckKey`, `CheckLevel`, `CallCheck`, `CallSign`, `EarlyExitCheck`, `CallEvaluation` (v4), `CallScoreStatus` (`"processing"|"not_connected"|"very_short"|"early_exit"|"provisional"|"scored"|"failed"`), `CallAlertType`, `CallAlert`; `api.calls.alerts(params)`, `api.calls.alertCount()`, `api.calls.markAlertSeen(id)`; exports from `CallAi.tsx`: `CHECK_LABEL: Record<CheckKey,string>`, `scoreColor(score: number)` (0–100), `CallScorePill`, `CallAiDetail`, `MaskedTranscript`, `anyProcessing`.

- [ ] **Step 1: Types in `api.ts`.** Replace `ScoreCriterion`, the v3 `CallEvaluation`, `CallScoreStatus` and `CallScoreBreakdown` (lines ~168-233) with:

```ts
export type CallGroup = "not_connected" | "very_short" | "early_exit" | "real_conversation";
export type CheckKey =
  | "opening" | "courtesy" | "questions" | "listening" | "product_info"
  | "doubts" | "clarity" | "next_step" | "decision" | "crm_update";
export type CheckLevel = "excellent" | "good" | "partial" | "poor" | "missing";

export interface CallCheck {
  key: CheckKey;
  full: number;
  level: CheckLevel | null;
  ai_level: CheckLevel | null;
  capped_by: "talk_share" | "interruptions" | "talk_share_and_interruptions" | "wrong_info" | "rude" | null;
  marks: number | null;
  reason: string | null;
  quote: string | null;
  time: string | null;
  proof_missing: boolean;
}

export interface CallSign { sign: number; speaker: "telecaller" | "customer"; quote: string; time: string }

export interface EarlyExitCheck {
  polite: boolean;
  rude_quote: string | null;
  enquiry_confirmed_early: boolean;
  expected_crm: "wrong_number" | "not_enquired" | "callback" | "language_barrier" | "voicemail" | "other";
  crm_matches: boolean | null;
}

/** v4 evaluation (CallIQ Steps 1-2). Older rows have no evaluation_version 4 and are not shown. */
export interface CallEvaluation {
  evaluation_version: number;
  rules_version?: string;
  group?: "early_exit" | "real_conversation";
  signs?: CallSign[];
  valid_sign_count?: number;
  early_exit_check?: EarlyExitCheck;
  checks?: CallCheck[];
  top_improve?: CheckKey[];
  tips?: string[];
  wrong_info?: { quote: string; time: string; kb_fact: string | null }[];
  unverified_claims?: string[];
  language_barrier?: boolean;
}

export type CallAiStatus = "pending" | "transcribing" | "scoring" | "done" | "failed";
export type CallScoreStatus =
  | "processing" | "not_connected" | "very_short" | "early_exit" | "provisional" | "scored" | "failed";

export type CallAlertType =
  | "rude" | "wrong_info" | "crm_mismatch" | "no_proof" | "transcript_failed"
  | "language_barrier" | "lead_source_quality" | "tracks_swapped";

export interface CallAlert {
  id: string;
  type: CallAlertType;
  quote: string | null;
  detail: Record<string, unknown>;
  created_at: string;
  seen_at: string | null;
  caller_id: string | null;
  call_log_id: string | null;
  callers: { name: string | null } | null;
  call_logs: {
    id: string; created_at: string; duration_seconds: number | null; lead_id: string | null;
    leads: { name: string | null; phone: string | null } | null;
  } | null;
}
```

In `CallLog`, remove `score_breakdown`, `flag_status`, `flag_reason`, `flagged_at`, `flag_resolved_at`, and add:

```ts
  call_group?: CallGroup | null;
  talk_share?: number | null;
  interruption_count?: number | null;
  interruptions_per_5min?: number | null;
  score_final?: boolean;
```

Remove `score_criteria?: ScoreCriterion[];` (~line 789). Replace `flagged` and `resolveFlag` (~1675-1680) with:

```ts
    alerts: (params: { type?: CallAlertType; caller_id?: string; seen?: boolean; page?: number; limit?: number } = {}) => {
      const q = new URLSearchParams();
      if (params.type) q.set("type", params.type);
      if (params.caller_id) q.set("caller_id", params.caller_id);
      q.set("seen", String(params.seen ?? false));
      q.set("page", String(params.page ?? 1));
      q.set("limit", String(params.limit ?? 20));
      return request<{ data: CallAlert[]; total: number; page: number; limit: number }>(`/api/v1/calls/alerts?${q}`);
    },
    alertCount: () => request<{ count: number }>("/api/v1/calls/alerts/count"),
    markAlertSeen: (alertId: string) =>
      request<CallAlert>(`/api/v1/calls/alerts/${alertId}/seen`, { method: "POST" }),
```

(Match the exact request-helper name used by the neighbouring `retryAi` entry. If it isn't `request`, use the same helper it calls.)

- [ ] **Step 2: Rewrite `CallAi.tsx`.** Keep `MaskedTranscript` and `ProcessingBanner` exactly as they are. Delete `SCORE_CRITERIA`, `CRITERION_LABEL`, `OUTCOME_LABEL`, `barColor`, `FlagNotice` and `ScoreBreakdown`, and add the following. The design must match the existing card language (stone palette `#292524/#57534e/#a8a29e/#e8e3db/#faf8f5`, `font-label`/`font-body`/`font-display`, rounded-xl bordered panels), consistent with this file's current look.

```tsx
export const CHECK_LABEL: Record<CheckKey, string> = {
  opening: "Opening", courtesy: "Courtesy & empathy", questions: "Asking questions",
  listening: "Listening", product_info: "Correct product information", doubts: "Clearing doubts",
  clarity: "Clarity", next_step: "Next step", decision: "Asking for the decision", crm_update: "CRM update",
};
const STAGES: { name: string; keys: CheckKey[] }[] = [
  { name: "Connect", keys: ["opening", "courtesy"] },
  { name: "Understand", keys: ["questions", "listening"] },
  { name: "Explain", keys: ["product_info", "doubts", "clarity"] },
  { name: "Close", keys: ["next_step", "decision", "crm_update"] },
];
const LEVEL_LABEL: Record<CheckLevel, string> = {
  excellent: "Excellent", good: "Good", partial: "Partial", poor: "Poor", missing: "Missing",
};
const LEVEL_TONE: Record<CheckLevel, string> = {
  excellent: "text-emerald-700 bg-emerald-50 border-emerald-200",
  good: "text-cyan-700 bg-cyan-50 border-cyan-200",
  partial: "text-amber-700 bg-amber-50 border-amber-200",
  poor: "text-orange-700 bg-orange-50 border-orange-200",
  missing: "text-rose-700 bg-rose-50 border-rose-200",
};
const CAP_NOTE: Record<string, string> = {
  talk_share: "capped by talk share",
  interruptions: "capped by interruptions",
  talk_share_and_interruptions: "capped by talk share and interruptions",
  wrong_info: "wrong information given",
  rude: "rude on the call",
};
const EXPECTED_CRM_LABEL: Record<EarlyExitCheck["expected_crm"], string> = {
  wrong_number: "Wrong number", not_enquired: "Not enquired", callback: "Callback with a date and time",
  language_barrier: "Language barrier", voicemail: "Voicemail / IVR", other: "—",
};

export function scoreColor(score: number): string {
  if (score >= 80) return "text-emerald-700 bg-emerald-50 border-emerald-200";
  if (score >= 60) return "text-cyan-700 bg-cyan-50 border-cyan-200";
  if (score >= 40) return "text-amber-700 bg-amber-50 border-amber-200";
  return "text-rose-700 bg-rose-50 border-rose-200";
}

const MUTED_PILL = `${PILL} bg-[#faf8f5] text-[#a8a29e] border-[#e8e3db]`;

/** Compact status for a call row. */
export function CallScorePill({ log }: { log: CallLog }) {
  if (log.provider !== "telecmi") return null;
  if (isProcessing(log)) {
    return (
      <span className={`${PILL} bg-[#faf8f5] text-[#78716c] border-[#e8e3db]`}>
        <Loader2 size={9} className="animate-spin" />
        {log.ai_status === "scoring" ? "Marking…" : "Transcribing…"}
      </span>
    );
  }
  switch (log.score_status) {
    case "scored":
    case "provisional":
      return log.score != null ? (
        <span className={`${PILL} ${scoreColor(log.score)}`} title={log.score_status === "provisional" ? "Provisional until the wrap-up is saved" : undefined}>
          {log.score.toFixed(1)}/100{log.score_status === "provisional" ? " · provisional" : ""}
        </span>
      ) : null;
    case "early_exit":
      return <span className={MUTED_PILL}>Early exit</span>;
    case "very_short":
      return <span className={MUTED_PILL}>Not scored · under 30s</span>;
    case "not_connected":
      return <span className={MUTED_PILL}>Not scored · not connected</span>;
    case "failed":
      return <span className={`${PILL} bg-rose-50 text-rose-700 border-rose-200`}>Processing failed</span>;
    default:
      return null;
  }
}

function Quote({ time, text }: { time: string | null; text: string | null }) {
  if (!text) return null;
  return (
    <p className="font-body text-[11px] leading-relaxed text-[#44403c]">
      {time && <span className="font-label text-[10px] font-bold text-[#a8a29e] mr-1.5">[{time}]</span>}
      &ldquo;{text}&rdquo;
    </p>
  );
}

function CheckRow({ check }: { check: CallCheck }) {
  const [open, setOpen] = useState(false);
  const pending = check.level === null;
  return (
    <div className="rounded-lg">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={pending}
        aria-expanded={open}
        className="grid w-full grid-cols-[minmax(0,1fr)_auto_3.5rem] items-center gap-2 px-2 py-1.5 text-left rounded-lg hover:bg-[#faf8f5] disabled:hover:bg-transparent"
      >
        <span className="font-label text-[11px] font-semibold text-[#57534e] truncate">
          {CHECK_LABEL[check.key]}
          {check.proof_missing && <span className="ml-1.5 text-[9px] font-bold text-amber-700">· needs review</span>}
        </span>
        {pending ? (
          <span className={MUTED_PILL}>Waiting for wrap-up</span>
        ) : (
          <span className={`${PILL} ${LEVEL_TONE[check.level as CheckLevel]}`}>{LEVEL_LABEL[check.level as CheckLevel]}</span>
        )}
        <span className="font-label text-[11px] font-bold text-[#292524] text-right tabular-nums">
          {pending ? "—" : (check.marks ?? 0).toFixed(1)}<span className="text-[#a8a29e] font-semibold"> /{check.full}</span>
        </span>
      </button>
      {open && !pending && (
        <div className="ml-2 border-l-2 border-[#f0ece4] pl-3 pb-2 space-y-1">
          {check.reason && <p className="font-body text-[11px] text-[#57534e]">{check.reason}</p>}
          {check.capped_by && (
            <p className="font-label text-[10px] text-amber-700">
              AI said {check.ai_level ? LEVEL_LABEL[check.ai_level] : "—"}; {CAP_NOTE[check.capped_by]}.
            </p>
          )}
          <Quote time={check.time} text={check.quote} />
        </div>
      )}
    </div>
  );
}

function NumbersLine({ log }: { log: CallLog }) {
  const share = log.talk_share;
  const ipm = log.interruptions_per_5min;
  if (share == null && ipm == null) return null;
  return (
    <p className="font-body text-[11px] text-[#57534e]">
      {share != null && (
        <span className={share > 65 ? "text-amber-700 font-bold" : ""}>Talk share {Math.round(share)}%</span>
      )}
      {share != null && ipm != null && <span className="text-[#a8a29e]"> · </span>}
      {ipm != null && (
        <span className={ipm > 1 ? "text-amber-700 font-bold" : ""}>
          Interruptions {ipm.toFixed(1)} per 5 min{log.interruption_count != null ? ` (${log.interruption_count})` : ""}
        </span>
      )}
    </p>
  );
}

function RealConversationCard({ log }: { log: CallLog }) {
  const evaluation = log.evaluation;
  const checks = evaluation?.checks ?? [];
  if (log.score == null || !checks.length) return null;
  const byKey = Object.fromEntries(checks.map((c) => [c.key, c])) as Record<CheckKey, CallCheck>;
  const provisional = log.score_status === "provisional";
  return (
    <div className="rounded-xl border border-[#e8e3db] bg-white px-3 py-3 space-y-3">
      <div className="flex items-center gap-3">
        <div className={`flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-xl border ${scoreColor(log.score)}`}>
          <span className="font-display text-lg font-extrabold leading-none tabular-nums">{log.score.toFixed(1)}</span>
          <span className="font-label text-[8px] font-bold opacity-70">/ 100</span>
        </div>
        <div className="min-w-0 space-y-0.5">
          <p className="font-body text-xs font-bold text-[#292524]">
            Real conversation{provisional && <span className="ml-1.5 font-label text-[10px] font-bold text-amber-700">· provisional until the wrap-up is saved</span>}
          </p>
          <NumbersLine log={log} />
        </div>
      </div>

      {(evaluation?.tips?.length ?? 0) > 0 && (
        <div className="space-y-1">
          {evaluation!.tips!.map((tip) => (
            <p key={tip} className="flex items-start gap-1.5 font-body text-[11px] text-amber-800">
              <Lightbulb size={12} className="shrink-0 mt-0.5" /> {tip}
            </p>
          ))}
        </div>
      )}

      {(evaluation?.top_improve?.length ?? 0) > 0 && (
        <div className="rounded-lg bg-[#faf8f5] px-2.5 py-2">
          <p className="font-label text-[9px] uppercase tracking-wider font-extrabold text-[#a8a29e] mb-0.5">Top things to improve</p>
          <p className="font-body text-[11px] font-semibold text-[#292524]">
            {evaluation!.top_improve!.map((k) => `${CHECK_LABEL[k]} ${(byKey[k]?.marks ?? 0).toFixed(1)}/${byKey[k]?.full}`).join(" · ")}
          </p>
        </div>
      )}

      <div className="space-y-2">
        {STAGES.map((stage) => (
          <div key={stage.name}>
            <p className="font-label text-[9px] uppercase tracking-widest font-extrabold text-[#a8a29e] px-2 mb-0.5">{stage.name}</p>
            {stage.keys.map((k) => byKey[k] && <CheckRow key={k} check={byKey[k]} />)}
          </div>
        ))}
      </div>

      {(evaluation?.unverified_claims?.length ?? 0) > 0 && (
        <div className="border-t border-[#f0ece4] pt-2">
          <p className="font-label text-[9px] uppercase tracking-wider font-extrabold text-[#a8a29e] mb-1">Not in the knowledge base (not marked down)</p>
          {evaluation!.unverified_claims!.map((c) => (
            <p key={c} className="font-body text-[11px] text-[#57534e]">&ldquo;{c}&rdquo;</p>
          ))}
        </div>
      )}
    </div>
  );
}

function EarlyExitCard({ log }: { log: CallLog }) {
  const check = log.evaluation?.early_exit_check;
  if (!check) return null;
  const row = (ok: boolean | null, label: string, note?: string) => (
    <p className="flex items-start gap-1.5 font-body text-[11px] text-[#57534e]">
      {ok === null ? <Clock size={12} className="text-[#a8a29e] shrink-0 mt-0.5" /> : ok ? (
        <CheckCircle2 size={12} className="text-emerald-600 shrink-0 mt-0.5" />
      ) : (
        <AlertTriangle size={12} className="text-rose-600 shrink-0 mt-0.5" />
      )}
      <span>{label}{note && <span className="text-[#a8a29e]"> · {note}</span>}</span>
    </p>
  );
  return (
    <div className="rounded-xl border border-[#e8e3db] bg-white px-3 py-3 space-y-2">
      <div>
        <p className="font-body text-xs font-bold text-[#292524]">Early exit · not scored</p>
        <p className="font-label text-[10px] text-[#a8a29e]">No real sales discussion happened, so this call doesn&apos;t count in quality or effort.</p>
      </div>
      {row(check.polite, check.polite ? "Stayed polite" : "Not polite on this call")}
      {!check.polite && <Quote time={null} text={check.rude_quote} />}
      {row(check.enquiry_confirmed_early, check.enquiry_confirmed_early ? "Confirmed the enquiry early" : "Didn't confirm the enquiry in the first 30 seconds", "coaching only")}
      {row(
        check.crm_matches,
        check.crm_matches === null ? "Wrap-up check pending" : check.crm_matches ? "Wrap-up matches the call" : "Wrap-up doesn't match the call",
        check.expected_crm !== "other" ? `expected: ${EXPECTED_CRM_LABEL[check.expected_crm]}` : undefined,
      )}
    </div>
  );
}

/** Everything the AI produced for a recorded call, in the order people read it. */
export function CallAiDetail({ log, onChanged }: { log: CallLog; onChanged?: () => void }) {
  if (log.provider !== "telecmi") return null;
  const brief = log.ai_summary?.brief;
  const v4 = log.evaluation?.evaluation_version === 4;
  return (
    <div className="space-y-2.5">
      <ProcessingBanner log={log} onRetried={onChanged} />
      {log.score_status === "very_short" && (
        <p className="font-label text-[10px] text-[#a8a29e]">Not scored · under 30 seconds of talk time. Counted as a dial only.</p>
      )}
      {log.score_status === "not_connected" && (
        <p className="font-label text-[10px] text-[#a8a29e]">Not scored · the customer didn&apos;t answer. Counted as a dial only.</p>
      )}
      {v4 && log.call_group === "real_conversation" && <RealConversationCard log={log} />}
      {v4 && log.call_group === "early_exit" && <EarlyExitCard log={log} />}
      {brief && (
        <div className="rounded-xl border border-[#f0ece4] bg-white px-3 py-2.5">
          <p className="font-label text-[9px] uppercase tracking-widest font-extrabold text-primary mb-1 flex items-center gap-1">
            <Sparkles size={10} /> Summary
          </p>
          <p className="font-body text-[11px] leading-relaxed text-[#44403c]">{brief}</p>
        </div>
      )}
      <MaskedTranscript preview={log.transcript_preview} />
    </div>
  );
}
```

Update the icon import to `AlertTriangle, CheckCircle2, Clock, Lightbulb, Loader2, RefreshCw, Sparkles` and the type import to `api, type CallCheck, type CallLog, type CheckKey, type CheckLevel, type EarlyExitCheck, type TranscriptPreview`.

- [ ] **Step 3: Remove the criteria picker.** In `TelecallingConfigPanel.tsx`, delete the `import { SCORE_CRITERIA } ...`, the `score_criteria?: ScoreCriterion[]` draft field, `ALL_CRITERIA`, and the whole `{/* Call scoring criteria … */}` block (~lines 149-194). Remove `ScoreCriterion` from its type import, and delete `TickMark` if it becomes unused.

- [ ] **Step 4: Typecheck + lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: clean. Fix every error this surfaces, including in files that only consumed the removed types (`FlaggedCalls.tsx` is removed in Task 11; if typecheck fails there now, do Task 11 Step 1 first).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(ui): call card for 10-check scoring, early exit and not-scored labels" -- frontend/lib/api.ts frontend/components/CallAi.tsx frontend/app/dashboard/settings/TelecallingConfigPanel.tsx
```

---

### Task 11: Needs attention list + sidebar badge

**Files:**
- Create: `frontend/app/dashboard/telecalling/components/sections/NeedsAttention.tsx`
- Delete: `frontend/app/dashboard/telecalling/components/sections/FlaggedCalls.tsx`
- Modify: `frontend/app/dashboard/telecalling/components/performance-view.tsx:20,208`, `frontend/components/sidebar.tsx`

**Interfaces:**
- Consumes: `api.calls.alerts`, `api.calls.alertCount`, `api.calls.markAlertSeen`, `CallAlert`, `CallAlertType`.

- [ ] **Step 1: Write `NeedsAttention.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Eye, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, type CallAlert, type CallAlertType } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";

const TYPE_LABEL: Record<CallAlertType, string> = {
  rude: "Rude or dismissive",
  wrong_info: "Wrong product info",
  crm_mismatch: "Wrap-up mismatch",
  no_proof: "Mark without proof",
  transcript_failed: "Couldn't transcribe",
  language_barrier: "Language barrier",
  lead_source_quality: "Bad lead source",
  tracks_swapped: "Tracks may be swapped",
};
const SERIOUS: CallAlertType[] = ["rude", "wrong_info"];

interface NeedsAttentionProps {
  onViewLead: (leadId: string) => void;
}

/** Admin-only list of call-scoring warnings: one place instead of a notification per call. */
export default function NeedsAttention({ onViewLead }: NeedsAttentionProps) {
  const [type, setType] = useState<CallAlertType | "">("");
  const [rows, setRows] = useState<CallAlert[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async (nextType: CallAlertType | "", nextPage: number) => {
    setLoading(true);
    try {
      const res = await api.calls.alerts({ type: nextType || undefined, page: nextPage });
      setRows((prev) => (nextPage === 1 ? res.data : [...prev, ...res.data]));
      setTotal(res.total);
      setPage(nextPage);
    } catch (err) {
      console.error("Failed to load call alerts:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(type, 1);
  }, [type, load]);

  async function markSeen(alert: CallAlert) {
    setBusyId(alert.id);
    try {
      await api.calls.markAlertSeen(alert.id);
      setRows((prev) => prev.filter((r) => r.id !== alert.id));
      setTotal((n) => Math.max(0, n - 1));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not mark as seen");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div id="needs-attention" className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
        <div>
          <h2 className="font-display text-base font-bold text-primary flex items-center gap-2">
            <AlertTriangle size={15} className="text-amber-600" /> Needs attention
            {total > 0 && (
              <span className="inline-flex min-w-5 h-5 items-center justify-center rounded-full bg-rose-600 px-1.5 font-label text-[10px] font-extrabold text-white">
                {total}
              </span>
            )}
          </h2>
          <p className="font-label text-xs text-on-surface-muted mt-0.5">
            Warnings from call scoring. You get one summary each morning; only rudeness and wrong product info alert you straight away.
          </p>
        </div>
        <select
          value={type}
          onChange={(e) => setType(e.target.value as CallAlertType | "")}
          aria-label="Filter by type"
          className="rounded-lg border border-[#e8e3db] bg-white px-2.5 py-1.5 font-label text-xs text-[#292524]"
        >
          <option value="">All types</option>
          {(Object.keys(TYPE_LABEL) as CallAlertType[]).map((t) => (
            <option key={t} value={t}>{TYPE_LABEL[t]}</option>
          ))}
        </select>
      </div>

      {loading && rows.length === 0 ? (
        <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin text-[#a8a29e]" /></div>
      ) : rows.length === 0 ? (
        <p className="py-8 text-center font-body text-sm text-[#a8a29e]">Nothing needs attention.</p>
      ) : (
        <ul className="divide-y divide-[#f0ece4]">
          {rows.map((a) => {
            const lead = a.call_logs?.leads;
            const leadId = a.call_logs?.lead_id;
            return (
              <li key={a.id} className="flex items-start gap-3 py-3">
                <span className={`mt-0.5 shrink-0 inline-flex items-center rounded-full border px-2 py-0.5 font-label text-[9px] font-bold ${SERIOUS.includes(a.type) ? "bg-rose-50 text-rose-700 border-rose-200" : "bg-amber-50 text-amber-700 border-amber-200"}`}>
                  {TYPE_LABEL[a.type]}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-body text-xs font-bold text-[#292524] truncate">
                    {a.callers?.name ?? "—"}
                    {lead && <span className="font-semibold text-[#78716c]"> · {lead.name || formatPhone(lead.phone ?? "")}</span>}
                  </p>
                  {a.quote && <p className="font-body text-[11px] text-[#57534e] mt-0.5 break-words">{a.quote}</p>}
                  <p className="font-label text-[10px] text-[#a8a29e] mt-0.5">{timeAgo(a.created_at)}</p>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  {leadId && (
                    <button type="button" onClick={() => onViewLead(leadId)} className="inline-flex items-center gap-1 rounded-lg border border-[#e8e3db] bg-white px-2.5 py-1.5 font-label text-[10px] font-extrabold text-[#57534e] hover:bg-[#faf8f5]">
                      <Eye size={11} /> Open
                    </button>
                  )}
                  <button type="button" disabled={busyId === a.id} onClick={() => void markSeen(a)} className="inline-flex items-center gap-1 rounded-lg bg-primary px-2.5 py-1.5 font-label text-[10px] font-extrabold text-white disabled:opacity-60">
                    {busyId === a.id ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />} Seen
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {rows.length < total && (
        <button type="button" onClick={() => void load(type, page + 1)} disabled={loading} className="mt-3 w-full rounded-lg border border-[#e8e3db] py-2 font-label text-xs font-bold text-[#57534e] hover:bg-[#faf8f5] disabled:opacity-60">
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Swap it in.** Delete `FlaggedCalls.tsx`. In `performance-view.tsx`, replace the import with `import NeedsAttention from "./sections/NeedsAttention";` and line ~208 with:

```tsx
      {callingProvider === "telecmi" && canManageTeam && <NeedsAttention onViewLead={setViewingLeadId} />}
```

- [ ] **Step 3: Sidebar badge.** In `components/sidebar.tsx`, next to `inboxCount`, add `const [alertCount, setAlertCount] = useState(0);` and a poll (admins only; the route 403s for others, which is ignored):

```tsx
  useEffect(() => {
    if (!telecallingOn) return;
    let stopped = false;
    const poll = async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/calls/alerts/count`, { headers: auth });
        if (res.ok && !stopped) setAlertCount((await res.json()).count ?? 0);
      } catch {}
    };
    void poll();
    const id = setInterval(poll, 60_000);
    return () => { stopped = true; clearInterval(id); };
  }, [telecallingOn]);
```

Render the badge on the `/dashboard/telecalling` (Dialer) item in both the desktop and collapsed nav, using exactly the same markup the `inboxCount` badge uses at lines ~326 and ~602 (`{alertCount > 9 ? "9+" : alertCount}`), shown only when `alertCount > 0`. Find where the nav items are mapped, and pass `badge` when `item.href === "/dashboard/telecalling"`.

- [ ] **Step 4: Typecheck + lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/telecalling/components/sections/NeedsAttention.tsx
git rm -q frontend/app/dashboard/telecalling/components/sections/FlaggedCalls.tsx
git commit -m "feat(ui): admin Needs attention list with sidebar badge, replaces Flagged calls" -- frontend/app/dashboard/telecalling/components/sections/NeedsAttention.tsx frontend/app/dashboard/telecalling/components/sections/FlaggedCalls.tsx frontend/app/dashboard/telecalling/components/performance-view.tsx frontend/components/sidebar.tsx
```

---

### Task 12: `/10` → `/100` everywhere

**Files:** every screen that shows a call score or call-score average.

- [ ] **Step 1: Find them**

Run: `cd frontend && grep -rn "/10\b\|/ 10\b\|avg_score\|overall_score\|avg_score_month\|scoreColor(" app components lib --include=*.tsx --include=*.ts | grep -v "bg-\|from-\|to-\|/100"`

Known sites: `performance-view.tsx:354` (`/10`), `ProfileClient.tsx:~269` (`/ 10`), `WinnerBanner.tsx`, `analytics/CompareTab.tsx`, `operator/(console)/client/[id]/views/analytics.tsx`, `operator/(console)/client/[id]/views/team.tsx`, `QaReviewFeed.tsx`.

- [ ] **Step 2: Change each** visible `/10` or `/ 10` next to a *call* score to `/100` / `/ 100`. Any progress-bar width computed as `score * 10` becomes `score`. Any threshold on those values (`>= 8`, `>= 7`) becomes ×10. Lead scores (`leads.score`) are a different scale, so leave those untouched. Check each hit's data source before editing it.

- [ ] **Step 3: Typecheck + lint + build**

Run: `cd frontend && npm run typecheck && npm run lint && npm run build`
Expected: clean.

- [ ] **Step 4: Commit** (explicit pathspec listing every file edited in Step 2)

```bash
git commit -m "feat(ui): call scores shown out of 100" -- <each edited file>
```

---

### Task 13: Real-call verification, screenshots, docs

- [ ] **Step 1: Run the new pipeline on the real test call.** This overwrites the evaluation of test call `ed296fa2-b80b-465b-9a43-1ed023b64eaf`, which the user made for this purpose. Write `scratchpad/rerun_call.py`:

```python
import asyncio, sys
sys.path.insert(0, r"C:\Users\vskee\Desktop\Aira-Ai\backend")
from app.db.supabase import get_supabase
from app.services.call_ai_pipeline import run_call_ai

CALL = "ed296fa2-b80b-465b-9a43-1ed023b64eaf"
db = get_supabase()
db.table("call_logs").update({"ai_status": "pending", "ai_attempts": 0}).eq("id", CALL).execute()
asyncio.run(run_call_ai(CALL))
row = db.table("call_logs").select("call_group,score_status,score,talk_share,interruption_count,transcript,evaluation").eq("id", CALL).single().execute().data
print(row["call_group"], row["score_status"], row["score"], row["talk_share"], row["interruption_count"])
print(row["transcript"])
print(row["evaluation"].get("signs"), row["evaluation"].get("early_exit_check"))
```

Run it from `backend/` (so `.env` loads) **twice**.
Expected, both runs identical: `early_exit early_exit None` with 0–1 valid signs. The right channel carries the user (the telecaller), so the ≈5–18 s explanation ("நான் வந்துட்டு அந்த டெலிகாலிங் ஸ்கோரிங்…") must be labelled **Telecaller**, and the ≈30–37 s line ("ஸ்கோரிங் இப்பதான்…") **Customer**. If the labels come out the other way round, stop and report: `TELECALLER_CHANNEL` is wrong.

- [ ] **Step 2: Document examples through the real AI.** In the same script style, call `sort_call` and `mark_call` directly on the method document's Example 1 and Example 2 transcripts (as in `test_call_sorting.py`, with times) using the tenant's key (`tenant_id` of the test call). Expected: Example 1 → `early_exit`; Example 2 → `real_conversation` with ≥ 5 valid signs; `mark_call` returns levels for all 9 checks. Run each twice and confirm identical output.

- [ ] **Step 3: Render and screenshot.** Start backend and frontend (`uvicorn app.main:app --reload`, `npm run dev`), log in as the tenant owner, and open Telecalling → Recent calls → the test call. Screenshot with Playwright (`channel: 'chrome'`): the Early-exit card, a real-conversation card (use a fixture row, or the Example 2 evaluation written to a scratch copy), Needs attention, the sidebar badge, and the settings page without the criteria picker. Fix anything that looks broken before showing the user.

- [ ] **Step 4: Update the second brain.**
  - `.agents/context/subsystem-notes.md` → rewrite the "Call evaluation" section: v4 flow, per-track transcription (right = telecaller, verified 2026-09-25 on call `ed296fa2`), the AI swapped speakers on single-pass transcription, check 10 cut-off 2 h, `call_alerts` + morning summary, quotes exposed / transcript masked, `MAX_ATTEMPTS = 2`. Remove the stale `0.5×outcome + 0.5×AI` line.
  - `.agents/decisions/log.md` → a dated entry: Phase 1 decisions Q1–Q9 (one line each), migrations 205 (applied) / 206 (pending until deploy).
  - Run `graphify` (the `/wiki` skill, fast mode) so the wiki reflects the new modules.

- [ ] **Step 5: Commit**

```bash
git commit -m "docs: call scoring v4 notes and decision log" -- .agents/context/subsystem-notes.md .agents/decisions/log.md graphify-out
```

- [ ] **Step 6: Hand back.** Report to the user: test results, the re-scored test call, screenshots, and what's waiting on them. **Do not push.** Ask for the go-ahead to push/deploy. After the deploy, apply migration 207.

---

### Task 14 (after deploy only): Migration 207

**Files:** Create `backend/supabase/migrations/207_drop_call_flags.sql`

Note: migration 206 was already applied live during Task 8 (`206_call_score_status_v4.sql`, widening `call_logs_score_status_check` to old ∪ new values so the v4 code's writes wouldn't 500 pre-deploy) — this task's file moved from 206 to 207 as a result.

```sql
-- Old no-answer safety-gate flag and 7+3 breakdown: replaced by call_alerts and evaluation v4.
-- Fold the pre-v4 score_status values into the v4 set, then narrow the check
-- (206 widened it to old ∪ new only so pre-deploy writes wouldn't fail).
UPDATE call_logs SET score_status = 'very_short' WHERE score_status = 'short_call';
UPDATE call_logs SET score_status = 'not_connected' WHERE score_status = 'no_answer';
UPDATE call_logs SET score_status = 'processing' WHERE score_status IN ('pending', 'awaiting_outcome', 'no_recording');

ALTER TABLE call_logs
  DROP COLUMN IF EXISTS flag_status,
  DROP COLUMN IF EXISTS flag_reason,
  DROP COLUMN IF EXISTS flagged_at,
  DROP COLUMN IF EXISTS flag_resolved_by,
  DROP COLUMN IF EXISTS flag_resolved_at,
  DROP COLUMN IF EXISTS score_breakdown;

-- Old v3-scored rows carry a 0-10 scale score under the new v4 evaluation_version
-- gate; clear them back to processing so the next AI sweep re-scores them on v4.
UPDATE call_logs SET score = NULL, score_status = 'processing'
  WHERE provider = 'telecmi' AND score IS NOT NULL
    AND (evaluation->>'evaluation_version') IS DISTINCT FROM '4';

ALTER TABLE call_logs DROP CONSTRAINT IF EXISTS call_logs_score_status_check;
ALTER TABLE call_logs ADD CONSTRAINT call_logs_score_status_check
  CHECK (score_status IS NULL OR score_status = ANY (ARRAY['processing','not_connected','very_short','early_exit','provisional','scored','failed']));
```

- [ ] **Step 1:** Confirm the deployed backend no longer references these columns: `grep -rn "flag_status\|score_breakdown\|flagged_at\|flag_reason\|flag_resolved" backend/app frontend/app frontend/components frontend/lib` → no matches. Confirm Render's latest deploy is the merged commit (`deploy-check` skill).
- [ ] **Step 2:** Apply it via Supabase MCP `apply_migration` (name `207_drop_call_flags`) and verify the columns are gone from `information_schema.columns` and the check constraint only allows the new set.
- [ ] **Step 3:** Commit the file: `git commit -m "chore(db): drop old call flag columns, narrow score_status" -- backend/supabase/migrations/207_drop_call_flags.sql`
- [ ] **Step 4: Re-score the test call.** On the live server (via Supabase MCP `execute_sql`), re-queue test call `ed296fa2` for AI processing now that 207 has cleared its stale v3 score:
  ```sql
  UPDATE call_logs SET ai_status = 'pending', ai_attempts = 0, ai_updated_at = now() - interval '5 minutes'
    WHERE id = 'ed296fa2-b80b-465b-9a43-1ed023b64eaf';
  ```
  Wait for the 3-minute call-ai sweep to pick it up, then check `call_group`, `score_status` and `evaluation` on the row. Expected: `call_group = 'early_exit'` (this call was confirmed early-exit in Task 13's manual review) and the right-channel speaker in the evaluation is the telecaller (also confirmed in Task 13).
