import { API_URL, getAuthHeaders } from "@/lib/api";
import type { BrainResponse } from "./types";

const BRAIN_URL = `${API_URL}/api/v1/brain`;

export class BrainApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "BrainApiError";
  }
}

function messageForStatus(status: number): string {
  if (status === 403) return "You don't have access to Anril Brain.";
  if (status === 404) return "Anril Brain isn't available yet. Please try again shortly.";
  return "Couldn't load Anril Brain. Please try again.";
}

function isBrainResponse(body: unknown): body is BrainResponse {
  if (typeof body !== "object" || body === null) return false;
  const b = body as Record<string, unknown>;
  return (
    typeof b.headline === "object" && b.headline !== null &&
    typeof b.waiting === "object" && b.waiting !== null &&
    Array.isArray(b.inputs) &&
    Array.isArray(b.handovers) &&
    typeof b.status === "object" && b.status !== null
  );
}

export async function getBrain(): Promise<BrainResponse> {
  let res: Response;
  try {
    res = await fetch(BRAIN_URL, { headers: await getAuthHeaders() });
  } catch {
    throw new BrainApiError("Couldn't reach the server. Please try again.");
  }
  if (!res.ok) throw new BrainApiError(messageForStatus(res.status), res.status);
  const body: unknown = await res.json().catch(() => null);
  if (!isBrainResponse(body)) throw new BrainApiError("Anril Brain sent an unexpected response.");
  return body;
}
