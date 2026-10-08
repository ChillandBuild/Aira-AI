import { NextResponse } from "next/server";

const APP_NAME = "Anril AI";
const APP_DESCRIPTION = "WhatsApp lead management for education consultancies.";

export function GET() {
  return NextResponse.json(
    {
      id: "/",
      name: APP_NAME,
      short_name: "Anril",
      description: APP_DESCRIPTION,
      start_url: "/dashboard",
      scope: "/",
      display: "standalone",
      orientation: "portrait-primary",
      background_color: "#ffffff",
      theme_color: "#0A1528",
      categories: ["business", "productivity"],
      icons: [
        {
          src: "/icons/anril-icon-192.png",
          sizes: "192x192",
          type: "image/png",
        },
        {
          src: "/icons/anril-icon-512.png",
          sizes: "512x512",
          type: "image/png",
        },
        {
          src: "/icons/anril-maskable-512.png",
          sizes: "512x512",
          type: "image/png",
          purpose: "maskable",
        },
      ],
    },
    { headers: { "Content-Type": "application/manifest+json" } }
  );
}
