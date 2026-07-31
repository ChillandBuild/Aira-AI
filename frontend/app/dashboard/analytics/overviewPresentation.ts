type Summary = Record<string, number>;

export type FunnelStep = {
  label: string;
  count: number;
};

function count(summary: Summary, key: string): number {
  return Number(summary[key] ?? 0);
}

export function buildFunnel(summary: Summary): FunnelStep[] {
  const newLeads = count(summary, "new_leads");
  return [
    { label: "New leads", count: newLeads },
    { label: "Hot", count: count(summary, "hot") },
    { label: "Converted", count: count(summary, "converted") },
  ];
}
