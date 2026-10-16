import type { AdBreakdownKey, AdBreakdownValues } from "@/lib/api";

export const BREAKDOWN_TABS: { key: AdBreakdownKey; label: string; noun: string }[] = [
  { key: "placement", label: "Placement", noun: "placement" },
  { key: "age", label: "Age", noun: "age group" },
  { key: "gender", label: "Gender", noun: "gender" },
  { key: "region", label: "Region", noun: "region" },
  { key: "device", label: "Device", noun: "device" },
];

const PLATFORM_NAMES: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  messenger: "Messenger",
  audience_network: "Audience Network",
  threads: "Threads",
  whatsapp: "WhatsApp",
};

const POSITION_NAMES: Record<string, string> = {
  feed: "Feed",
  story: "Stories",
  stories: "Stories",
  reels: "Reels",
  explore: "Explore",
  explore_home: "Explore home",
  profile_feed: "Profile feed",
  marketplace: "Marketplace",
  video_feeds: "Video feeds",
  right_hand_column: "Right column",
  search: "Search results",
  messenger_inbox: "Inbox",
  inbox: "Inbox",
  an_classic: "Native",
  instream_video: "In-stream videos",
  reels_overlay: "Reels overlay",
  facebook_reels: "Reels",
};

const GENDER_NAMES: Record<string, string> = {
  male: "Men",
  female: "Women",
  unknown: "Unknown",
};

const DEVICE_NAMES: Record<string, string> = {
  android_smartphone: "Android phone",
  android_tablet: "Android tablet",
  iphone: "iPhone",
  ipad: "iPad",
  desktop: "Computer",
  other: "Other",
};

/** "audience_network" -> "Audience network", "banner" -> "Banner". */
function sentenceCase(raw: string): string {
  const spaced = raw.replaceAll("_", " ").trim().toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function placementLabel(raw: string): string {
  const [platformRaw, positionRaw] = raw.split(" · ");
  const platformKey = (platformRaw ?? "").trim().toLowerCase();
  const platform = PLATFORM_NAMES[platformKey] ?? sentenceCase(platformKey);
  let position = (positionRaw ?? "").trim().toLowerCase();
  if (position.startsWith(`${platformKey}_`)) position = position.slice(platformKey.length + 1);
  if (!position) return platform;
  const positionLabel = POSITION_NAMES[position] ?? sentenceCase(position);
  return `${platform} ${positionLabel}`;
}

/** Human label for a raw Meta breakdown value, e.g. "instagram · instagram_reels" -> "Instagram Reels". */
export function groupLabel(raw: string, breakdown: AdBreakdownKey): string {
  const trimmed = (raw ?? "").trim();
  if (!trimmed || trimmed.toLowerCase() === "unknown") return "Unknown";
  switch (breakdown) {
    case "placement":
      return placementLabel(trimmed);
    case "gender":
      return GENDER_NAMES[trimmed.toLowerCase()] ?? sentenceCase(trimmed);
    case "device":
      return DEVICE_NAMES[trimmed.toLowerCase()] ?? sentenceCase(trimmed);
    case "age":
    case "region":
      return trimmed;
  }
}

/** Cost per chat click: Meta's figure when present, otherwise spend divided by clicks. */
export function costPerClick(values: AdBreakdownValues): number | null {
  if (values.cost_per_inline_link_click != null) return values.cost_per_inline_link_click;
  const clicks = values.inline_link_clicks;
  const spend = values.spend;
  if (clicks != null && spend != null && clicks > 0 && spend > 0) return spend / clicks;
  return null;
}

/**
 * Index of the row with the lowest cost per chat click, counting only rows with
 * at least `minClicks` chat clicks. Returns null when fewer than two rows qualify,
 * since a single group cannot be "cheapest".
 */
export function pickCheapest(
  rows: { label: string; values: AdBreakdownValues }[],
  minClicks = 5,
): number | null {
  let best: number | null = null;
  let bestCost = Infinity;
  let qualifying = 0;
  rows.forEach((row, index) => {
    const clicks = row.values.inline_link_clicks;
    if (clicks == null || clicks < minClicks) return;
    const cost = costPerClick(row.values);
    if (cost == null) return;
    qualifying += 1;
    if (cost < bestCost) {
      bestCost = cost;
      best = index;
    }
  });
  return qualifying >= 2 ? best : null;
}

function rupees(amount: number): string {
  return Math.round(amount).toLocaleString("en-IN");
}

/** Callout text when a group is cheaper than the whole ad; null otherwise. */
export function cheapestSentence(
  rowLabel: string,
  rowCost: number,
  overallCost: number | null,
): string | null {
  if (overallCost == null || rowCost >= overallCost) return null;
  return `Cheapest chat clicks for this ad: ${rowLabel}, ₹${rupees(rowCost)} each vs ₹${rupees(overallCost)} for the whole ad.`;
}
