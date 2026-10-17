import type { MetadataRoute } from "next";

const SITE_URL = "https://www.anrilaitech.com";

// The app itself (dashboard, operator console, auth callbacks) is never useful in search.
// /new is not blocked here: its pages carry a noindex robots meta tag instead, which a
// crawler can only read if it is allowed to fetch them.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/dashboard", "/operator", "/auth", "/offline"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
