// Mirrors the GET /api/v1/brain and GET /api/v1/brain/count contract
// (docs/designs/aira-brain-blueprint.md, section 7). Keep in step with it.

export type HandoverKind = "asked_for_human" | "knowledge_gap" | "payment" | "other";

export type InputState = "ok" | "missing" | "off" | "attention";

export type ConnectionState = "ok" | "token_problem" | "quiet" | "unknown";

export interface BrainHeadline {
  chats: number;
  handled_by_aira: number;
  handed_over: number;
  unanswered: number;
  window_days: number;
  asked_for_human: number;
  knowledge_gaps: number;
}

export interface SortReview {
  id: string;
  document_id: string;
  title: string;
  created_at: string;
}

export interface FailedFile {
  id: string;
  name: string;
}

export interface RejectedTemplate {
  id?: string;
  name?: string;
}

export interface BrainWaiting {
  count: number;
  sort_reviews: SortReview[];
  consistency_count: number;
  failed_files: FailedFile[];
  rejected_templates: RejectedTemplate[];
}

/** One Description section, for the filled/empty dots on the Description row. */
export interface InputSection {
  key: string;
  label: string;
  filled: boolean;
}

export interface BrainInput {
  key: string;
  label: string;
  state: InputState;
  detail: string;
  edit_href: string;
  can_edit: boolean;
  reason: string | null;
  /** Only the Description row carries this. Absent means no dots are drawn. */
  sections?: InputSection[];
  /** Only the Products row carries this (for example "2 draft products Aira can't see yet"). */
  flag?: string | null;
}

export interface BrainHandover {
  handover_id: string;
  /** null when the caller lacks conversations.view (the backend hides it). */
  lead_id: string | null;
  reason: string;
  kind: HandoverKind;
  likely_question: string | null;
  opened_at: string;
}

export interface BrainChannel {
  channel: string;
  last_event: string | null;
  token_problem: boolean;
}

export interface BrainConnection {
  state: ConnectionState;
  channels: BrainChannel[];
}

export interface QuotaMetric {
  metric: string;
  used: number;
  hard_cap: number;
}

export interface BrainQuota {
  metrics: QuotaMetric[];
}

export interface BrainStatus {
  auto_reply: "on" | "off";
  /** Omitted unless the caller has settings.view. */
  connection?: BrainConnection;
  /** null unless a hard cap is set. */
  quota: BrainQuota | null;
}

export interface BrainResponse {
  headline: BrainHeadline;
  waiting: BrainWaiting;
  inputs: BrainInput[];
  handovers: BrainHandover[];
  status: BrainStatus;
}

export interface BrainCount {
  count: number;
  sort_count: number;
  consistency_count: number;
}
