import type { Metadata, Viewport } from "next";
import { Manrope, JetBrains_Mono, Dancing_Script, Instrument_Sans } from "next/font/google";
import { Toaster } from "sonner";
import { PwaRegistrar } from "@/components/PwaRegistrar";
import "./globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-manrope",
  display: "swap",
  weight: ["300", "400", "500", "600", "700", "800"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

// Display face for headings and KPI figures. Deliberately NOT wired to the
// shared `font-display` role -- that alias points at Manrope and is used in 76
// component files, so repointing it would restyle most of the app. Opt in per
// page with `font-heading`.
const instrumentSans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-heading",
  display: "swap",
});

const dancingScript = Dancing_Script({
  subsets: ["latin"],
  variable: "--font-script",
  display: "swap",
  weight: ["700"],
});

export const metadata: Metadata = {
  title: {
    default: "Aira AI - Lead Intelligence",
    template: "%s | Aira AI",
  },
  description: "WhatsApp lead management for education consultancies",
  applicationName: "Aira AI",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Aira AI",
  },
  formatDetection: {
    telephone: false,
  },
  other: {
    "mobile-web-app-capable": "yes",
  },
  icons: {
    icon: [
      { url: "/aira/favicon.ico" },
      { url: "/aira/icons/aira-icon.svg", type: "image/svg+xml" },
      { url: "/aira/icons/aira-icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/aira/icons/aira-icon-192.png", sizes: "192x192", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#5b21b6",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${manrope.variable} ${jetbrainsMono.variable} ${instrumentSans.variable} ${dancingScript.variable}`}>
      <head>
        <link rel="manifest" href="/aira/manifest.webmanifest" crossOrigin="use-credentials" />
      </head>
      <body className="antialiased">
        {children}
        <Toaster position="top-right" richColors closeButton />
        <PwaRegistrar />
      </body>
    </html>
  );
}
