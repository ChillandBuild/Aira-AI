import type { CallLog } from "@/lib/api";

/** Human label for a call that owes feedback, e.g. "Missed call from lead". */
export function pendingCallLabel(log: Pick<CallLog, "direction" | "duration_seconds" | "status">): string {
  if (log.direction === "missed") return "Missed call";
  if (log.direction === "incoming") return "Incoming";
  const answered = (log.duration_seconds ?? 0) > 0;
  if (log.direction === "outgoing" && !answered) return "Outgoing, not answered";
  if (log.direction === "outgoing") return "Outgoing";
  return log.status === "sim_started" ? "Call started from Aira" : "Call";
}
