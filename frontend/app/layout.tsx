import type { Metadata } from "next";
import { Manrope, JetBrains_Mono, Dancing_Script } from "next/font/google";
import { SpeedInsights } from "@vercel/speed-insights/next";
import { Toaster } from "sonner";
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
  title: "AIRA AI — Turn Every Enquiry Into Revenue | AI Revenue Acceleration Platform",
  description: "AIRA helps businesses automate conversations, qualify leads, evaluate telecallers and convert more customers. AI-powered conversational CRM for WhatsApp, Instagram, Facebook & more.",
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
      </body>
    </html>
  );
}
