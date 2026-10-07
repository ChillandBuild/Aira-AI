import type { BrainResponse } from "./types";

export interface BrainNextStep {
  title: string;
  detail: string;
  label: string;
  section: string;
  needsAttention: boolean;
  href?: string;
}

export function nextBrainStep(brain: BrainResponse): BrainNextStep {
  const { status, waiting } = brain;
  if (status.auto_reply === "off") return {
    title: "Automatic replies are off",
    detail: "Anril will not answer customers automatically while this switch is off. Turn it on when you want automatic replies.",
    label: "Turn on auto-reply", section: "overview", needsAttention: true, href: "/dashboard/settings/auto-reply",
  };
  if (status.connection?.state === "token_problem") return {
    title: "Check your channel connection",
    detail: "A recent connection problem may prevent replies. Check the channel before relying on Anril to answer.",
    label: "Check connection", section: "overview", needsAttention: true, href: "/dashboard/settings/connect-channels",
  };
  if (status.quota?.metrics.some((metric) => metric.used >= metric.hard_cap)) return {
    title: "A usage cap has been reached",
    detail: "A configured usage limit may prevent further replies. Review the cap and contact your account administrator.",
    label: "View usage", section: "overview", needsAttention: true,
  };
  if (waiting.count > 0) return {
    title: "Finish the items waiting on you",
    detail: waiting.sort_reviews.length > 0
      ? "Approve the sorted files before Anril can use their new answers. Other pending fixes are listed alongside them."
      : "Conflicts, failed files, or rejected templates need a decision. Open each item to see what needs fixing.",
    label: "Review pending items", section: "approvals", needsAttention: true,
  };
  const input = brain.inputs.find((item) => item.state === "missing" || item.state === "attention");
  if (input) return {
    title: `${input.label} needs attention`,
    detail: `${input.detail} Check this input so Anril has the information it needs to answer accurately.`,
    label: "Check Anril’s information", section: "knowledge", needsAttention: true,
  };
  if (brain.handovers.some((handover) => handover.kind === "knowledge_gap")) return {
    title: "Turn an unanswered question into knowledge",
    detail: "A recent conversation exposed a gap in what Anril knows. Add the correct answer, review it, then test the question again.",
    label: "Review knowledge gaps", section: "handovers", needsAttention: true,
  };
  return {
    title: "Check an answer before customers do",
    detail: status.connection?.state === "ok"
      ? "No pending items or flagged inputs in this snapshot. Test a real customer question to check the answer; setup status alone cannot prove its accuracy."
      : "No pending items or flagged inputs in this snapshot. Channel readiness cannot be verified from the available status. Test an answer and check the channel separately.",
    label: "Test a customer question", section: "test", needsAttention: false,
  };
}
