import { operatorFetch } from "@/lib/operator";

/**
 * Client-side state for the read-only "View as tenant" operator support
 * session. This is NOT an auth mechanism — the operator's own JWT is used
 * for every request throughout. Starting/ending a session only calls the
 * admin-guarded, audit-logged `/operator/impersonation/start|end` endpoints
 * and stores a local marker (session-scoped, cleared on tab close) so the
 * UI can show a persistent "Viewing as {tenant} — Exit" banner and route
 * data-fetching toward the tenant-scoped read views. No token or credential
 * is stored — there is none to store.
 */

const STORAGE_KEY = "aira_operator_impersonation";
const EVENT_NAME = "aira:impersonation-change";

export interface ImpersonationSession {
  tenantId: string;
  tenantName: string;
  startedAt: string;
  expiresAt: string;
}

interface StartResponse {
  tenant_id: string;
  tenant_name: string;
  started_at: string;
  expires_at: string;
  read_only: boolean;
}

function emitChange() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(EVENT_NAME));
  }
}

/**
 * Clears the local session marker (sessionStorage) and notifies every
 * listener (OperatorSidebar, ClientDetailSidebar, ImpersonationBanner, the
 * client-detail header, ...) via the same change event the Exit path emits.
 * Local-only: does NOT call the backend /impersonation/end endpoint. Use this
 * for client-side expiry; use `endImpersonation` for an operator-initiated
 * exit, which also audit-logs the end on the server.
 */
export function clearImpersonationSession(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(STORAGE_KEY);
  emitChange();
}

export function getImpersonationSession(): ImpersonationSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as ImpersonationSession;
    if (new Date(session.expiresAt).getTime() <= Date.now()) {
      clearImpersonationSession();
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function subscribeImpersonation(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(EVENT_NAME, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(EVENT_NAME, callback);
    window.removeEventListener("storage", callback);
  };
}

export async function startImpersonation(tenantId: string): Promise<ImpersonationSession> {
  const res = await operatorFetch<StartResponse>("/api/v1/operator/impersonation/start", {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId }),
  });
  const session: ImpersonationSession = {
    tenantId: res.tenant_id,
    tenantName: res.tenant_name,
    startedAt: res.started_at,
    expiresAt: res.expires_at,
  };
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  emitChange();
  return session;
}

export async function endImpersonation(tenantId: string): Promise<void> {
  try {
    await operatorFetch("/api/v1/operator/impersonation/end", {
      method: "POST",
      body: JSON.stringify({ tenant_id: tenantId }),
    });
  } finally {
    window.sessionStorage.removeItem(STORAGE_KEY);
    emitChange();
  }
}
