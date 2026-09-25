"use client";

export function InsightsTab() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {[
        ["Views", "Coming soon"],
        ["Sent images", "Coming soon"],
        ["Most requested", "Coming soon"],
      ].map(([label, value]) => (
        <div key={label} className="rounded-card border border-border bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase text-ink-muted">{label}</p>
          <p className="mt-3 font-display text-2xl font-bold text-ink">{value}</p>
        </div>
      ))}
    </div>
  );
}
