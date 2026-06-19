"use client";

/**
 * A single meandering river that runs the full height of the page, behind the
 * content and above the background orbs. Scrolling it feels like heading
 * downstream. The path is drawn in a 0..100 x 0..1000 space and stretched
 * vertically (preserveAspectRatio="none"), so it adapts to any page height.
 *
 * Motion lives entirely in CSS (.river-thread-*) so reduced-motion can freeze
 * the current without touching this markup. Purely decorative.
 */
export default function RiverThread() {
  // Gentle S-curves down the center; amplitude kept small so it never
  // collides with content columns.
  const path =
    "M50 0 C 70 80, 30 150, 50 230 S 78 360, 50 450 S 22 600, 50 700 S 80 850, 50 1000";

  return (
    <div className="river-thread" aria-hidden="true">
      <svg
        viewBox="0 0 100 1000"
        preserveAspectRatio="none"
        className="river-thread-svg"
        fill="none"
      >
        <defs>
          <linearGradient id="river-base" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5b21b6" stopOpacity="0.05" />
            <stop offset="50%" stopColor="#7c3aed" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#5b21b6" stopOpacity="0.05" />
          </linearGradient>
        </defs>

        {/* Soft riverbed */}
        <path d={path} className="river-thread-bed" stroke="url(#river-base)" />
        {/* Flowing light that drifts downstream */}
        <path d={path} className="river-thread-current" stroke="#7c3aed" />
      </svg>
    </div>
  );
}
