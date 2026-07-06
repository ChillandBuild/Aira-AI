import { describe, expect, it } from "vitest";
import type { Lead } from "@/lib/api";
import { getLeadQueueSection, sortLeadsForCallQueue } from "./queue-priority";

function lead(overrides: Partial<Lead>): Lead {
  return {
    id: overrides.id || "lead",
    phone: overrides.phone ?? "+919999999999",
    name: overrides.name ?? "Lead",
    source: overrides.source ?? "upload",
    score: overrides.score ?? 5,
    segment: overrides.segment ?? "C",
    ai_enabled: true,
    opted_out: false,
    created_at: overrides.created_at ?? "2026-07-05T08:00:00Z",
    ...overrides,
  };
}

describe("telecalling queue priority", () => {
  it("classifies channel leads and replied upload leads as message priority", () => {
    expect(getLeadQueueSection(lead({ source: "whatsapp" }))).toBe("messages");
    expect(getLeadQueueSection(lead({ source: "upload", last_inbound_at: "2026-07-05T09:00:00Z" }))).toBe("messages");
    expect(getLeadQueueSection(lead({ source: "upload" }))).toBe("upload");
  });

  it("keeps message leads above telecalling upload leads in the same caller queue", () => {
    const sorted = sortLeadsForCallQueue([
      lead({ id: "upload-hot", source: "upload", segment: "A", score: 10 }),
      lead({ id: "message-warm", source: "instagram", segment: "B", score: 6 }),
      lead({ id: "upload-cold", source: "upload", segment: "C", score: 5 }),
      lead({ id: "reply-hot", source: "upload", segment: "A", score: 9, last_inbound_at: "2026-07-05T10:00:00Z" }),
    ]);

    expect(sorted.map((item) => item.id)).toEqual(["reply-hot", "message-warm", "upload-hot", "upload-cold"]);
  });
});
