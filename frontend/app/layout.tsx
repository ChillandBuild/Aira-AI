import type { Metadata, Viewport } from "next";
import { Manrope, JetBrains_Mono, Dancing_Script } from "next/font/google";
import { SpeedInsights } from "@vercel/speed-insights/next";
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
  manifest: "/manifest.webmanifest",
  applicationName: "Aira AI",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Aira AI",
  },
  formatDetection: {
    telephone: false,
  },
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/icons/aira-icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/icons/aira-icon-192.png", sizes: "192x192", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#5b21b6",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${manrope.variable} ${jetbrainsMono.variable} ${dancingScript.variable}`}>
      <body className="antialiased">
        {children}
        <Toaster position="top-right" richColors closeButton />
        <SpeedInsights />
        <PwaRegistrar />
      </body>
    </html>
  );
}
