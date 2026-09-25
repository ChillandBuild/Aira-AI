export type SegmentCode = "A" | "B" | "C" | "D";

export interface ScoreEventLike {
  event_type: "segment_changed" | "score_updated";
  from_segment: string | null;
  to_segment: string | null;
  metadata: {
    classification_reason?: string | null;
    intent_reason?: string | null;
    message_snippet?: string;
    channel?: string;
    // Older events still carry numbers; they are never surfaced.
    [key: string]: unknown;
  };
}

export interface ScoreEventView {
  changed: boolean;
  from: SegmentCode | null;
  to: SegmentCode | null;
  reason: string | null;
  snippet: string | null;
  channel: string | null;
}

// Values the scoring engine stores when the AI gave no sentence (a fallback or a bare
// label). They are codes, not something a person should read.
const PLACEHOLDER_REASONS = new Set([
  "classified_hot",
  "classified_warm",
  "classified_cold",
  "classified",
  "error_fallback",
  "parse_error_fallback",
]);

const REJECTION_TEXT = "Said they are not interested";

function asSegment(value: string | null): SegmentCode | null {
  return value === "A" || value === "B" || value === "C" || value === "D" ? value : null;
}

function readableReason(metadata: ScoreEventLike["metadata"]): string | null {
  const reason = (metadata.classification_reason ?? "").trim();
  if (reason && !PLACEHOLDER_REASONS.has(reason)) return reason;
  if (metadata.intent_reason === "rejection") return REJECTION_TEXT;
  return null;
}

/** What one Score History row should say. Groups and words only, never a number. */
export function describeScoreEvent(ev: ScoreEventLike): ScoreEventView {
  const from = asSegment(ev.from_segment);
  const to = asSegment(ev.to_segment);
  return {
    changed: ev.event_type === "segment_changed" || (to !== null && from !== to),
    from,
    to,
    reason: readableReason(ev.metadata),
    snippet: ev.metadata.message_snippet?.trim() || null,
    channel: ev.metadata.channel ?? null,
  };
}
