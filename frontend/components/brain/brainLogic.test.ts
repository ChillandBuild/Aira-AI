import { describe, expect, it } from "vitest";
import {
  ANCHOR_CONFLICTS,
  ANCHOR_FAILED,
  INITIAL_COUNT_STATE,
  badgeCount,
  canAutoCheckPanel,
  handoverAction,
  headlineSentence,
  initialLatestState,
  nextCountState,
  parseBrainCount,
  pickMainAction,
  reduceLatest,
  topLineText,
  type CountState,
} from "./brainLogic";
import type { BrainHeadline, BrainWaiting } from "./types";

const COUNT_BODY = { count: 3, sort_count: 1, consistency_count: 2 };

function withValue(seq: number): CountState {
  return { appliedSeq: seq, value: { count: 3, sort_count: 1, consistency_count: 2 } };
}

describe("parseBrainCount", () => {
  it("accepts a well-formed body", () => {
    expect(parseBrainCount(COUNT_BODY)).toEqual(COUNT_BODY);
  });

  it("defaults missing breakdown fields to 0", () => {
    expect(parseBrainCount({ count: 4 })).toEqual({ count: 4, sort_count: 0, consistency_count: 0 });
  });

  it.each([null, undefined, "3", 3, {}, { count: "3" }, { count: -1 }, { count: NaN }])(
    "rejects %j",
    (raw) => {
      expect(parseBrainCount(raw)).toBeNull();
    },
  );
});

describe("nextCountState (poll-result rule)", () => {
  it("shows nothing before the first success", () => {
    expect(badgeCount(INITIAL_COUNT_STATE)).toBeNull();
  });

  it("takes the value on success", () => {
    const next = nextCountState(INITIAL_COUNT_STATE, { seq: 1, ok: true, data: COUNT_BODY });
    expect(next.value).toEqual(COUNT_BODY);
    expect(badgeCount(next)).toBe(3);
  });

  it("keeps the last value when a poll fails (network error or 500)", () => {
    const prev = withValue(1);
    expect(nextCountState(prev, { seq: 2, ok: false })).toBe(prev);
    expect(nextCountState(prev, { seq: 2, ok: false, status: 500 })).toBe(prev);
  });

  it("keeps the last value when the success body is malformed", () => {
    const prev = withValue(1);
    expect(nextCountState(prev, { seq: 2, ok: true, data: { nope: 1 } })).toBe(prev);
  });

  it.each([403, 404])("clears the badge on a %i", (status) => {
    const next = nextCountState(withValue(1), { seq: 2, ok: false, status });
    expect(next.value).toBeNull();
    expect(badgeCount(next)).toBeNull();
  });

  it("stays empty on a 404 before any success (frontend deployed before backend)", () => {
    const next = nextCountState(INITIAL_COUNT_STATE, { seq: 1, ok: false, status: 404 });
    expect(badgeCount(next)).toBeNull();
  });

  it("ignores a result from an older request", () => {
    const prev = withValue(5);
    expect(nextCountState(prev, { seq: 4, ok: false, status: 404 })).toBe(prev);
    expect(nextCountState(prev, { seq: 4, ok: true, data: { count: 9 } })).toBe(prev);
  });

  it("recovers after a clear when a later poll succeeds", () => {
    const cleared = nextCountState(withValue(1), { seq: 2, ok: false, status: 404 });
    const back = nextCountState(cleared, { seq: 3, ok: true, data: COUNT_BODY });
    expect(badgeCount(back)).toBe(3);
  });

  it("draws no badge for a count of 0", () => {
    const next = nextCountState(INITIAL_COUNT_STATE, { seq: 1, ok: true, data: { count: 0 } });
    expect(next.value?.count).toBe(0);
    expect(badgeCount(next)).toBeNull();
  });

  it("does not mutate the previous state", () => {
    const prev = withValue(1);
    const snapshot = JSON.stringify(prev);
    nextCountState(prev, { seq: 2, ok: false, status: 403 });
    expect(JSON.stringify(prev)).toBe(snapshot);
  });
});

describe("reduceLatest (latest response wins)", () => {
  it("applies the first success", () => {
    const next = reduceLatest(initialLatestState<string>(), { type: "success", seq: 1, data: "a" });
    expect(next).toEqual({ appliedSeq: 1, data: "a", error: null });
  });

  it("lets the later request win when it answers first", () => {
    let state = initialLatestState<string>();
    state = reduceLatest(state, { type: "success", seq: 2, data: "later" });
    state = reduceLatest(state, { type: "success", seq: 1, data: "earlier" });
    expect(state.data).toBe("later");
  });

  it("applies responses that arrive in order", () => {
    let state = initialLatestState<string>();
    state = reduceLatest(state, { type: "success", seq: 1, data: "first" });
    state = reduceLatest(state, { type: "success", seq: 2, data: "second" });
    expect(state.data).toBe("second");
  });

  it("keeps good data when a later refresh fails", () => {
    let state = reduceLatest(initialLatestState<string>(), { type: "success", seq: 1, data: "ok" });
    state = reduceLatest(state, { type: "failure", seq: 2, message: "boom" });
    expect(state.data).toBe("ok");
    expect(state.error).toBeNull();
  });

  it("surfaces an error only when there is no data", () => {
    const state = reduceLatest(initialLatestState<string>(), { type: "failure", seq: 1, message: "boom" });
    expect(state).toEqual({ appliedSeq: 0, data: null, error: "boom" });
  });

  it("clears the error when a later success arrives", () => {
    let state = reduceLatest(initialLatestState<string>(), { type: "failure", seq: 1, message: "boom" });
    state = reduceLatest(state, { type: "success", seq: 2, data: "ok" });
    expect(state).toEqual({ appliedSeq: 2, data: "ok", error: null });
  });

  it("still applies an older success after a newer failure (it beats nothing)", () => {
    let state = reduceLatest(initialLatestState<string>(), { type: "failure", seq: 2, message: "boom" });
    state = reduceLatest(state, { type: "success", seq: 1, data: "ok" });
    expect(state.data).toBe("ok");
    expect(state.error).toBeNull();
  });

  it("ignores a failure from a request older than the applied one", () => {
    const applied = reduceLatest(initialLatestState<string>(), { type: "success", seq: 3, data: "ok" });
    expect(reduceLatest(applied, { type: "failure", seq: 2, message: "old" })).toBe(applied);
  });

  it("decides the empty state from the later response", () => {
    type Snapshot = { waiting: number };
    let state = initialLatestState<Snapshot>();
    state = reduceLatest(state, { type: "success", seq: 1, data: { waiting: 0 } });
    state = reduceLatest(state, { type: "success", seq: 2, data: { waiting: 1 } });
    expect(state.data?.waiting).toBe(1);
  });
});

describe("canAutoCheckPanel (managers only)", () => {
  it("allows the owner", () => {
    expect(canAutoCheckPanel("owner", [])).toBe(true);
  });

  it("allows a custom role with knowledge.manage", () => {
    expect(canAutoCheckPanel("caller", ["knowledge.view", "knowledge.manage"])).toBe(true);
  });

  it("refuses knowledge.view only", () => {
    expect(canAutoCheckPanel("caller", ["knowledge.view"])).toBe(false);
  });

  it("refuses while the role is still loading", () => {
    expect(canAutoCheckPanel(null, [])).toBe(false);
  });
});

const BASE_HEADLINE: BrainHeadline = {
  chats: 84,
  handled_by_aira: 71,
  handed_over: 6,
  unanswered: 7,
  window_days: 7,
  asked_for_human: 5,
  knowledge_gaps: 1,
};

describe("headlineSentence", () => {
  it("matches the blueprint example", () => {
    expect(headlineSentence(BASE_HEADLINE)).toBe(
      "This week: Aira handled 71 of 84 chats. 6 reached a human: 5 asked for a person, 1 was a gap in what Aira knows.",
    );
  });

  it("pluralises gaps", () => {
    const text = headlineSentence({ ...BASE_HEADLINE, handed_over: 5, asked_for_human: 3, knowledge_gaps: 2 });
    expect(text).toContain("3 asked for a person, 2 were gaps in what Aira knows.");
  });

  it("accounts for payment and other handovers", () => {
    const text = headlineSentence({ ...BASE_HEADLINE, handed_over: 8, asked_for_human: 5, knowledge_gaps: 1 });
    expect(text).toContain("2 for other reasons");
  });

  it("handles no chats", () => {
    expect(headlineSentence({ ...BASE_HEADLINE, chats: 0, handled_by_aira: 0, handed_over: 0 })).toBe(
      "This week: no chats yet.",
    );
  });

  it("handles no handovers", () => {
    const text = headlineSentence({ ...BASE_HEADLINE, handed_over: 0, asked_for_human: 0, knowledge_gaps: 0 });
    expect(text).toBe("This week: Aira handled 71 of 84 chats. Nobody needed a human.");
  });

  it("names a non-weekly window", () => {
    expect(headlineSentence({ ...BASE_HEADLINE, window_days: 1 }).startsWith("In the last 1 day:")).toBe(true);
  });
});

describe("topLineText", () => {
  it("says ready when nothing waits", () => {
    expect(topLineText(0)).toBe("Aira is ready");
  });

  it("counts things", () => {
    expect(topLineText(1)).toBe("1 thing needs you");
    expect(topLineText(4)).toBe("4 things need you");
  });
});

const EMPTY_WAITING: BrainWaiting = {
  count: 0,
  sort_reviews: [],
  consistency_count: 0,
  failed_files: [],
  rejected_templates: [],
};

describe("pickMainAction", () => {
  it("prefers a sorted-file review", () => {
    const action = pickMainAction({
      ...EMPTY_WAITING,
      count: 3,
      sort_reviews: [{ id: "r1", document_id: "d1", title: "Diwali.pdf", created_at: "2026-09-30T00:00:00Z" }],
      consistency_count: 2,
    });
    expect(action).toEqual({ kind: "review", label: "Review 1 sorted file", reviewId: "r1" });
  });

  it("falls back to conflicts, then failed files, then templates", () => {
    expect(pickMainAction({ ...EMPTY_WAITING, count: 2, consistency_count: 2 })).toMatchObject({
      kind: "anchor",
      anchor: ANCHOR_CONFLICTS,
    });
    expect(pickMainAction({ ...EMPTY_WAITING, count: 1, failed_files: [{ id: "f", name: "a.pdf" }] })).toMatchObject({
      kind: "anchor",
      anchor: ANCHOR_FAILED,
    });
    expect(pickMainAction({ ...EMPTY_WAITING, count: 1, rejected_templates: [{ id: "t" }] })).toMatchObject({
      kind: "link",
      href: "/dashboard/templates",
    });
  });

  it("offers to add knowledge when nothing waits", () => {
    expect(pickMainAction(EMPTY_WAITING)).toMatchObject({ kind: "link", href: "/dashboard/knowledge" });
  });
});

describe("handoverAction", () => {
  const base = {
    handover_id: "h1",
    lead_id: "lead-1" as string | null,
    reason: "asked for a person",
    kind: "asked_for_human" as const,
    likely_question: null,
    opened_at: "2026-09-30T00:00:00Z",
  };

  it("links to the chat when lead_id is present", () => {
    expect(handoverAction(base, false)).toEqual({ kind: "open_chat", leadId: "lead-1" });
  });

  it("shows the inbox-access note instead of a link when lead_id is null", () => {
    expect(handoverAction({ ...base, lead_id: null }, false)).toEqual({ kind: "no_inbox_access" });
  });

  it("still offers Add an answer for knowledge gaps, even without a lead_id", () => {
    expect(handoverAction({ ...base, kind: "knowledge_gap", lead_id: null }, false)).toEqual({ kind: "add_answer" });
  });

  it("offers nothing in read-only mode", () => {
    expect(handoverAction(base, true)).toEqual({ kind: "none" });
    expect(handoverAction({ ...base, lead_id: null }, true)).toEqual({ kind: "none" });
  });
});
