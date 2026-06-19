export function AiraLogo({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="36" height="36" rx="7" fill="#1c1917" />
      <rect x="6" y="6" width="11" height="11" rx="1.5" fill="rgba(255,255,255,.88)" />
      <rect x="19" y="6" width="11" height="11" rx="1.5" fill="rgba(255,255,255,.28)" />
      <rect x="6" y="19" width="11" height="11" rx="1.5" fill="rgba(255,255,255,.28)" />
      <rect x="19" y="19" width="11" height="11" rx="1.5" fill="rgba(255,255,255,.10)" />
    </svg>
  );
}
