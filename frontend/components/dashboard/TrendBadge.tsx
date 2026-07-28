interface TrendBadgeProps {
  pct: number | null;
  label: string;
}

export function TrendBadge({ pct, label }: TrendBadgeProps) {
  if (pct === null) return null;

  const badgeClass = pct > 0 ? "badge-green" : pct < 0 ? "badge-red" : "badge-gray";
  const arrow = pct > 0 ? "↑" : pct < 0 ? "↓" : "→";

  return (
    <div className="mt-8 flex items-center">
      <span className={`badge ${badgeClass} font-semibold`}>
        {arrow} {Math.abs(pct)}%
      </span>
      <span className="text-xs text-ink-muted ml-2 font-medium">{label}</span>
    </div>
  );
}
