import { describe, expect, it } from "vitest";
import {
  daysWaited,
  fleetWaitingByTenant,
  isOperatorBrainResponse,
  isStuckApproval,
  waitedLabel,
  waitingColumnText,
} from "./operatorBrain";

const NOW = Date.parse("2026-09-30T12:00:00Z");

describe("daysWaited", () => {
  it("counts whole days", () => {
    expect(daysWaited("2026-09-20T12:00:00Z", NOW)).toBe(10);
    expect(daysWaited("2026-09-29T13:00:00Z", NOW)).toBe(0);
  });
  it("never goes negative and tolerates junk", () => {
    expect(daysWaited("2026-10-05T00:00:00Z", NOW)).toBe(0);
    expect(daysWaited("not a date", NOW)).toBe(0);
  });
});

describe("isStuckApproval", () => {
  it("is false at exactly seven days and true just past it", () => {
    expect(isStuckApproval("2026-09-23T12:00:00Z", NOW)).toBe(false);
    expect(isStuckApproval("2026-09-23T11:59:00Z", NOW)).toBe(true);
    expect(isStuckApproval("junk", NOW)).toBe(false);
  });
});

describe("labels", () => {
  it("phrases days", () => {
    expect(waitedLabel(0)).toBe("today");
    expect(waitedLabel(1)).toBe("1 day");
    expect(waitedLabel(9)).toBe("9 days");
  });
  it("phrases the clients-list column", () => {
    const rows = [
      { tenant_id: "a", waiting_count: 3, pending_reviews: 2, oldest_review_days: 9, oldest_review_at: "x" },
      { tenant_id: "b", waiting_count: 1, pending_reviews: 0, oldest_review_days: null, oldest_review_at: null },
    ];
    const map = fleetWaitingByTenant(rows);
    expect(waitingColumnText(map.get("a"))).toBe("3 (oldest 9 days)");
    expect(waitingColumnText(map.get("b"))).toBe("1");
    expect(waitingColumnText(map.get("missing"))).toBe("None");
  });
});

describe("isOperatorBrainResponse", () => {
  it("rejects a client-shaped body without the operator blocks", () => {
    const shared = { headline: {}, waiting: {}, inputs: [], handovers: [], status: {} };
    expect(isOperatorBrainResponse(shared)).toBe(false);
    expect(isOperatorBrainResponse({ ...shared, operator_rows: [], history: {}, fallback_signals: {} })).toBe(true);
    expect(isOperatorBrainResponse(null)).toBe(false);
  });
});
