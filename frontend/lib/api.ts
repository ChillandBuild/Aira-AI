import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://aira-ai-5tfr.onrender.com";
const MAX_LEADS_LIST_LIMIT = 200;

export async function getAuthHeaders(): Promise<Record<string, string>> {
  const supabase = createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) return {};
  return { Authorization: `Bearer ${session.access_token}` };
}

export interface Lead {
  id: string;
  phone: string | null;
  name: string | null;
  source: string;
  score: number;
  segment: "A" | "B" | "C" | "D";
  ai_enabled: boolean;
  opted_out: boolean;
  converted_at?: string | null;
  assigned_to?: string | null;
  needs_human_intervention?: boolean;
  tg_username?: string | null;
  ig_user_id?: string | null;
  fb_user_id?: string | null;
  ad_campaign_id?: string | null;
  created_at: string;
  last_message_content?: string | null;
  pinned_at?: string | null;
  last_inbound_at?: string | null;
  broadcast_sent_at?: string | null;
  assigned_at?: string | null;
  broadcast_id?: string | null;
  template_name?: string | null;
  tag_name?: string | null;
  ad_campaign_name?: string | null;
  channel?: string | null;
  call_status?: "new" | "in_progress" | "callback" | "converted" | "not_interested" | "dnc" | "unreachable" | null;
  do_not_call?: boolean;
  needs_human_attention?: boolean;
  archived_at?: string | null;
  blocked_at?: string | null;
}

export interface CatalogItem {
  id: string;
  tenant_id: string;
  name: string;
  item_type: string;
  description: string | null;
  status: "draft" | "ready";
  created_at: string;
  updated_at: string;
}

export interface CatalogMedia {
  id: string;
  tenant_id: string;
  catalog_item_id: string;
  storage_path: string;
  label: string | null;
  created_at: string;
  item_name?: string | null;
  url?: string;
}

export interface CatalogAiRules {
  can_recommend: boolean;
  can_send_images: boolean;
  max_images_per_reply: number;
}

export interface Message {
  id: string;
  lead_id: string;
  direction: "inbound" | "outbound";
  channel: string;
  content: string;
  is_ai_generated: boolean;
  reply_source?: "knowledge" | "ai" | null;
  meta_message_id?: string | null;
  media_url?: string | null;
  media_type?: "image" | "document" | "audio" | "video" | "sticker" | null;
  media_filename?: string | null;
  media_mime_type?: string | null;
  created_at: string;
}

export interface Caller {
  id: string;
  name: string;
  phone: string | null;
  overall_score: number;
  active: boolean;
  status?: "active" | "break" | "logged_out";
  status_changed_at?: string;
  target?: number;
  telecmi_agent_id?: string | null;
  has_telecmi_agent_password?: boolean;
  shift_start_hour?: number | null;
  shift_end_hour?: number | null;
}

export interface CallerStats {
  calls_today: number;
  calls_this_week: number;
  conversion_rate_week: number;
  avg_duration_seconds: number | null;
  pending_hot_leads: number;
  overall_score: number;
  name: string;
  phone: string;
  status: string;
  caller_id: string;
}

export type Disposition = "answered" | "no_answer" | "busy" | "switched_off" | "followup_required";
export type ManualCallStatus = "connected" | "not_picked" | "busy" | "wrong_number" | "interested" | "not_interested" | "callback";
export type CallOutcome = "converted" | "interested" | "callback" | "not_interested" | "no_answer" | "do_not_call" | "do_not_contact" | "in_progress";

export interface TemplatePerformanceRow {
  template_name: string;
  broadcasts: number;
  sent: number;
  read: number;
  replied: number;
  hot_leads: number;
  last_sent: string | null;
}

export interface CallEvaluation {
  evaluation_version?: number;
  greeting_quality?: number;
  greeting_quality_reason?: string;
  communication_clarity?: number;
  communication_clarity_reason?: string;
  product_knowledge?: number;
  product_knowledge_reason?: string;
  requirement_understanding?: number;
  requirement_understanding_reason?: string;
  conversation_engagement?: number;
  conversation_engagement_reason?: string;
  objection_handling?: number;
  objection_handling_reason?: string;
  professionalism?: number;
  professionalism_reason?: string;
  talk_ratio?: number;
  overall_score?: number;
  quality_label?: "Excellent" | "Good" | "Average" | "Bad";
  clear_next_step?: boolean;
  next_step_summary?: string | null;
  outcome_match?: boolean;
  outcome_match_reason?: string;
  purchase_intent?: "high" | "medium" | "low";
  missed_opportunity?: boolean;
  missed_opportunity_note?: string | null;
  coaching_tip?: string;
}

export interface CallLog {
  id: string;
  lead_id: string | null;
  call_sid: string | null;
  duration_seconds: number | null;
  outcome: CallOutcome | null;
  disposition: string | null;
  manual_status?: ManualCallStatus | null;
  recording_url: string | null;
  score: number | null;
  status: string;
  ai_summary: {
    course?: string;
    product?: string;
    budget?: string;
    timeline?: string;
    next_action?: string;
    sentiment?: string;
    brief?: string;
  } | null;
  evaluation: CallEvaluation | null;
  quality_rating: number | null;
  notes?: string | null;
  provider?: "telecmi" | "sim_basic";
  feedback_source?: "automatic" | "manual";
  manual_started_at?: string | null;
  manual_ended_at?: string | null;
  transcript: string | null;
  created_at: string;
  leads?: { phone: string | null; name: string | null } | null;
}

export interface DigestEntry {
  digest_date: string;
  call_count: number;
  stats: {
    total_calls: number;
    converted: number;
    callbacks: number;
    not_interested: number;
    no_answer: number;
    avg_duration_seconds: number;
    avg_score: number | null;
    weakest_criterion: string | null;
    criteria_avg: Record<string, number>;
  };
  coaching_report: string | null;
  created_at: string;
}

export interface NoteWithLead {
  id: string;
  lead_id: string;
  caller_id: string | null;
  call_log_id: string | null;
  content: string;
  structured: {
    course?: string;
    product?: string;
    budget?: string;
    timeline?: string;
    next_action?: string;
    sentiment?: string;
    brief?: string;
  };
  is_pinned: boolean;
  tags?: string[];
  created_at: string;
  leads: { id: string; name: string | null; phone: string; segment: string; score: number; assigned_to: string | null } | null;
}

export interface SegmentTemplate {
  id: string;
  segment: "A" | "B" | "C" | "D";
  message: string;
  enabled: boolean;
  updated_at: string;
}

export interface BroadcastHistoryItem {
  timestamp: string;
  broadcast_id?: string;
  template_name: string;
  opt_in_source: string;
  sent: number;
  delivered: number;
  opened: number;
  failed: number;
  total_leads: number;
  number_used: string;
  csv_file_url?: string;
  csv_file_path?: string;
  csv_file_name?: string;
  tag_id?: string;
  tag_name?: string;
  hot?: number;
  warm?: number;
  cold?: number;
  replied_positive?: number;
  replied_negative?: number;
  replied_neutral?: number;
}

export interface BroadcastResult {
  total: number;
  sent: number;
  failed: number;
  skipped_window: number;
}

export interface WabaTemplate {
  id: string;
  name: string;
  category: string;
  status: string;
  body_text?: string | null;
}

export interface ReengagementStep {
  id: string;
  tenant_id: string;
  type: "broadcast" | "inbound";
  broadcast_id?: string | null;
  delay_hours: number;
  target_segments: string[];
  target_sources?: string[] | null;
  message_type: "freeform" | "template";
  message_content?: string | null;
  template_name?: string | null;
  template_variables?: string[] | null;
  fallback_template_name?: string | null;
  fallback_template_variables?: string[] | null;
  created_at: string;
}

export interface ReengagementLog {
  id: string;
  step_id: string;
  lead_id: string;
  status: "sent" | "sent_fallback" | "skipped_window" | "failed";
  sent_at: string;
  leads?: { name: string | null; phone: string; segment: string | null } | null;
}

export interface AIPrompt {
  id: string;
  name: string;
  content: string;
  updated_at: string;
}

export interface TuneSuggestion {
  id: string;
  for_prompt: string;
  suggestion: string;
  rationale: string | null;
  status: "pending" | "applied" | "rejected";
  created_at: string;
}

export interface AnalyzeResult {
  analyzed_leads: number;
  suggestions_created: number;
  data: TuneSuggestion[];
}

export interface SystemStatus {
  has_meta: boolean;
  has_gemini: boolean;
  has_groq: boolean;
  supabase_url: string;
  active_prompt: { name: string; updated_at: string } | null;
}

export interface AnalyticsOverview {
  daily_leads: { day: string; count: number }[];
  daily_messages: { day: string; inbound: number; outbound: number }[];
  funnel: { inquiries: number; engaged: number; hot: number; converted: number };
  ai_vs_human: { ai: number; human: number };
  unreplied_24h: number;
  converted_7d: number;
  ai_handled_today: number;
  by_segment: Record<"A" | "B" | "C" | "D", number>;
}

export interface FollowUpQueueItem {
  id: string;
  lead_id: string;
  cadence: "1d" | "1w" | "1m";
  status: string;
  scheduled_for: string;
  sent_at: string | null;
  message_preview: string | null;
  skip_reason: string | null;
  last_error: string | null;
  lead_name: string | null;
  phone: string | null;
  segment: "A" | "B" | "C" | "D" | null;
}

export interface FollowUpSummary {
  pending: number;
  due_now: number;
  sent_7d: number;
  failed_7d: number;
  skipped_7d: number;
  by_cadence: { cadence: "1d" | "1w" | "1m"; pending: number; due_now: number; sent_7d: number }[];
  queue: FollowUpQueueItem[];
}

export interface FollowUpRunResult {
  processed: number;
  sent: number;
  failed: number;
  skipped: number;
  summary: FollowUpSummary;
}

export interface CallbackBoardItem {
  id: string;
  lead_id: string;
  scheduled_for: string;
  message_preview: string | null;
  status: string;
  lead: {
    id: string;
    name: string | null;
    phone: string | null;
    segment: "A" | "B" | "C" | "D" | null;
    assigned_to: string | null;
    score: number | null;
  };
  assigned_caller: {
    id: string;
    name: string;
    status: "active" | "break" | "logged_out";
    is_on_call: boolean;
  } | null;
  scheduled_by: {
    id: string;
    name: string | null;
  } | null;
}

export interface AdCampaignInsight {
  id: string;
  platform: "instagram" | "facebook" | "google";
  campaign_name: string;
  external_campaign_id: string | null;
  spend_inr: number;
  total_leads: number;
  progressive_leads: number;
  conversion_count: number;
  engaged_count: number;
  hot_count: number;
  segment_mix: { A: number; B: number; C: number; D: number };
  progressive_rate: number;
  conversion_rate: number;
  engaged_rate: number;
  cost_per_lead: number | null;
  cost_per_conversion: number | null;
  budget_recommendation: "increase" | "hold" | "decrease";
  suggestions: string[];
  adset_examples: string[];
  creative_examples: string[];
}

export interface AdPerformanceSummary {
  totals: {
    campaigns: number;
    tracked_leads: number;
    progressive_rate: number;
    conversion_rate: number;
    recommend_increase: number;
    recommend_decrease: number;
  };
  campaigns: AdCampaignInsight[];
}

export interface TeamMember {
  user_id: string;
  role: "owner" | "caller";
  role_id?: string | null;
  role_name?: string | null;
  permissions?: string[];
  full_name?: string | null;
  force_password_reset?: boolean;
  created_at: string;
  caller_profile: {
    id: string;
    name: string | null;
    phone: string | null;
    overall_score: number | null;
    active: boolean;
    telecmi_agent_id: string | null;
  } | null;
}

export interface AttendanceDay {
  date: string;
  status: "present" | "absent" | "holiday" | "future";
}

export interface CallerAttendance {
  caller_id: string;
  days: AttendanceDay[];
  today_status: "present" | "absent" | "holiday" | "future";
}

export interface TeamAttendanceSummary {
  present_today: number;
  absent_today: number;
  attendance_rate_month: number;
}

export interface TeamAttendanceGridData {
  callers: { caller_id: string; name: string }[];
  days: string[];
  grid: Record<string, Record<string, "present" | "absent" | "holiday" | "future">>;
  summary: TeamAttendanceSummary;
}

export interface MyProfile {
  tenant_id: string;
  role: "owner" | "caller";
  role_id?: string | null;
  role_name?: string | null;
  role_slug?: string | null;
  permissions?: string[];
  force_password_reset?: boolean;
  caller_profile: {
    id: string;
    name: string | null;
    phone: string | null;
    overall_score: number | null;
  } | null;
}

export interface PermissionDef {
  key: string;
  label: string;
  group: string;
}

export interface ClientRole {
  id: string;
  tenant_id: string;
  name: string;
  slug: string | null;
  description: string | null;
  permissions: string[];
  is_system_template: boolean;
  created_at: string;
  updated_at: string;
}

export interface RbacUser {
  user_id: string;
  full_name: string;
  email: string;
  role: "owner" | "caller";
  role_id: string | null;
  role_name: string;
  force_password_reset: boolean;
  created_at: string;
  caller_profile: TeamMember["caller_profile"];
}

export interface WhatsAppAnalytics {
  messages_sent_today: number;
  messages_received_today: number;
  ai_reply_count_today: number;
  avg_reply_time_seconds: number | null;
}

export interface TelecallingAnalytics {
  calls_today: number;
  calls_this_week: number;
  avg_duration_seconds: number | null;
  outcome_breakdown: { converted: number; interested: number; callback: number; not_interested: number; no_answer: number };
  manual_status_breakdown?: Record<ManualCallStatus, number>;
  per_caller: {
    caller_id: string;
    name: string;
    calls_today: number;
    overall_score: number | null;
    connect_rate?: number;
    avg_talk_seconds?: number | null;
    talk_minutes_today?: number;
    idle_minutes_today?: number;
    avg_gap_seconds?: number | null;
    longest_idle_seconds?: number | null;
    bunking_flag?: boolean;
    speed_to_lead_min?: number | null;
    quality_avg?: number | null;
  }[];
  connect_rate?: number;
  avg_talk_seconds?: number | null;
  talk_minutes_today?: number;
  idle_minutes_today?: number;
  avg_gap_seconds?: number | null;
  longest_idle_seconds?: number | null;
  speed_to_lead_min?: number | null;
  quality_avg?: number | null;
}

export interface TelecallingConfig {
  enabled?: boolean;
  calling_provider?: "telecmi" | "sim_basic";
  segments?: string[];
  channels?: string[];
  scripts?: Record<string, string>;
  assignment_mode?: "push" | "pull";
}

export interface FunnelAnalytics {
  total_leads: number;
  by_segment: { A: number; B: number; C: number; D: number };
  by_source: { whatsapp: number; instagram: number; upload: number };
  leads_this_week: number;
  avg_score: number | null;
}

export interface AnalyticsOverviewExtended {
  daily_leads: { day: string; count: number }[];
  daily_messages: { day: string; inbound: number; outbound: number }[];
  funnel: { inquiries: number; engaged: number; hot: number; converted: number };
  ai_vs_human: { ai: number; human: number };
  unreplied_24h: number;
  converted_7d: number;
  converted_today: number;
  ai_handled_today: number;
  by_segment: Record<"A" | "B" | "C" | "D", number>;
  channel_breakdown: { whatsapp: number; instagram: number; facebook: number; telegram: number; upload: number; manual: number };
  total_leads: number;
}

export interface MessagingAnalytics {
  sent_today: number;
  received_today: number;
  ai_reply_rate: number | null;
  reply_source_breakdown: { ai: number; knowledge: number; manual: number; unknown: number };
  daily_messages: { day: string; inbound: number; outbound: number }[];
}

export interface TelecallingComparisonMetrics {
  calls: number;
  connect_rate: number;
  conversions: number;
  avg_talk_seconds: number;
  idle_minutes: number;
}

export interface TelecallingAnalyticsExtended {
  calls_today: number;
  calls_this_week: number;
  avg_duration_seconds: number | null;
  total_minutes_today: number;
  calls_attempted?: number;
  connected_calls?: number;
  not_picked_calls?: number;
  busy_calls?: number;
  wrong_number_calls?: number;
  interested_leads?: number;
  followups_scheduled?: number;
  outcome_breakdown: { converted: number; interested: number; callback: number; not_interested: number; no_answer: number };
  manual_status_breakdown: Record<ManualCallStatus, number>;
  manual_status_all_time_breakdown?: Record<ManualCallStatus, number>;
  conversions_today?: number;
  per_caller: {
    caller_id: string;
    name: string;
    calls_today: number;
    overall_score: number | null;
    total_minutes_today: number;
    conversion_rate: number | null;
    connect_rate?: number;
    avg_talk_seconds?: number | null;
    talk_minutes_today?: number;
    idle_minutes_today?: number;
    avg_gap_seconds?: number | null;
    longest_idle_seconds?: number | null;
    bunking_flag?: boolean;
    speed_to_lead_min?: number | null;
    quality_avg?: number | null;
  }[];
  calls_per_hour: { hour: number; label: string; count: number }[];
  calls_per_slot: { slot: string; count: number; caller_counts: Record<string, number> }[];
  connect_rate?: number;
  avg_talk_seconds?: number | null;
  talk_minutes_today?: number;
  idle_minutes_today?: number;
  avg_gap_seconds?: number | null;
  longest_idle_seconds?: number | null;
  speed_to_lead_min?: number | null;
  quality_avg?: number | null;
  comparison?: {
    yesterday: TelecallingComparisonMetrics;
    avg_7d: TelecallingComparisonMetrics;
  };
}

export interface FunnelAnalyticsExtended {
  total_leads: number;
  by_segment: { A: number; B: number; C: number; D: number };
  by_source: { whatsapp: number; instagram: number; facebook: number; telegram: number; upload: number; manual: number };
  leads_this_week: number;
  avg_score: number | null;
  score_histogram: { range: string; count: number }[];
  hot_lead_aging: { bucket: string; count: number }[];
}

// Transient statuses worth a retry: server waking / restarting / behind a proxy.
const RETRYABLE_STATUS = new Set([502, 503, 504]);
// Cold-start (Render spin-up) can take 30–50s; give GETs room, keep mutations tight.
const GET_TIMEOUT_MS = 45_000;
const MUTATION_TIMEOUT_MS = 15_000;
const RETRY_DELAYS_MS = [2_000, 6_000, 15_000];

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Marks failures safe to retry (network/timeout/transient status) vs. real errors.
class RetryableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RetryableError";
  }
}

async function apiFetchOnce<T>(path: string, opts: RequestInit, timeoutMs: number): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...opts,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders,
        ...(opts.headers as Record<string, string> ?? {}),
      },
    });
    if (!res.ok) {
      if (res.status === 401 && typeof window !== "undefined") {
        window.location.href = "/aira/login";
      }
      if (RETRYABLE_STATUS.has(res.status)) {
        throw new RetryableError(`Server unavailable (${res.status})`);
      }
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      const error = new Error(err.detail || "Request failed") as Error & { status?: number };
      error.status = res.status;
      throw error;
    }
    return res.json();
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new RetryableError("Request timed out — server took too long to respond");
    }
    // Safari says "Load failed", Chrome says "Failed to fetch", Firefox says "NetworkError…"
    // Any TypeError from fetch() is a network-layer failure — always retryable.
    if (err instanceof TypeError) {
      throw new RetryableError("Cannot reach server — it may be restarting.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();
  // Only idempotent reads are retried — retrying a POST/PATCH/DELETE could
  // double-send a broadcast/message/assignment if the first reached the server.
  const idempotent = method === "GET" || method === "HEAD";
  const timeoutMs = idempotent ? GET_TIMEOUT_MS : MUTATION_TIMEOUT_MS;
  const maxAttempts = idempotent ? RETRY_DELAYS_MS.length + 1 : 1;

  let lastErr: unknown;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await apiFetchOnce<T>(path, opts, timeoutMs);
    } catch (err) {
      lastErr = err;
      if (!(err instanceof RetryableError) || attempt === maxAttempts - 1) break;
      await delay(RETRY_DELAYS_MS[attempt]);
    }
  }
  if (lastErr instanceof RetryableError) {
    throw new Error(
      lastErr.message.includes("timed out")
        ? lastErr.message
        : "Cannot reach server — it may be restarting. Try again in 30 seconds.",
    );
  }
  throw lastErr;
}

export interface AppNotification {
  id: string;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

export interface PoolItem {
  kind: "handover";
  id: string;
  lead_id: string;
  lead_name: string | null;
  reason: string | null;
  created_at: string;
}

export type NotificationConfig = {
  push_enabled: boolean;
  events: Record<string, boolean>;
  claimable_threshold_minutes: number;
  claimable_audience: "telecallers_and_admin" | "telecallers_only" | "admin_only" | "specific";
  claimable_caller_ids: string[];
  quiet_hours: { enabled: boolean; start_hour: number; end_hour: number };
  whatsapp_notifications: {
    enabled: boolean;
    recipient_phones: string[];
    template_id: string | null;
    target_segments: string[];
    delay_minutes?: number;
  };
};

export interface TimelineEvent {
  type: "status" | "call";
  id: string;
  status?: string;
  outcome?: string;
  started_at: string;
  ended_at?: string | null;
  duration_seconds: number | null;
  lead_name?: string;
  lead_phone?: string;
}

export interface AssignmentLogEntry {
  id: string;
  lead_id: string | null;
  lead_name: string | null;
  lead_phone: string | null;
  segment: string | null;
  event_type: "assigned" | "reassigned";
  caller_id: string | null;
  caller_name: string | null;
  prev_caller_name: string | null;
  reason: string | null;
  method: string | null;
  score: number | null;
  matched_segments: string[] | null;
  created_at: string;
}

export interface AssignmentLogSummary {
  assigned_today: number;
  by_caller: Record<string, { caller_name: string; count: number } | number>;
  by_segment: Record<string, number>;
}

export const api = {
  leads: {
    list: async (params?: {
      segment?: string;
      limit?: number;
      skip?: number;
      assigned_to?: string;
      source_filter?: string;
      broadcast_id?: string;
      ad_campaign_id?: string;
    }) => {
      const qs = new URLSearchParams();
      if (params?.segment) qs.set("segment", params.segment);
      if (params?.assigned_to) qs.set("assigned_to", params.assigned_to);
      if (params?.source_filter) qs.set("source_filter", params.source_filter);
      if (params?.broadcast_id) qs.set("broadcast_id", params.broadcast_id);
      if (params?.ad_campaign_id) qs.set("ad_campaign_id", params.ad_campaign_id);
      if (typeof params?.limit === "number" && Number.isFinite(params.limit)) {
        const normalizedLimit = Math.min(Math.max(Math.trunc(params.limit), 1), MAX_LEADS_LIST_LIMIT);
        qs.set("limit", String(normalizedLimit));
      }
      if (params?.skip) qs.set("skip", String(params.skip));
      const res = await apiFetch<{ data: Lead[] }>(`/api/v1/leads/?${qs}`);
      return res.data || [];
    },
    get: (id: string) => apiFetch<Lead>(`/api/v1/leads/${id}`),
    update: (id: string, data: Partial<Pick<Lead, "name" | "score" | "segment">>) =>
      apiFetch<Lead>(`/api/v1/leads/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    convert: (id: string, notes?: string) =>
      apiFetch<Lead>(`/api/v1/leads/${id}/convert`, {
        method: "POST",
        body: JSON.stringify({ notes: notes ?? null }),
      }),
    toggleAI: (id: string, enabled: boolean) =>
      apiFetch<Lead>(`/api/v1/leads/${id}/ai`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    sendMessage: (id: string, content: string) =>
      apiFetch<Message>(`/api/v1/leads/${id}/send`, {
        method: "POST",
        body: JSON.stringify({ content }),
      }),
    sendMedia: async (id: string, file: File, caption?: string): Promise<Message> => {
      const authHeaders = await getAuthHeaders();
      const fd = new FormData();
      fd.append("file", file);
      if (caption) fd.append("caption", caption);
      const res = await fetch(`${API_URL}/api/v1/leads/${id}/send-media`, {
        method: "POST",
        body: fd,
        headers: { ...authHeaders },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Media send failed" }));
        throw new Error(err.detail || "Media send failed");
      }
      return res.json();
    },
    compose: (phone: string, content: string, name?: string) =>
      apiFetch<{ lead_id: string; sid: string; phone: string }>(`/api/v1/leads/compose`, {
        method: "POST",
        body: JSON.stringify({ phone, content, name }),
      }),
    broadcast: (data: {
      message: string;
      segment?: string;
      source_filter?: string;
      broadcast_id?: string;
      ad_campaign_id?: string;
    }) =>
      apiFetch<{ total: number; sent: number; failed: number; skipped_window: number }>(
        `/api/v1/leads/broadcast`,
        {
          method: "POST",
          body: JSON.stringify(data),
        }
      ),
    delete: (id: string) =>
      apiFetch<{ success: boolean; message: string }>(`/api/v1/leads/${id}`, {
        method: "DELETE",
      }),
    clearChat: (id: string) =>
      apiFetch<{ success: boolean; message: string }>(`/api/v1/leads/${id}/clear-chat`, {
        method: "DELETE",
      }),
    pin: (id: string) =>
      apiFetch<Lead>(`/api/v1/leads/${id}/pin`, {
        method: "PATCH",
      }),
    archive: (id: string) =>
      apiFetch<Lead>(`/api/v1/leads/${id}/archive`, {
        method: "PATCH",
      }),
    block: (id: string) =>
      apiFetch<Lead>(`/api/v1/leads/${id}/block`, {
        method: "PATCH",
      }),
    release: (id: string) =>
      apiFetch<{ released: boolean }>(`/api/v1/leads/${id}/release`, {
        method: "PATCH",
      }),
    messages: async (id: string) => {
      const res = await apiFetch<Message[] | { data: Message[] }>(`/api/v1/leads/${id}/messages`);
      return Array.isArray(res) ? res : res.data || [];
    },
    callLogs: async (leadId: string) => {
      const res = await apiFetch<{ data: CallLog[] }>(`/api/v1/leads/${leadId}/call-logs`);
      return res.data || [];
    },
    preCallBrief: async (leadId: string) =>
      apiFetch<{ brief: string; opener: string }>(`/api/v1/leads/${leadId}/pre-call-brief`, { method: "POST" }),
    exportUrl: (segment?: string) =>
      `${API_URL}/api/v1/leads/export${segment ? `?segment=${segment}` : ""}`,
    exportLeads: async (segment?: string) => {
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/leads/export${segment ? `?segment=${segment}` : ""}`, { headers });
      if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `leads_${segment || "all"}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    },
    exportAssigned: async () => {
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/leads/export-assigned`, { headers });
      if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `my_assigned_leads.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    },
    assign: (leadId: string, callerId: string | null) =>
      apiFetch<Lead>(`/api/v1/leads/${leadId}/assign`, {
        method: "PATCH",
        body: JSON.stringify({ caller_id: callerId }),
      }),
    bulkAssign: (leadIds: string[], callerId: string | null) =>
      apiFetch<{ success: boolean; updated: number }>(`/api/v1/leads/bulk-assign`, {
        method: "POST",
        body: JSON.stringify({ lead_ids: leadIds, caller_id: callerId }),
      }),
    takeover: (leadId: string) =>
      apiFetch<{ success: boolean; assigned_to: string }>(`/api/v1/leads/${leadId}/takeover`, {
        method: "POST",
      }),
  },
  assignmentLog: {
    list: async (params?: { page?: number; limit?: number; caller_id?: string; segment?: string; from_date?: string; to_date?: string }) => {
      const qs = new URLSearchParams();
      if (params?.page) qs.set("page", String(params.page));
      if (params?.limit) qs.set("limit", String(params.limit));
      if (params?.caller_id) qs.set("caller_id", params.caller_id);
      if (params?.segment) qs.set("segment", params.segment);
      if (params?.from_date) qs.set("from_date", params.from_date);
      if (params?.to_date) qs.set("to_date", params.to_date);
      return apiFetch<{ data: AssignmentLogEntry[]; meta: { total: number; page: number; limit: number } }>(`/api/v1/assignment-log?${qs.toString()}`);
    },
    summary: () =>
      apiFetch<AssignmentLogSummary>(`/api/v1/assignment-log/summary`),
    exportCsv: async (params?: { caller_id?: string; segment?: string; from_date?: string; to_date?: string }) => {
      const headers = await getAuthHeaders();
      const qs = new URLSearchParams({ format: "csv" });
      if (params?.caller_id) qs.set("caller_id", params.caller_id);
      if (params?.segment) qs.set("segment", params.segment);
      if (params?.from_date) qs.set("from_date", params.from_date);
      if (params?.to_date) qs.set("to_date", params.to_date);
      const res = await fetch(`${API_URL}/api/v1/assignment-log?${qs.toString()}`, { headers });
      if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "assignment-log.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    },
  },
  callers: {
    create: (name: string, phone: string) =>
      apiFetch<Caller>(`/api/v1/callers/`, {
        method: "POST",
        body: JSON.stringify({ name, phone }),
      }),
    update: (id: string, data: { name?: string; phone?: string; telecmi_agent_id?: string | null; telecmi_agent_password?: string | null; shift_start_hour?: number | null; shift_end_hour?: number | null }) =>
      apiFetch<Caller>(`/api/v1/callers/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    remove: (id: string) =>
      apiFetch<{ deleted: boolean }>(`/api/v1/callers/${id}`, { method: "DELETE" }),
    list: async () => {
      const res = await apiFetch<{ data: Caller[]; admin_caller?: Caller | null }>(`/api/v1/callers/`);
      return { data: res.data || [], admin_caller: res.admin_caller ?? null };
    },
    logs: async (id: string) => {
      const res = await apiFetch<{ data: CallLog[] }>(`/api/v1/callers/${id}/logs`);
      return res.data || [];
    },
    coaching: (id: string) =>
      apiFetch<{ caller_id: string; tip: string }>(`/api/v1/callers/${id}/coaching`),
    digest: (id: string, days = 7) =>
      apiFetch<{ data: DigestEntry[] }>(`/api/v1/callers/${id}/digest?days=${days}`).then(r => r.data || []),
    myStatus: () =>
      apiFetch<{ status: string; caller_id: string | null }>(`/api/v1/callers/my-status`),
    setMyStatus: (status: "active" | "break" | "logged_out") =>
      apiFetch<{ status: string; changed_at: string }>(`/api/v1/callers/my-status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    myStats: () =>
      apiFetch<CallerStats>(`/api/v1/callers/my-stats`),
    statusSummary: (id: string) =>
      apiFetch<{
        active_minutes_today: number;
        break_minutes_today: number;
        idle_minutes_today: number;
        current_status: string;
        since: string;
        first_login_at: string | null;
        last_logout_at: string | null;
        breaks: { started_at: string; ended_at: string | null; duration_minutes: number }[];
        scheduled_count: number;
      }>(`/api/v1/callers/${id}/status-summary`),
    getTimeline: (id: string, date?: string) => {
      const q = date ? `?date=${encodeURIComponent(date)}` : "";
      return apiFetch<{ data: TimelineEvent[] }>(`/api/v1/callers/${id}/timeline${q}`);
    },
    winners: () =>
      apiFetch<{
        daily: { caller_id: string; name: string; value: number; label: string } | null;
        monthly: { caller_id: string; name: string; value: number; calls_this_month: number; label: string } | null;
      }>(`/api/v1/callers/winners`),
    myCallsToday: () =>
      apiFetch<{ data: CallLog[] }>(`/api/v1/callers/my-calls-today`).then(res => res.data || []),
    myPerformance: () =>
      apiFetch<{ target: number; achieved: number }>(`/api/v1/callers/my-performance`),
    updateTarget: (callerId: string, target: number) =>
      apiFetch<Caller>(`/api/v1/callers/${callerId}/target`, {
        method: "PATCH",
        body: JSON.stringify({ target }),
      }),
  },
  calls: {
    initiate: (target: { leadId?: string; phone?: string; callbackJobId?: string }, callerId?: string) =>
      apiFetch<{ call_log_id: string; call_sid: string; status: string; provider: "telecmi" | "sim_basic"; lead_id: string | null; lead_name: string | null; phone?: string | null }>(
        `/api/v1/calls/initiate`,
        { method: "POST", keepalive: true, body: JSON.stringify({ lead_id: target.leadId, phone: target.phone, caller_id: callerId, callback_job_id: target.callbackJobId }) }
      ),
    setOutcome: (
      callLogId: string,
      outcome: NonNullable<CallLog["outcome"]>,
      opts?: { callbackTime?: string; notes?: string; qualityRating?: number; durationSeconds?: number; manualStartedAt?: string; manualEndedAt?: string; manualStatus?: ManualCallStatus }
    ) =>
      apiFetch<{
        call_log_id: string;
        outcome: string;
        score: number;
        caller_overall_score: number | null;
      }>(`/api/v1/calls/${callLogId}/outcome`, {
        method: "PATCH",
        body: JSON.stringify({
          outcome,
          manual_status: opts?.manualStatus ?? null,
          callback_time: opts?.callbackTime ?? null,
          notes: opts?.notes ?? null,
          quality_rating: opts?.qualityRating ?? null,
          duration_seconds: opts?.durationSeconds ?? null,
          manual_started_at: opts?.manualStartedAt ?? null,
          manual_ended_at: opts?.manualEndedAt ?? null,
        }),
      }),
    setDisposition: (
      callLogId: string,
      disposition: Disposition,
      opts?: { notes?: string; callbackTime?: string },
    ) =>
      apiFetch<{
        call_log_id: string;
        outcome: string | null;
        disposition: string | null;
        score: number | null;
        caller_overall_score: number | null;
      }>(`/api/v1/calls/${callLogId}/outcome`, {
        method: "PATCH",
        body: JSON.stringify({
          disposition,
          notes: opts?.notes ?? null,
          callback_time: opts?.callbackTime ?? null,
        }),
      }),
    statsToday: () =>
      apiFetch<{ calls_today: number; conversions_today: number }>(`/api/v1/calls/stats-today`),
    recentByLeads: (leadIds: string[]) =>
      apiFetch<Record<string, string>>(
        `/api/v1/calls/recent-by-leads?lead_ids=${leadIds.slice(0, 50).join(",")}`,
      ),
    deleteLog: (callLogId: string) =>
      apiFetch<{ deleted: boolean }>(`/api/v1/calls/${callLogId}`, { method: "DELETE" }),
    getLog: (callLogId: string) =>
      apiFetch<CallLog>(`/api/v1/calls/${callLogId}`),
    generateSummary: (callLogId: string) =>
      apiFetch<CallLog>(`/api/v1/calls/${callLogId}/generate-summary`, { method: "POST" }),
    getPendingWrapups: () =>
      apiFetch<CallLog[]>(`/api/v1/calls/pending-wrapups`),
    nextLead: (callerId?: string) =>
      apiFetch<Lead>(`/api/v1/calls/next-lead${callerId ? `?caller_id=${callerId}` : ""}`),
    assignmentMode: () =>
      apiFetch<{ mode: "push" | "pull"; enabled: boolean; calling_provider: "telecmi" | "sim_basic" }>(`/api/v1/calls/assignment-mode`),
    sendToMobile: (leadId: string, callerId?: string | null) =>
      apiFetch<{
        sent: boolean;
        lead_id: string;
        caller_id: string | null;
        push_url: string;
        push_configured: boolean;
        subscription_count: number;
      }>(`/api/v1/calls/send-to-mobile`, {
        method: "POST",
        body: JSON.stringify({ lead_id: leadId, caller_id: callerId || undefined }),
      }),
  },
  notes: {
    leadsWithActivity: () =>
      apiFetch<{ data: { id: string; name: string | null; phone: string; score: number; segment: string; assigned_to: string | null }[] }>(
        `/api/v1/lead-notes/leads-with-activity`
      ),
    all: () =>
      apiFetch<{ data: NoteWithLead[] }>(`/api/v1/lead-notes/all`),
    update: (noteId: string, data: { content?: string; is_pinned?: boolean; tags?: string[] }) =>
      apiFetch<{ id: string; content: string; is_pinned: boolean; tags: string[] }>(
        `/api/v1/lead-notes/note/${noteId}`,
        { method: "PATCH", body: JSON.stringify(data) }
      ),
    delete: (noteId: string) =>
      apiFetch<{ deleted: boolean }>(`/api/v1/lead-notes/note/${noteId}`, { method: "DELETE" }),
  },
  segments: {
    templates: async () => {
      const res = await apiFetch<{ data: SegmentTemplate[] }>(`/api/v1/segments/templates`);
      return res.data || [];
    },
    saveTemplate: (segment: string, message: string, enabled = true) =>
      apiFetch<SegmentTemplate>(`/api/v1/segments/templates/${segment}`, {
        method: "PUT",
        body: JSON.stringify({ message, enabled }),
      }),
    broadcast: (segment: string) =>
      apiFetch<BroadcastResult>(`/api/v1/segments/${segment}/broadcast`, { method: "POST" }),
  },
  broadcasts: {
    history: async () => {
      const res = await apiFetch<{ data: BroadcastHistoryItem[] }>("/api/v1/upload/history");
      return res.data || [];
    },
  },
  reengagement: {
    listSteps: async (params?: { type?: string; broadcast_id?: string }) => {
      const qs = new URLSearchParams();
      if (params?.type) qs.set("type", params.type);
      if (params?.broadcast_id) qs.set("broadcast_id", params.broadcast_id);
      const res = await apiFetch<{ data: ReengagementStep[] }>(`/api/v1/reengagement/steps?${qs}`);
      return res.data || [];
    },
    createStep: (data: {
      type: "broadcast" | "inbound";
      broadcast_id?: string | null;
      delay_hours: number;
      target_segments: string[];
      target_sources?: string[] | null;
      message_type: "freeform" | "template";
      message_content?: string | null;
      template_name?: string | null;
      template_variables?: string[] | null;
      fallback_template_name?: string | null;
      fallback_template_variables?: string[] | null;
    }) =>
      apiFetch<ReengagementStep>(`/api/v1/reengagement/steps`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    deleteStep: (stepId: string) =>
      apiFetch<{ success: boolean }>(`/api/v1/reengagement/steps/${stepId}`, {
        method: "DELETE",
      }),
    getLogs: async (stepId?: string) => {
      const qs = stepId ? `?step_id=${stepId}` : "";
      const res = await apiFetch<{ data: ReengagementLog[] }>(`/api/v1/reengagement/logs${qs}`);
      return res.data || [];
    },
  },
  knowledge: {
    listDocuments: async () => {
      const res = await apiFetch<{ data: Array<{id:string;name:string;size_bytes:number;file_type:string;status:string;created_at:string;chunk_count?:number}> }>(`/api/v1/knowledge/documents`);
      return res.data || [];
    },
    uploadDocument: async (file: File, campaignTagId?: string | null) => {
      const authHeaders = await getAuthHeaders();
      const fd = new FormData();
      fd.append("file", file);
      if (campaignTagId) fd.append("campaign_tag_id", campaignTagId);
      const res = await fetch(`${API_URL}/api/v1/knowledge/upload-document`, {
        method: "POST",
        body: fd,
        headers: { ...authHeaders },
      });
      if (!res.ok) throw new Error("Upload failed");
      return res.json();
    },
    deleteDocument: (id: string) =>
      apiFetch<{ success: boolean }>(`/api/v1/knowledge/documents/${id}`, {
        method: "DELETE",
      }),
    listCampaignTags: async () => {
      const res = await apiFetch<{ data: Array<{ id: string; name: string; color?: string }> }>(`/api/v1/broadcast-tags/`);
      return res.data || [];
    },
  },
  catalog: {
    listItems: async (q?: string) => {
      const qs = q ? `?q=${encodeURIComponent(q)}` : "";
      const res = await apiFetch<{ data: CatalogItem[] }>(`/api/v1/catalog/items${qs}`);
      return res.data || [];
    },
    createItem: (data: { name: string; item_type: string; description?: string | null }) =>
      apiFetch<CatalogItem>(`/api/v1/catalog/items`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    updateItem: (
      id: string,
      data: Partial<Pick<CatalogItem, "name" | "item_type" | "description" | "status">>
    ) =>
      apiFetch<CatalogItem>(`/api/v1/catalog/items/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    deleteItem: (id: string) =>
      apiFetch<{ success: boolean }>(`/api/v1/catalog/items/${id}`, {
        method: "DELETE",
      }),
    uploadMedia: async (itemId: string, file: File): Promise<CatalogMedia> => {
      const authHeaders = await getAuthHeaders();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_URL}/api/v1/catalog/items/${itemId}/media`, {
        method: "POST",
        body: fd,
        headers: { ...authHeaders },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Media upload failed" }));
        throw new Error(err.detail || "Media upload failed");
      }
      return res.json();
    },
    listMedia: async () => {
      const res = await apiFetch<{ data: CatalogMedia[] }>(`/api/v1/catalog/media`);
      return res.data || [];
    },
    deleteMedia: (id: string) =>
      apiFetch<{ success: boolean }>(`/api/v1/catalog/media/${id}`, {
        method: "DELETE",
      }),
    getAiRules: () => apiFetch<CatalogAiRules>(`/api/v1/catalog/ai-rules`),
    updateAiRules: (data: Partial<CatalogAiRules>) =>
      apiFetch<CatalogAiRules>(`/api/v1/catalog/ai-rules`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
  },
  aiTune: {
    prompts: async () => {
      const res = await apiFetch<{ data: AIPrompt[] }>(`/api/v1/ai-tune/prompts`);
      return res.data || [];
    },
    updatePrompt: (name: string, content: string) =>
      apiFetch<AIPrompt>(`/api/v1/ai-tune/prompts/${name}`, {
        method: "PUT",
        body: JSON.stringify({ content }),
      }),
    analyze: (forPrompt = "whatsapp_reply") =>
      apiFetch<AnalyzeResult>(
        `/api/v1/ai-tune/analyze?for_prompt=${encodeURIComponent(forPrompt)}`,
        { method: "POST" },
      ),
    suggestions: async (status: "pending" | "applied" | "rejected" | "all" = "pending") => {
      const res = await apiFetch<{ data: TuneSuggestion[] }>(
        `/api/v1/ai-tune/suggestions?status=${status}`,
      );
      return res.data || [];
    },
    apply: (id: string) =>
      apiFetch<{ applied: boolean; for_prompt: string; new_length: number }>(
        `/api/v1/ai-tune/suggestions/${id}/apply`,
        { method: "POST" },
      ),
    reject: (id: string) =>
      apiFetch<{ rejected: boolean }>(`/api/v1/ai-tune/suggestions/${id}/reject`, {
        method: "POST",
      }),
  },
  system: {
    status: () => apiFetch<SystemStatus>(`/api/v1/system/status`),
  },
  analytics: {
    overview: () => apiFetch<AnalyticsOverview>(`/api/v1/analytics/overview`),
    adPerformance: () => apiFetch<AdPerformanceSummary>(`/api/v1/analytics/ad-performance`),
    whatsapp: () => apiFetch<WhatsAppAnalytics>(`/api/v1/analytics/whatsapp`),
    telecalling: () => apiFetch<TelecallingAnalytics>(`/api/v1/analytics/telecalling`),
    funnel: () => apiFetch<FunnelAnalytics>(`/api/v1/analytics/funnel`),
    overviewExtended: (range: "today" | "7d" | "30d" = "7d") =>
      apiFetch<AnalyticsOverviewExtended>(`/api/v1/analytics/overview?range=${range}`),
    messaging: (channel: string = "all", range: "today" | "7d" | "30d" = "7d") =>
      apiFetch<MessagingAnalytics>(`/api/v1/analytics/messaging?channel=${channel}&range=${range}`),
    telecallingExtended: (params?: { from?: string; to?: string }) => {
      const qs = new URLSearchParams();
      if (params?.from) qs.set("from", params.from);
      if (params?.to) qs.set("to", params.to);
      const s = qs.toString();
      return apiFetch<TelecallingAnalyticsExtended>(`/api/v1/analytics/telecalling${s ? `?${s}` : ""}`);
    },
    funnelExtended: () =>
      apiFetch<FunnelAnalyticsExtended>(`/api/v1/analytics/funnel`),
    templatePerformance: async () => {
      const res = await apiFetch<{ data: TemplatePerformanceRow[] }>(`/api/v1/analytics/template-performance`);
      return res.data || [];
    },
    inbound: (range: string) =>
      apiFetch<{
        kpis: {
          today: { total: number; organic: number; ad: number };
          range: { total: number; organic: number; ad: number };
        };
        daily: { day: string; organic: number; ad: number }[];
        by_segment: { A: number; B: number; C: number; D: number };
        by_channel: { whatsapp: number; instagram: number; facebook: number; telegram: number };
      }>(`/api/v1/analytics/inbound?range=${range}`),
    callerTimeline: (callerId: string, date: string) =>
      apiFetch<{ data: TimelineEvent[] }>(`/api/v1/analytics/caller-timeline?caller_id=${encodeURIComponent(callerId)}&date=${encodeURIComponent(date)}`),
    qaQueue: (limit: number) =>
      apiFetch<{ data: CallLog[] }>(`/api/v1/analytics/qa-queue?limit=${limit}`),
    exportTelecallingCsv: async (since?: string, until?: string) => {
      const headers = await getAuthHeaders();
      const qs = new URLSearchParams({ format: "csv" });
      if (since) qs.set("since", since);
      if (until) qs.set("until", until);
      const res = await fetch(`${API_URL}/api/v1/analytics/telecalling/export?${qs.toString()}`, { headers });
      if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "telecalling_performance.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    },
  },
  insights: {
    whatsapp: (params?: { range?: string; since?: string; until?: string; source?: string }) => {
      const qs = new URLSearchParams();
      if (params?.range) qs.set("range", params.range);
      if (params?.since) qs.set("since", params.since);
      if (params?.until) qs.set("until", params.until);
      if (params?.source) qs.set("source", params.source);
      const q = qs.toString();
      return apiFetch(`/api/v1/insights/whatsapp${q ? `?${q}` : ""}`);
    },
    sync: () => apiFetch(`/api/v1/insights/sync`, { method: "POST" }),
    trends: (range = "30d") => apiFetch(`/api/v1/insights/trends?range=${range}`),
  },
  followUps: {
    summary: () => apiFetch<FollowUpSummary>(`/api/v1/follow-ups/summary`),
    run: (limit = 20) =>
      apiFetch<FollowUpRunResult>(`/api/v1/follow-ups/run?limit=${limit}`, {
        method: "POST",
      }),
    rescheduleCallback: (jobId: string, scheduledFor: string) =>
      apiFetch<{ success: boolean; data: unknown }>(`/api/v1/follow-ups/callback/${jobId}/reschedule`, {
        method: "PATCH",
        body: JSON.stringify({ scheduled_for: scheduledFor }),
      }),
    callbacksBoard: () =>
      apiFetch<{ data: CallbackBoardItem[] }>(`/api/v1/follow-ups/callbacks/board`),
  },
  settings: {
    getTelecallingConfig: () =>
      apiFetch<TelecallingConfig>(`/api/v1/settings/telecalling-config`),
  },
  upload: {
    leads: async (
      file: File,
      options?: {
        campaignMessage?: string;
        segmentOverride?: string;
        platform?: string;
        campaignName?: string;
        externalCampaignId?: string;
        adSetName?: string;
        externalAdSetId?: string;
        adName?: string;
        externalAdId?: string;
        utmSource?: string;
        utmCampaign?: string;
        utmContent?: string;
        spendInr?: string;
      },
    ) => {
      const fd = new FormData();
      fd.append("file", file);
      if (options?.campaignMessage) fd.append("campaign_message", options.campaignMessage);
      if (options?.segmentOverride) fd.append("segment_override", options.segmentOverride);
      if (options?.platform) fd.append("platform", options.platform);
      if (options?.campaignName) fd.append("campaign_name", options.campaignName);
      if (options?.externalCampaignId) fd.append("external_campaign_id", options.externalCampaignId);
      if (options?.adSetName) fd.append("ad_set_name", options.adSetName);
      if (options?.externalAdSetId) fd.append("external_ad_set_id", options.externalAdSetId);
      if (options?.adName) fd.append("ad_name", options.adName);
      if (options?.externalAdId) fd.append("external_ad_id", options.externalAdId);
      if (options?.utmSource) fd.append("utm_source", options.utmSource);
      if (options?.utmCampaign) fd.append("utm_campaign", options.utmCampaign);
      if (options?.utmContent) fd.append("utm_content", options.utmContent);
      if (options?.spendInr) fd.append("spend_inr", options.spendInr);
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/upload/leads`, { method: "POST", body: fd, headers: { ...authHeaders } });
      if (!res.ok) throw new Error(`Upload failed ${res.status}: ${await res.text()}`);
      return res.json() as Promise<{
        total: number;
        inserted: number;
        skipped: number;
        attributed: number;
        campaign_sent: number;
        campaign_failed: number;
      }>;
    },
  },
  onboarding: {
    status: () =>
      apiFetch<{ has_tenant: boolean; tenant_id?: string; role?: string }>("/api/v1/onboarding/status"),
    create: (name: string) =>
      apiFetch<{ tenant_id: string; already_exists: boolean }>("/api/v1/onboarding/", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
  },
  operator: {
    getCallingProvider: (tenantId: string) =>
      apiFetch<{ tenant_id: string; calling_provider: "telecmi" | "sim_basic"; telecalling_enabled: boolean }>(
        `/api/v1/operator/clients/${tenantId}/calling-provider`
      ),
    updateCallingProvider: (tenantId: string, callingProvider: "telecmi" | "sim_basic") =>
      apiFetch<{ tenant_id: string; calling_provider: "telecmi" | "sim_basic" }>(
        `/api/v1/operator/clients/${tenantId}/calling-provider`,
        {
          method: "PATCH",
          body: JSON.stringify({ calling_provider: callingProvider }),
        }
      ),
  },
  team: {
    me: () => apiFetch<MyProfile>("/api/v1/team/me"),
    list: () => apiFetch<{ data: TeamMember[]; calling_provider?: "telecmi" | "sim_basic" }>("/api/v1/team/"),
    invite: (email: string, password: string, name?: string, phone?: string, telecmiAgentId?: string, telecmiAgentPassword?: string) =>
      apiFetch<{ invited: boolean; email: string; user_id: string }>("/api/v1/team/invite", {
        method: "POST",
        body: JSON.stringify({ email, password, name, phone, telecmi_agent_id: telecmiAgentId, telecmi_agent_password: telecmiAgentPassword }),
      }),
    remove: (userId: string) =>
      apiFetch<{ removed: boolean }>(`/api/v1/team/${userId}`, { method: "DELETE" }),
    attendanceGrid: (params?: { month?: string; from?: string; to?: string }) => {
      const qs = new URLSearchParams();
      if (params?.month) qs.set("month", params.month);
      if (params?.from) qs.set("from", params.from);
      if (params?.to) qs.set("to", params.to);
      const s = qs.toString();
      return apiFetch<{ data: TeamAttendanceGridData }>(`/api/v1/team/attendance${s ? `?${s}` : ""}`);
    },
    attendanceForCaller: (callerId: string, months: number = 4) =>
      apiFetch<{ data: CallerAttendance }>(`/api/v1/team/attendance/${callerId}?months=${months}`),
    markAttendance: (callerId: string, date: string, status: "present" | "absent") =>
      apiFetch<{ data: AttendanceDay }>(`/api/v1/team/attendance/${callerId}`, {
        method: "POST",
        body: JSON.stringify({ date, status }),
      }),
    markHoliday: (date: string) =>
      apiFetch<{ data: { date: string; status: string; caller_count: number } }>("/api/v1/team/attendance/holiday", {
        method: "POST",
        body: JSON.stringify({ date }),
      }),
  },
  rbac: {
    permissions: () =>
      apiFetch<{ data: PermissionDef[] }>("/api/v1/rbac/permissions"),
    roles: () =>
      apiFetch<{ data: ClientRole[]; permissions: PermissionDef[] }>("/api/v1/rbac/roles"),
    createRole: (data: { name: string; permissions: string[] }) =>
      apiFetch<ClientRole>("/api/v1/rbac/roles", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    updateRole: (id: string, data: { name: string; permissions: string[] }) =>
      apiFetch<ClientRole>(`/api/v1/rbac/roles/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    deleteRole: (id: string) =>
      apiFetch<{ deleted: boolean }>(`/api/v1/rbac/roles/${id}`, {
        method: "DELETE",
      }),
    users: () =>
      apiFetch<{ data: RbacUser[] }>("/api/v1/rbac/users"),
    createUser: (data: {
      full_name: string;
      email: string;
      role_id: string;
      temporary_password: string;
      phone?: string | null;
      telecmi_agent_id?: string | null;
      telecmi_agent_password?: string | null;
    }) =>
      apiFetch<{ created: boolean; user_id: string; temporary_password: string }>("/api/v1/rbac/users", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    updateUser: (userId: string, data: {
      full_name?: string;
      role_id?: string;
      phone?: string | null;
      telecmi_agent_id?: string | null;
      telecmi_agent_password?: string | null;
    }) =>
      apiFetch<{ updated: boolean }>(`/api/v1/rbac/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    deleteUser: (userId: string) =>
      apiFetch<{ deleted: boolean }>(`/api/v1/rbac/users/${userId}`, {
        method: "DELETE",
      }),
    resetPassword: (userId: string) =>
      apiFetch<{ temporary_password: string }>(`/api/v1/rbac/users/${userId}/reset-password`, {
        method: "POST",
      }),
    markPasswordResetComplete: () =>
      apiFetch<{ updated: boolean }>("/api/v1/rbac/password-reset-complete", {
        method: "POST",
      }),
  },
  todos: {
    list: async (params?: { start_date?: string; end_date?: string }) => {
      const qs = new URLSearchParams();
      if (params?.start_date) qs.set("start_date", params.start_date);
      if (params?.end_date) qs.set("end_date", params.end_date);
      return apiFetch<Todo[]>(`/api/v1/todos/?${qs}`);
    },
    create: (data: { todo_date: string; content: string }) =>
      apiFetch<Todo>(`/api/v1/todos/`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      apiFetch<{ success: boolean }>(`/api/v1/todos/${id}`, {
        method: "DELETE",
      }),
    update: (id: string, data: { is_completed?: boolean; content?: string }) =>
      apiFetch<Todo>(`/api/v1/todos/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
  },
  inboundLeads: {
    campaigns: async () => {
      const res = await apiFetch<{ data: { id: string; campaign_name: string; platform: string }[] }>(`/api/v1/inbound-leads/campaigns`);
      return res.data || [];
    },
    googleLink: async (campaign: string, gclid?: string) => {
      const qs = new URLSearchParams({ campaign });
      if (gclid) qs.set("gclid", gclid);
      return apiFetch<{ link: string; campaign_slug: string; whatsapp_number: string }>(
        `/api/v1/inbound-leads/google-link?${qs}`
      );
    },
    list: async (params?: {
      origin?: string;
      segment?: string;
      ad_campaign_id?: string;
      source?: string;
      date_from?: string;
      date_to?: string;
      page?: number;
      limit?: number;
    }) => {
      const qs = new URLSearchParams();
      if (params?.origin) qs.set("origin", params.origin);
      if (params?.segment) qs.set("segment", params.segment);
      if (params?.ad_campaign_id) qs.set("ad_campaign_id", params.ad_campaign_id);
      if (params?.source) qs.set("source", params.source);
      if (params?.date_from) qs.set("date_from", params.date_from);
      if (params?.date_to) qs.set("date_to", params.date_to);
      if (params?.page) qs.set("page", String(params.page));
      if (params?.limit) qs.set("limit", String(params.limit));
      return apiFetch<{ data: InboundLead[]; total: number; page: number; limit: number }>(`/api/v1/inbound-leads/?${qs}`);
    },
    exportCsv: async (params?: {
      origin?: string;
      segment?: string;
      ad_campaign_id?: string;
      source?: string;
      date_from?: string;
      date_to?: string;
    }) => {
      const qs = new URLSearchParams();
      if (params?.origin) qs.set("origin", params.origin);
      if (params?.segment) qs.set("segment", params.segment);
      if (params?.ad_campaign_id) qs.set("ad_campaign_id", params.ad_campaign_id);
      if (params?.source) qs.set("source", params.source);
      if (params?.date_from) qs.set("date_from", params.date_from);
      if (params?.date_to) qs.set("date_to", params.date_to);
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/inbound-leads/export?${qs}`, { headers });
      if (!res.ok) throw new Error(`Export failed: ${res.status}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "inbound_leads.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    },
  },
  templates: {
    list: async () => {
      const res = await apiFetch<{ data: WabaTemplate[] }>("/api/v1/templates/");
      return res.data || [];
    },
  },
  notifications: {
    list: () => apiFetch<{ data: AppNotification[] }>("/api/v1/notifications"),
    pool: () => apiFetch<{ data: PoolItem[] }>("/api/v1/notifications/pool"),
    markRead: (id: string) =>
      apiFetch<{ success: boolean; data: AppNotification }>(`/api/v1/notifications/${id}/read`, {
        method: "PATCH",
      }),
    markAllRead: () =>
      apiFetch<{ success: boolean }>("/api/v1/notifications/read", {
        method: "PATCH",
      }),
    getConfig: () => apiFetch<NotificationConfig>("/api/v1/notifications/config"),
    saveConfig: (config: NotificationConfig) =>
      apiFetch<NotificationConfig>("/api/v1/notifications/config", {
        method: "PUT",
        body: JSON.stringify(config),
      }),
  },
  push: {
    publicKey: () => apiFetch<{ public_key: string | null }>("/api/v1/push/public-key"),
    status: () => apiFetch<{ supported_by_server: boolean; public_key_configured: boolean; private_key_configured: boolean; subscription_count: number }>("/api/v1/push/status"),
    saveSubscription: (subscription: PushSubscriptionJSON) =>
      apiFetch<{ saved: boolean }>("/api/v1/push/subscriptions", {
        method: "POST",
        body: JSON.stringify(subscription),
      }),
    deleteSubscription: (endpoint: string) =>
      apiFetch<{ deleted: boolean }>(`/api/v1/push/subscriptions?endpoint=${encodeURIComponent(endpoint)}`, {
        method: "DELETE",
      }),
  },
  chatHandovers: {
    assign: (handoverId: string, callerId: string) =>
      apiFetch<{ assigned: boolean }>(`/api/v1/chat-handovers/${handoverId}/assign`, {
        method: "PATCH",
        body: JSON.stringify({ caller_id: callerId }),
      }),
  },
};

export interface Todo {
  id: string;
  todo_date: string;
  content: string;
  is_completed: boolean;
  created_at: string;
  updated_at: string;
}

export interface InboundLead {
  id: string;
  phone: string;
  name: string;
  source: string;
  origin: string;
  channel_label: string;
  score: number;
  segment: string;
  segment_label: string;
  created_at: string;
  ad_campaign_id: string | null;
  campaign_name: string;
  campaign_platform: string;
  keyword: string;
}

export { API_URL };
