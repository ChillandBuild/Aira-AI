export interface OverviewData {
  tenant: { id: string; name: string; status: string; enabled_features: string[]; created_at: string };
  owner: { user_id: string | null; email: string | null };
  stats: { total_leads: number; active_leads: number; messages_sent_30d: number; messages_received_30d: number; team_members: number; last_activity: string | null };
}
