import { describe, expect, it } from "vitest";
import {
  blockingGates,
  isWhatAiraSaw,
  noticeGates,
  paiseToRupees,
  verdictLine,
  type SawGate,
} from "./whatAiraSaw";

const gate = (over: Partial<SawGate>): SawGate => ({
  key: "blocked",
  label: "Lead is blocked",
  active: false,
  blocks_reply: true,
  detail: "",
  ...over,
});

const valid = {
  reconstructed: true,
  generated_at: "2026-09-30T10:00:00Z",
  lead: { id: "l1", name: "Priya", segment: "B", score: 6, channel: "whatsapp" },
  message_used: { text: "hi", note: null },
  recent_messages: [],
  conversation_summary: null,
  campaign: null,
  deal_state: { selling_enabled: false, session: null },
  orders: [],
  call_summaries: [],
  gates: [],
  would_reply: true,
  knowledge: { text: null, note: "Not retrieved." },
  system_prompt: "MASTER",
  reply_language_mode: "english",
  intake_active: false,
  prompt_error: null,
};

describe("isWhatAiraSaw", () => {
  it("accepts a reconstruction and rejects anything else", () => {
    expect(isWhatAiraSaw(valid)).toBe(true);
    expect(isWhatAiraSaw({ ...valid, reconstructed: false })).toBe(false);
    expect(isWhatAiraSaw({ ...valid, gates: null })).toBe(false);
    expect(isWhatAiraSaw(null)).toBe(false);
    expect(isWhatAiraSaw("x")).toBe(false);
  });
});

describe("gates", () => {
  const gates = [
    gate({ key: "blocked", active: true }),
    gate({ key: "takeover", active: false }),
    gate({ key: "opted_out", label: "Lead opted out", active: true, blocks_reply: false }),
  ];
  it("splits blocking gates from notices", () => {
    expect(blockingGates(gates).map((g) => g.key)).toEqual(["blocked"]);
    expect(noticeGates(gates).map((g) => g.key)).toEqual(["opted_out"]);
  });
  it("words the verdict from the blocking gates only", () => {
    expect(verdictLine({ would_reply: false, gates })).toBe("Anril would not reply: lead is blocked.");
    expect(verdictLine({ would_reply: true, gates: [] })).toBe("Anril would reply to a new message.");
    expect(verdictLine({ would_reply: false, gates: [] })).toBe("Anril would not reply.");
  });
});

describe("paiseToRupees", () => {
  it("formats and tolerates null", () => {
    expect(paiseToRupees(150000)).toBe("₹1,500");
    expect(paiseToRupees(null)).toBe("—");
  });
});
