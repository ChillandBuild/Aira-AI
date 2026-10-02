import { createClient } from "@/lib/supabase/server";
import { serverFetchJson } from "@/lib/serverApi";
import { NotesGate } from "./NotesGate";
import type { Lead } from "@/lib/api";

interface LeadsWithActivityResponse {
  data: Lead[];
}

export default async function NotesPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;

  const seed = await serverFetchJson<LeadsWithActivityResponse>(
    "/api/v1/lead-notes/leads-with-activity",
    token,
  );

  return <NotesGate fallbackLeads={seed} />;
}
