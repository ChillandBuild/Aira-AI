import type { MetadataRoute } from "next";

const SITE_URL = "https://www.anrilaitech.com";

// Public pages only. The /new marketing pages join this list when they replace the
// current homepage; until then they are noindex.
const PATHS = ["/", "/contact", "/privacy-policy", "/terms-and-conditions", "/data-deletion"];

export default function sitemap(): MetadataRoute.Sitemap {
  return PATHS.map((path) => ({ url: `${SITE_URL}${path}` }));
}
