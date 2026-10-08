const TAGS: Record<string, { label: string; cls: string }> = {
  MARKETING: { label: "Marketing", cls: "border-amber-200 bg-amber-50 text-amber-800" },
  UTILITY: { label: "Utility", cls: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  AUTHENTICATION: { label: "Authentication", cls: "border-border bg-white text-ink-secondary" },
};

/** Marketing / Utility pill for a template. Always text, so colour is never the only signal. */
export function CategoryTag({ category }: { category: string | null | undefined }) {
  const tag = category ? TAGS[category.toUpperCase()] : undefined;
  if (!tag) return null;
  return (
    <span className={`shrink-0 rounded-full border px-2 py-0.5 font-label text-[10px] font-bold ${tag.cls}`}>
      {tag.label}
    </span>
  );
}
