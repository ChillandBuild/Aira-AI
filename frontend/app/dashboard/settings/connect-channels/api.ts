import { API_URL, getAuthHeaders } from "@/lib/api";
import type { Setting, SettingsMap } from "./channels";

export async function fetchSettings(): Promise<Setting[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings/`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load settings");
  return (await res.json()).settings;
}

export async function saveSettings(updates: SettingsMap): Promise<void> {
  const auth = await getAuthHeaders();
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/settings/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ updates }),
    });
  } catch {
    // Raw fetch rejects with a cryptic "Load failed" (Safari) on any network hiccup.
    throw new Error("Cannot reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    // Surface the backend's specific reason (e.g. invalid Telegram token) instead of a generic string.
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Failed to save settings");
  }
}
