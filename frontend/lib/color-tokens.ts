/**
 * Brand primary colour scale, mirrored from tailwind.config.ts
 * (theme.colors.primary) and app/globals.css (--primary-*).
 *
 * Canvas 2D contexts (fillStyle, gradient stops) can't resolve CSS custom
 * properties, so code drawing to a <canvas> imports these constants
 * instead of a var(--primary-NNN) string. Everywhere else — DOM, SVG,
 * inline style objects — use the CSS variables directly.
 *
 * Keep these three definitions in sync if the brand colour changes.
 */
export const PRIMARY = {
  50: "#f5f3ff",
  100: "#ede9fe",
  200: "#ddd6fe",
  300: "#c4b5fd",
  400: "#a78bfa",
  500: "#8b5cf6",
  600: "#7c3aed",
  700: "#6d28d9",
  800: "#5b21b6",
  900: "#4c1d95",
  950: "#2e1065",
} as const;

/** Same scale as `PRIMARY`, as "r, g, b" triplets for canvas rgba() strings. */
export const PRIMARY_RGB = {
  50: "245, 243, 255",
  100: "237, 233, 254",
  200: "221, 214, 254",
  300: "196, 181, 253",
  400: "167, 139, 250",
  500: "139, 92, 246",
  600: "124, 58, 237",
  700: "109, 40, 217",
  800: "91, 33, 182",
  900: "76, 29, 149",
  950: "46, 16, 101",
} as const;
