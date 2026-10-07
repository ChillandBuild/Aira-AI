export interface OverviewData {
  tenant: { id: string; name: string; status: string; enabled_features: string[]; created_at: string };
  owner: { user_id: string | null; email: string | null };
  stats: { total_leads: number; active_leads: number; messages_sent_30d: number; messages_received_30d: number; team_members: number; last_activity: string | null };
}

export type PrivateSendReplyMode = "client" | "aira";

export interface PrivateSendKey {
  id: string;
  key_prefix: string;
  status: "active" | "revoked";
  created_at: string;
  last_seen_at: string | null;
  plugin_version: string | null;
  revoked_at: string | null;
}

export interface PrivateSendUsageDay {
  day: string;
  reported_sent: number;
  /** null until Meta has counted that day (the nightly job runs for yesterday). */
  meta_volume: number | null;
}

export interface PrivateSendUsage {
  period: string;
  reported_sent: number;
  meta_volume: number;
  mismatch: boolean;
  days: PrivateSendUsageDay[];
}

export interface PrivateSendOverview {
  enabled: boolean;
  monthly_cap: number | null;
  reply_mode: PrivateSendReplyMode;
  offline_grace_hours: number;
  keys: PrivateSendKey[];
  usage: PrivateSendUsage;
}

export interface PrivateSendNewKey {
  id: string;
  /** Full key. Returned once, never again. */
  key: string;
  key_prefix: string;
}

export interface PrivateSendSettingsPatch {
  reply_mode?: PrivateSendReplyMode;
  offline_grace_hours?: number;
  monthly_cap?: number | null;
}
