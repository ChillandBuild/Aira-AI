import { IntakeSession } from "@/lib/api";

export interface FieldColumn {
  key: string;
  label: string;
}

function prettify(key: string): string {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Union of every field key present across the given rows, first-seen order.
 * A key's label comes from the most recent row whose snapshot defines it, so a
 * renamed field reads under its current name while a deleted one keeps the name
 * it was collected under. Mirrors backend build_csv_headers — the two must agree
 * or the export and the screen disagree about what a column means.
 */
export function deriveColumns(rows: IntakeSession[]): FieldColumn[] {
  const order: string[] = [];
  const labels = new Map<string, string>();
  const labelDate = new Map<string, string>();

  const sorted = [...rows].sort((a, b) => a.created_at.localeCompare(b.created_at));

  for (const row of sorted) {
    const schema = new Map((row.field_schema ?? []).map((f) => [f.key, f.label]));
    for (const key of Object.keys(row.collected_data ?? {})) {
      if (!order.includes(key)) order.push(key);
      const snapshotLabel = schema.get(key);
      if (snapshotLabel && row.created_at >= (labelDate.get(key) ?? "")) {
        labels.set(key, snapshotLabel);
        labelDate.set(key, row.created_at);
      }
    }
  }

  const resolved = order.map((key) => ({ key, label: labels.get(key) ?? prettify(key) }));
  const counts = new Map<string, number>();
  for (const { label } of resolved) counts.set(label, (counts.get(label) ?? 0) + 1);

  return resolved.map(({ key, label }) => ({
    key,
    label: (counts.get(label) ?? 0) > 1 ? `${label} (${key})` : label,
  }));
}
