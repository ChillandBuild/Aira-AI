import type { MetadataRoute } from "next";

const APP_NAME = "Aira AI";
const APP_DESCRIPTION = "WhatsApp lead management for education consultancies.";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/aira",
    name: APP_NAME,
    short_name: "Aira",
    description: APP_DESCRIPTION,
    start_url: "/aira/dashboard",
    scope: "/aira/",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#faf8f5",
    theme_color: "#5b21b6",
    categories: ["business", "productivity"],
    icons: [
      {
        src: "/aira/icons/aira-icon-192.png",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/aira/icons/aira-icon-512.png",
        sizes: "512x512",
        type: "image/png",
      },
      {
        src: "/aira/icons/aira-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
