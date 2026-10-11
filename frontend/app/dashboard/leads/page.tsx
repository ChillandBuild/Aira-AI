import { LeadsClient } from "./LeadsClient";

const SEGMENTS = ["A", "B", "C", "D"] as const;
type Segment = (typeof SEGMENTS)[number];

function isSegment(value: string | string[] | undefined): value is Segment {
  return typeof value === "string" && (SEGMENTS as readonly string[]).includes(value);
}

// No server-side lead fetch: the page loads its leads and counts in the browser
// (paged, 25 at a time). Fetching here only delayed the first paint.
export default function LeadsPage({
  searchParams,
}: {
  searchParams: { segment?: string | string[] };
}) {
  const requestedSegment = searchParams?.segment;
  const initialTab: Segment = isSegment(requestedSegment) ? requestedSegment : "A";
  return <LeadsClient initialTab={initialTab} />;
}
