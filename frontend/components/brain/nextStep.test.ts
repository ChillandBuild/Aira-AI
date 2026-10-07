import { describe, expect, it } from "vitest";
import { nextBrainStep } from "./nextStep";
import type { BrainResponse } from "./types";

const brain: BrainResponse = {
  headline: { chats: 0, handled_by_aira: 0, handed_over: 0, unanswered: 0, window_days: 7, asked_for_human: 0, knowledge_gaps: 0 },
  waiting: { count: 0, sort_reviews: [], consistency_count: 0, failed_files: [], rejected_templates: [] },
  inputs: [], handovers: [], status: { auto_reply: "on", connection: { state: "ok", channels: [] }, quota: null },
};

describe("nextBrainStep", () => {
  it("prioritizes reply blockers over pending reviews", () => {
    const step = nextBrainStep({ ...brain, status: { ...brain.status, auto_reply: "off" }, waiting: { ...brain.waiting, count: 3 } });
    expect(step.section).toBe("overview");
    expect(step.title).toBe("Automatic replies are off");
  });
  it("surfaces connection problems even when nothing is waiting", () => {
    expect(nextBrainStep({ ...brain, status: { ...brain.status, connection: { state: "token_problem", channels: [] } } }).title).toBe("Check your channel connection");
  });
  it("explains that sorted knowledge is not active before approval", () => {
    const step = nextBrainStep({ ...brain, waiting: { ...brain.waiting, count: 1, sort_reviews: [{ id: "review", document_id: "doc", title: "FAQ", created_at: "2026-09-30" }] } });
    expect(step.section).toBe("approvals");
    expect(step.detail).toContain("before Anril can use");
  });
  it("does not treat optional off inputs as a setup problem", () => {
    expect(nextBrainStep({ ...brain, inputs: [{ key: "catalog", label: "Products", state: "off", detail: "Not needed", edit_href: "/dashboard/catalog", can_edit: true, reason: null }] }).section).toBe("test");
  });
  it("does not claim readiness when connection visibility is unavailable", () => {
    const step = nextBrainStep({ ...brain, status: { auto_reply: "on", quota: null } });
    expect(step.title).toBe("Check an answer before customers do");
    expect(step.detail).toContain("cannot be verified");
  });
  it("shows a reached cap ahead of knowledge improvements", () => {
    const step = nextBrainStep({ ...brain, status: { ...brain.status, quota: { metrics: [{ metric: "ai_reply", used: 10, hard_cap: 10 }] } } });
    expect(step.title).toBe("A usage cap has been reached");
  });
});
