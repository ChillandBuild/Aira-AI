import { createClient } from "@/lib/supabase/server";
import { serverFetchJson } from "@/lib/serverApi";
import type { Lead } from "@/lib/api";
import { LeadsClient } from "./LeadsClient";

const SEGMENTS = ["A", "B", "C", "D"] as const;
type Segment = (typeof SEGMENTS)[number];

function isSegment(value: string | string[] | undefined): value is Segment {
  return typeof value === "string" && (SEGMENTS as readonly string[]).includes(value);
}

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function LeadsPage({
  searchParams,
}: {
  searchParams: { segment?: string | string[]; date_from?: string | string[]; date_to?: string | string[] };
}) {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;

  const dateFrom = firstParam(searchParams?.date_from);
  const dateTo = firstParam(searchParams?.date_to);
  const dateQuery = dateFrom && dateTo ? `&date_from=${dateFrom}&date_to=${dateTo}` : "";

  const requestedSegment = searchParams?.segment;
  let initialTab: Segment;
  if (isSegment(requestedSegment)) {
    initialTab = requestedSegment;
  } else {
    // Land on the first segment that actually has leads, so an admin with no
    // telecaller doesn't open onto an empty "Hot" tab while every lead sits in
    // Cold. Counts are cheap (limit=1 → reads only the total) and run in parallel.
    const counts = await Promise.all(
      SEGMENTS.map((seg) =>
        serverFetchJson<{ total: number }>(`/api/v1/leads/?segment=${seg}&limit=1${dateQuery}`, token)
          .then((r) => r?.total ?? 0)
          .catch(() => 0),
      ),
    );
    initialTab = SEGMENTS.find((_, i) => counts[i] > 0) ?? "A";
  }

  const seed = await serverFetchJson<{ data: Lead[] }>(
    `/api/v1/leads/?segment=${initialTab}&limit=200${dateQuery}`,
    token,
  );

  return <LeadsClient initialTab={initialTab} fallbackLeads={seed?.data ?? null} />;
}
