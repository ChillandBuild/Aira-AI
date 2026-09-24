const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://aira-ai-5tfr.onrender.com";

// Server-side backend fetch with a hard timeout. A cold backend must NEVER
// hang SSR into a white screen — on timeout/error/non-200 we return null and
// let the client take over (spinner + retry), so SSR is never worse than today.
export async function serverFetchJson<T>(
  path: string,
  token: string | undefined,
  timeoutMs = 1500,
): Promise<T | null> {
  if (!token) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
