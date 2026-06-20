export function SkeletonCard() {
  return (
    <div className="bg-white rounded-card border border-border p-5 shadow-sm animate-pulse">
      <div className="h-3 bg-surface-mid rounded w-24 mb-3" />
      <div className="h-7 bg-surface-mid rounded w-16" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="bg-white rounded-card border border-border overflow-hidden animate-pulse">
      <div className="px-5 py-3 border-b border-border-subtle">
        <div className="h-4 bg-surface-mid rounded w-32" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="px-5 py-3 border-b border-border-subtle last:border-0 flex gap-4">
          <div className="h-3 bg-surface-mid rounded w-28" />
          <div className="h-3 bg-surface-mid rounded w-20" />
          <div className="h-3 bg-surface-mid rounded w-16" />
        </div>
      ))}
    </div>
  );
}
