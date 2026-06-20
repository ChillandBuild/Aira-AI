export function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-card border border-border p-5 shadow-sm">
      <div className="flex items-center gap-2 text-ink-muted mb-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wider font-label">{label}</span>
      </div>
      <p className="text-2xl font-bold text-ink">{typeof value === "number" ? value.toLocaleString() : value}</p>
    </div>
  );
}
