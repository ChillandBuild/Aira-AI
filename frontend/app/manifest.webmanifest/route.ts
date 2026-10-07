import { NextResponse } from "next/server";

const APP_NAME = "Anril AI";
const APP_DESCRIPTION = "WhatsApp lead management for education consultancies.";

export function GET() {
  return NextResponse.json(
    {
      id: "/anril",
      name: APP_NAME,
      short_name: "Anril",
      description: APP_DESCRIPTION,
      start_url: "/anril/dashboard",
      scope: "/anril",
      display: "standalone",
      orientation: "portrait-primary",
      background_color: "#ffffff",
      theme_color: "#5b21b6",
      categories: ["business", "productivity"],
      icons: [
        {
          src: "/anril/icons/anril-icon-192.png",
          sizes: "192x192",
          type: "image/png",
        },
        {
          src: "/anril/icons/anril-icon-512.png",
          sizes: "512x512",
          type: "image/png",
        },
        {
          src: "/anril/icons/anril-maskable-512.png",
          sizes: "512x512",
          type: "image/png",
          purpose: "maskable",
        },
      ],
    },
    { headers: { "Content-Type": "application/manifest+json" } }
  );
}
