import { SVGProps } from "react";

// "anril AI" wordmark: Manrope ExtraBold (800) glyphs converted to paths, so it
// renders identically everywhere without loading the font.
// Letters follow currentColor (navy via text-ink, white via text-white); the
// i's dot and "AI" are the teal accent. On navy, pass tone="dark" so the accent
// switches to the light teal (#038285 on navy is only ~3.9:1).
const VIEW_BOX = { x: 80, y: -1470, width: 6264, height: 1500 };
const ASPECT = VIEW_BOX.width / VIEW_BOX.height;
const ACCENT_ON_LIGHT = "var(--primary-800)";
const ACCENT_ON_DARK = "#3fbcbf";

const LETTERS =
  "M440 30Q324 30 243.5 -14.5Q163 -59 121.5 -133.5Q80 -208 80 -298Q80 -373 103.0 -435.0Q126 -497 177.5 -544.5Q229 -592 316 -624Q376 -646 459.0 -663.0Q542 -680 647.0 -695.5Q752 -711 878 -730L780 -676Q780 -772 734.0 -817.0Q688 -862 580 -862Q520 -862 455.0 -833.0Q390 -804 364 -730L118 -808Q159 -942 272.0 -1026.0Q385 -1110 580 -1110Q723 -1110 834.0 -1066.0Q945 -1022 1002 -914Q1034 -854 1040.0 -794.0Q1046 -734 1046 -660V0H808V-222L842 -176Q763 -67 671.5 -18.5Q580 30 440 30ZM498 -184Q573 -184 624.5 -210.5Q676 -237 706.5 -271.0Q737 -305 748 -328Q769 -372 772.5 -430.5Q776 -489 776 -528L856 -508Q735 -488 660.0 -474.5Q585 -461 539.0 -450.0Q493 -439 458 -426Q418 -410 393.5 -391.5Q369 -373 357.5 -351.0Q346 -329 346 -302Q346 -265 364.5 -238.5Q383 -212 417.0 -198.0Q451 -184 498 -184Z M2022 0V-510Q2022 -547 2018.0 -604.5Q2014 -662 1993.0 -720.0Q1972 -778 1924.5 -817.0Q1877 -856 1790 -856Q1755 -856 1715.0 -845.0Q1675 -834 1640.0 -802.5Q1605 -771 1582.5 -710.0Q1560 -649 1560 -548L1404 -622Q1404 -750 1456.0 -862.0Q1508 -974 1612.5 -1043.0Q1717 -1112 1876 -1112Q2003 -1112 2083.0 -1069.0Q2163 -1026 2207.5 -960.0Q2252 -894 2271.0 -822.5Q2290 -751 2294.0 -692.0Q2298 -633 2298 -606V0ZM1284 0V-1080H1526V-722H1560V0Z M2538 0V-1080H2778V-816L2752 -850Q2773 -906 2808.0 -952.0Q2843 -998 2894 -1028Q2933 -1052 2979.0 -1065.5Q3025 -1079 3074.0 -1082.5Q3123 -1086 3172 -1080V-826Q3127 -840 3067.5 -835.5Q3008 -831 2960 -808Q2912 -786 2879.0 -749.5Q2846 -713 2829.0 -663.5Q2812 -614 2812 -552V0Z M3362 0V-1080H3634V0Z M3934 0V-1470H4206V0Z";
const I_DOT = "M3362 -1230V-1470H3634V-1230Z";
const AI =
  "M4606.0 0 5046.0 -1440H5452.0L5892.0 0H5612.0L5220.0 -1270H5272.0L4886.0 0ZM4870.0 -300V-554H5630.0V-300Z M6072.0 0V-1440H6344.0V0Z";

type AnrilLogoProps = SVGProps<SVGSVGElement> & {
  /** "dark" when the logo sits on navy: uses the light teal accent. */
  tone?: "light" | "dark";
};

export function AnrilLogo({ width, height = 36, tone = "light", ...rest }: AnrilLogoProps) {
  const calculatedWidth = width ?? (typeof height === "number" ? Math.round(height * ASPECT) : undefined);
  const accent = tone === "dark" ? ACCENT_ON_DARK : ACCENT_ON_LIGHT;

  return (
    <svg
      width={calculatedWidth}
      height={height}
      viewBox={`${VIEW_BOX.x} ${VIEW_BOX.y} ${VIEW_BOX.width} ${VIEW_BOX.height}`}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Anril AI"
      {...rest}
    >
      <path d={LETTERS} fill="currentColor" />
      <path d={I_DOT} fill={accent} />
      <path d={AI} fill={accent} />
    </svg>
  );
}
