import { describe, expect, it } from "vitest";
import { describeScoreEvent, type ScoreEventLike } from "./scoreHistory";

const base: ScoreEventLike = {
  event_type: "score_updated",
  from_segment: "A",
  to_segment: "A",
  metadata: {},
};

describe("describeScoreEvent", () => {
  it("reports a group change with the AI's reason", () => {
    const d = describeScoreEvent({
      ...base,
      event_type: "segment_changed",
      from_segment: "B",
      to_segment: "A",
      metadata: { classification_reason: "Asked for the payment link" },
    });
    expect(d.changed).toBe(true);
    expect(d.from).toBe("B");
    expect(d.to).toBe("A");
    expect(d.reason).toBe("Asked for the payment link");
  });

  it("reports 'stayed' when the group did not change", () => {
    const d = describeScoreEvent({ ...base, metadata: { classification_reason: "Still asking about price" } });
    expect(d.changed).toBe(false);
    expect(d.to).toBe("A");
  });

  it("ignores machine placeholders, they are not sentences for a person", () => {
    for (const code of ["classified_hot", "classified_warm", "classified_cold", "error_fallback", "parse_error_fallback"]) {
      expect(describeScoreEvent({ ...base, metadata: { classification_reason: code } }).reason).toBeNull();
    }
  });

  it("explains a rejection from the older intent_reason field", () => {
    const d = describeScoreEvent({
      ...base,
      event_type: "segment_changed",
      from_segment: "B",
      to_segment: "D",
      metadata: { intent_reason: "rejection" },
    });
    expect(d.reason).toBe("Said they are not interested");
  });

  it("older events without a reason still describe the change, and never expose numbers", () => {
    const d = describeScoreEvent({
      ...base,
      event_type: "segment_changed",
      from_segment: "C",
      to_segment: "B",
      metadata: { prev_score: 4, new_score: 6, arc_score: 6, intent_delta: 1 },
    });
    expect(d.reason).toBeNull();
    expect(JSON.stringify(d)).not.toMatch(/prev_score|new_score|arc/);
  });

  it("returns the lead's message snippet and channel", () => {
    const d = describeScoreEvent({ ...base, metadata: { message_snippet: "price?", channel: "whatsapp" } });
    expect(d.snippet).toBe("price?");
    expect(d.channel).toBe("whatsapp");
  });

  it("treats a missing from-segment as a change into the new group", () => {
    const d = describeScoreEvent({ ...base, event_type: "segment_changed", from_segment: null, to_segment: "C" });
    expect(d.changed).toBe(true);
    expect(d.from).toBeNull();
  });
});
