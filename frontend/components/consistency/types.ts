// Mirrors GET /api/v1/consistency and the bulk routes
// (backend/app/routes/consistency.py; blueprint sections 7 and 9).

export type IssueKind = "price" | "required_detail" | "handover" | "other";
export type IssueWhere = "description" | "knowledge";

export interface Issue {
  id: string;
  kind: IssueKind;
  where: IssueWhere;
  document_id?: string | null;
  document_name: string | null;
  editable: boolean;
  quote: string;
  topic: string;
  truth: string;
  proposed: string | null;
  /** Key of the Description section holding the quote; null for files, the free-text area, or not found. */
  section?: string | null;
  section_label?: string | null;
}

export interface DismissedIssue {
  id: string;
  topic: string;
  quote: string;
  where: IssueWhere;
  document_name: string | null;
  section?: string | null;
  section_label?: string | null;
}

export interface Report {
  issues: Issue[];
  checked_at: string | null;
  stale: boolean;
  suggestions_complete?: boolean;
  dismissed_issues: DismissedIssue[];
}

export interface BatchNote {
  id: string;
  reason: string;
  code?: string;
}

export interface FixBatchResult {
  applied: string[];
  skipped: BatchNote[];
  failed: BatchNote[];
}

export interface DismissBatchResult {
  dismissed: string[];
  skipped: BatchNote[];
}

export interface RestoreBatchResult {
  restored: string[];
  skipped: BatchNote[];
}

export type BulkAction = "fix" | "dismiss";

export interface Access {
  canManage: boolean;
  isOwner: boolean;
}
