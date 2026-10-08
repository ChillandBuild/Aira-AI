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
 * 800 = Anril teal #038285; 950 is deliberately navy #0A1528 (dark sections).
 */
export const PRIMARY = {
  50: "#effbfb",
  100: "#d5f4f4",
  200: "#ade9ea",
  300: "#78d6d8",
  400: "#3fbcbf",
  500: "#1aa3a6",
  600: "#0b9396",
  700: "#068a8d",
  800: "#038285",
  900: "#04585b",
  950: "#0A1528",
} as const;

/** Same scale as `PRIMARY`, as "r, g, b" triplets for canvas rgba() strings. */
export const PRIMARY_RGB = {
  50: "239, 251, 251",
  100: "213, 244, 244",
  200: "173, 233, 234",
  300: "120, 214, 216",
  400: "63, 188, 191",
  500: "26, 163, 166",
  600: "11, 147, 150",
  700: "6, 138, 141",
  800: "3, 130, 133",
  900: "4, 88, 91",
  950: "10, 21, 40",
} as const;
