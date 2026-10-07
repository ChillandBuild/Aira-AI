import { describe, expect, it } from "vitest";
import {
  INITIAL_SANDBOX_STATE,
  MAX_MESSAGE_CHARS,
  MAX_TURNS,
  canSend,
  isWindowed,
  messageForStatus,
  parseSandboxReply,
  resetState,
  toRequestMessages,
  withReply,
  withUserTurn,
  withoutFailedTurn,
  type SandboxTurn,
} from "./testAiraLogic";

const REPLY = { reply: "We open at 9.", knowledgeUsed: true };

function turns(count: number): SandboxTurn[] {
  return Array.from({ length: count }, (_, i) => ({ role: i % 2 === 0 ? "user" : "assistant", content: `m${i}` }));
}

describe("messageForStatus", () => {
  it("has plain words for the statuses the server uses", () => {
    expect(messageForStatus(429)).toMatch(/wait a few minutes/);
    expect(messageForStatus(503)).toBe("Test Anril is switched off right now.");
    expect(messageForStatus(409)).toMatch(/reply model isn't set up/);
  });

  it("falls back for unknown statuses and a dropped connection", () => {
    expect(messageForStatus(502)).toMatch(/couldn't answer/);
    expect(messageForStatus(null)).toMatch(/reach the server/);
  });
});

describe("canSend", () => {
  it("needs permission, an idle box and real text", () => {
    expect(canSend("hi", false, true)).toBe(true);
    expect(canSend("hi", false, false)).toBe(false);
    expect(canSend("hi", true, true)).toBe(false);
    expect(canSend("   ", false, true)).toBe(false);
  });

  it("blocks a message over the limit", () => {
    expect(canSend("x".repeat(MAX_MESSAGE_CHARS), false, true)).toBe(true);
    expect(canSend("x".repeat(MAX_MESSAGE_CHARS + 1), false, true)).toBe(false);
  });
});

describe("toRequestMessages", () => {
  it("sends role and text only", () => {
    const sent = toRequestMessages([{ role: "assistant", content: "hi", knowledgeUsed: true }]);
    expect(sent).toEqual([{ role: "assistant", content: "hi" }]);
  });

  it("keeps only the newest turns when the chat is long, and the last is still the newest", () => {
    const all = turns(MAX_TURNS + 3);
    const sent = toRequestMessages(all);
    expect(sent).toHaveLength(MAX_TURNS);
    expect(sent[sent.length - 1].content).toBe(all[all.length - 1].content);
    expect(isWindowed(all)).toBe(true);
    expect(isWindowed(turns(MAX_TURNS))).toBe(false);
  });
});

describe("parseSandboxReply", () => {
  it("reads reply and knowledge_used", () => {
    expect(parseSandboxReply({ reply: "Hello", knowledge_used: true, model: "m", note: "n" })).toEqual({
      reply: "Hello",
      knowledgeUsed: true,
    });
    expect(parseSandboxReply({ reply: "Hello" })?.knowledgeUsed).toBe(false);
  });

  it("rejects anything without a reply", () => {
    expect(parseSandboxReply(null)).toBeNull();
    expect(parseSandboxReply({})).toBeNull();
    expect(parseSandboxReply({ reply: "  " })).toBeNull();
  });
});

describe("conversation state", () => {
  it("adds the user turn, then the reply for that same request", () => {
    const sent = withUserTurn(INITIAL_SANDBOX_STATE, "hours?");
    const answered = withReply(sent, sent.requestId, REPLY);
    expect(answered.turns.map((t) => t.role)).toEqual(["user", "assistant"]);
  });

  it("drops a reply that arrives after Reset", () => {
    const sent = withUserTurn(INITIAL_SANDBOX_STATE, "hours?");
    const cleared = resetState(sent);
    expect(withReply(cleared, sent.requestId, REPLY).turns).toEqual([]);
  });

  it("drops a reply that arrives after a newer send", () => {
    const first = withUserTurn(INITIAL_SANDBOX_STATE, "one");
    const second = withUserTurn(first, "two");
    expect(withReply(second, first.requestId, REPLY)).toBe(second);
  });

  it("takes a failed turn back off, but not if the chat was reset meanwhile", () => {
    const sent = withUserTurn(INITIAL_SANDBOX_STATE, "hours?");
    expect(withoutFailedTurn(sent, sent.requestId).turns).toEqual([]);
    const cleared = resetState(sent);
    expect(withoutFailedTurn(cleared, sent.requestId)).toBe(cleared);
  });

  it("does not mutate the previous state", () => {
    const before = withUserTurn(INITIAL_SANDBOX_STATE, "hours?");
    withReply(before, before.requestId, REPLY);
    expect(before.turns).toHaveLength(1);
  });
});
