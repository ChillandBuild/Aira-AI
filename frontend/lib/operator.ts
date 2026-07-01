import { API_URL, getAuthHeaders } from "@/lib/api";

/**
 * Shared fetch helper for the operator console. Adds JSON content-type +
 * auth headers, and throws `detail || "Request failed"` on non-ok responses.
 * Returns the parsed JSON body as-is — callers that expect an `{ data }`
 * envelope must unwrap it themselves (this mirrors the per-page helpers it
 * replaces, some of which returned raw arrays/objects and some `{ data }`).
 */
export async function operatorFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...auth, ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

/**
 * Relative time formatter for the operator console. Handles both past
 * ("Xs ago") and future ("in Xs") timestamps across seconds/minutes/hours/days.
 * Returns "—" for null.
 */
export function relTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const future = diff < 0;
  const s = Math.abs(diff) / 1000;

  let fmt: string;
  if (s < 60) fmt = `${Math.round(s)}s`;
  else if (s < 3600) fmt = `${Math.round(s / 60)}m`;
  else if (s < 86400) fmt = `${Math.round(s / 3600)}h`;
  else fmt = `${Math.round(s / 86400)}d`;

  return future ? `in ${fmt}` : `${fmt} ago`;
}
