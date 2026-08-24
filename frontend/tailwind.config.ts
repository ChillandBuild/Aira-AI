import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#faf8f5",
        surface: "#ffffff",
        "surface-mid": "#f0ece4",
        "surface-low": "#faf8f5",
        "surface-subtle": "#faf8f5",

        primary: "#5b21b6",
        "primary-dark": "#4c1d95",
        "primary-light": "#f5f3ff",
        "primary-muted": "#ede9fe",

        ink: "#1c1917",
        "ink-secondary": "#78716c",
        "ink-muted": "#a8a29e",

        border: "#e8e3db",
        "border-subtle": "#f0ece4",

        success: "#059669",
        warning: "#d97706",
        danger: "#e11d48",

        secondary: "#1c1917",
        "secondary-light": "#78716c",
        "secondary-bg": "#f0ece4",
        "secondary-text": "#1c1917",
        tertiary: "#292524",
        "on-surface": "#1c1917",
        "on-surface-muted": "#a8a29e",

        "segment-a-bg": "#ecfdf5",
        "segment-a-text": "#059669",
        "segment-a-border": "#bbf7d0",
        "segment-b-bg": "#fffbeb",
        "segment-b-text": "#d97706",
        "segment-b-border": "#fde68a",
        "segment-c-bg": "#f8fafc",
        "segment-c-text": "#64748b",
        "segment-c-border": "#e2e8f0",
        "segment-d-bg": "#fff1f2",
        "segment-d-text": "#e11d48",
        "segment-d-border": "#fecdd3",
      },
      fontFamily: {
        display: ["var(--font-manrope)", "sans-serif"],
        body: ["var(--font-manrope)", "sans-serif"],
        label: ["var(--font-manrope)", "sans-serif"],
        // Opt-in display face (Archivo). See app/layout.tsx for why this is a
        // separate role rather than a repoint of `display`.
        heading: ["var(--font-heading)", "var(--font-manrope)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      boxShadow: {
        card: "0 2px 16px -2px rgba(28,25,23,.07), 0 1px 4px -1px rgba(28,25,23,.04)",
        "card-hover": "0 8px 28px -4px rgba(28,25,23,.12), 0 3px 8px -2px rgba(28,25,23,.05)",
        sidebar: "0 4px 30px rgba(28,25,23,.03)",
        sm: "0 1px 2px rgba(28,25,23,.04)",
      },
      borderRadius: {
        card: "1.25rem",
        xl: "0.875rem",
        "2xl": "1.125rem",
        "3xl": "1.25rem",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #2e1065 0%, #5b21b6 100%)",
        "warm-base": "linear-gradient(180deg, #faf8f5 0%, #f0ece4 100%)",
      },
    },
  },
  plugins: [],
};
export default config;
