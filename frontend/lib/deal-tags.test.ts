import { describe, expect, it } from "vitest";
import { getDealTags, idleDays, isLinkExpired, type DealTagInput } from "./deal-tags";

const NOW = new Date("2026-10-10T12:00:00.000Z");
const DAY_MS = 24 * 60 * 60 * 1000;
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString();
const ahead = (ms: number) => new Date(NOW.getTime() + ms).toISOString();

function deal(overrides: Partial<DealTagInput> = {}): DealTagInput {
  return { stage: "awaiting_payment", payment_link: "https://rzp.io/i/abc", ...overrides };
}

describe("idleDays", () => {
  it("counts whole days since last activity", () => {
    expect(idleDays(ago(3 * DAY_MS + 5 * 60 * 1000), NOW)).toBe(3);
  });

  it("floors a partial day", () => {
    expect(idleDays(ago(2 * DAY_MS - 1), NOW)).toBe(1);
  });

  it("is exactly 2 at 48 hours", () => {
    expect(idleDays(ago(2 * DAY_MS), NOW)).toBe(2);
  });

  it("returns null for missing or unparseable timestamps", () => {
    expect(idleDays(undefined, NOW)).toBeNull();
    expect(idleDays(null, NOW)).toBeNull();
    expect(idleDays("not a date", NOW)).toBeNull();
  });

  it("clamps a future timestamp (clock skew) to 0", () => {
    expect(idleDays(ahead(DAY_MS), NOW)).toBe(0);
  });
});

describe("isLinkExpired", () => {
  it("is true when the expiry is in the past", () => {
    expect(isLinkExpired(deal({ link_expires_at: ago(1000) }), NOW)).toBe(true);
  });

  it("is false when the expiry is in the future", () => {
    expect(isLinkExpired(deal({ link_expires_at: ahead(1000) }), NOW)).toBe(false);
  });

  it("is false at the exact expiry instant (only strictly past counts)", () => {
    expect(isLinkExpired(deal({ link_expires_at: NOW.toISOString() }), NOW)).toBe(false);
  });

  it("is true when the link is missing (null or empty)", () => {
    expect(isLinkExpired(deal({ payment_link: null }), NOW)).toBe(true);
    expect(isLinkExpired(deal({ payment_link: "" }), NOW)).toBe(true);
  });

  it("is true for a missing link even if the stored expiry is still in the future", () => {
    expect(isLinkExpired(deal({ payment_link: null, link_expires_at: ahead(DAY_MS) }), NOW)).toBe(true);
  });

  it("is false when the API did not send link fields at all", () => {
    expect(isLinkExpired({ stage: "awaiting_payment" }, NOW)).toBe(false);
  });

  it("is false when a live link has no expiry recorded", () => {
    expect(isLinkExpired(deal({ link_expires_at: null }), NOW)).toBe(false);
  });

  it("is false for an unparseable expiry", () => {
    expect(isLinkExpired(deal({ link_expires_at: "garbage" }), NOW)).toBe(false);
  });

  it("only applies to awaiting_payment deals", () => {
    for (const stage of ["quoted", "won", "lost"] as const) {
      expect(isLinkExpired(deal({ stage, payment_link: null, link_expires_at: ago(DAY_MS) }), NOW)).toBe(false);
    }
  });
});

describe("getDealTags", () => {
  it("returns no tags for a fresh deal with a live link", () => {
    const tags = getDealTags(
      deal({ last_activity_at: ago(60 * 1000), link_expires_at: ahead(DAY_MS), refund_needed: false }),
      NOW,
    );
    expect(tags).toEqual([]);
  });

  it("returns no tags when the API sends none of the optional fields", () => {
    expect(getDealTags({ stage: "quoted" }, NOW)).toEqual([]);
  });

  it("hides the idle tag at 1 day and shows it at 2", () => {
    expect(getDealTags(deal({ last_activity_at: ago(DAY_MS + 3600 * 1000) }), NOW)).toEqual([]);
    expect(getDealTags(deal({ last_activity_at: ago(2 * DAY_MS) }), NOW)).toEqual([
      { key: "idle", label: "Idle 2 days", tone: "muted" },
    ]);
  });

  it("labels a long idle period with its whole-day count", () => {
    const tags = getDealTags(deal({ last_activity_at: ago(31 * DAY_MS + 1000) }), NOW);
    expect(tags[0].label).toBe("Idle 31 days");
  });

  it("does not tag idle on deals that are already won or lost", () => {
    for (const stage of ["won", "lost"] as const) {
      expect(getDealTags(deal({ stage, last_activity_at: ago(40 * DAY_MS) }), NOW)).toEqual([]);
    }
  });

  it("tags idle on quoted deals", () => {
    const tags = getDealTags({ stage: "quoted", last_activity_at: ago(5 * DAY_MS) }, NOW);
    expect(tags).toEqual([{ key: "idle", label: "Idle 5 days", tone: "muted" }]);
  });

  it("shows Link expired with warning tone", () => {
    expect(getDealTags(deal({ link_expires_at: ago(1000) }), NOW)).toEqual([
      { key: "link_expired", label: "Link expired", tone: "warning" },
    ]);
  });

  it("shows Refund needed with danger tone, on any stage", () => {
    for (const stage of ["quoted", "awaiting_payment", "won", "lost"] as const) {
      expect(getDealTags({ stage, payment_link: "x", refund_needed: true }, NOW)).toEqual([
        { key: "refund_needed", label: "Refund needed", tone: "danger" },
      ]);
    }
  });

  it("does not show Refund needed for false, null or absent", () => {
    expect(getDealTags(deal({ refund_needed: false }), NOW)).toEqual([]);
    expect(getDealTags(deal({ refund_needed: null }), NOW)).toEqual([]);
    expect(getDealTags(deal(), NOW)).toEqual([]);
  });

  it("orders tags refund, link expired, idle when several apply", () => {
    const tags = getDealTags(
      deal({ last_activity_at: ago(9 * DAY_MS), link_expires_at: ago(DAY_MS), refund_needed: true }),
      NOW,
    );
    expect(tags.map((t) => t.key)).toEqual(["refund_needed", "link_expired", "idle"]);
  });
});
