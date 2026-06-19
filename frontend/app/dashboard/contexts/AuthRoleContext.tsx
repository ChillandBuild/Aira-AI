"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { API_URL } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

interface RoleCtx {
  role: "owner" | "caller" | null;
  callerId: string | null;
  enabledFeatures: string[];
  isSystemAdmin: boolean;
  pageToggles: Record<string, unknown> | null;
  loading: boolean;
}

const AuthRoleContext = createContext<RoleCtx>({
  role: null,
  callerId: null,
  enabledFeatures: ["whatsapp", "telecalling"],
  isSystemAdmin: false,
  pageToggles: null,
  loading: true,
});

const CACHE_KEY = "aira_role_cache";

interface CacheEntry {
  userId: string;
  role: "owner" | "caller";
  callerId: string | null;
  enabledFeatures: string[];
  isSystemAdmin: boolean;
  pageToggles: Record<string, unknown> | null;
}

function readCache(): CacheEntry | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function writeCache(data: CacheEntry) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify(data)); } catch {}
}

export function clearRoleCache() {
  try { localStorage.removeItem(CACHE_KEY); } catch {}
}

export function AuthRoleProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<"owner" | "caller" | null>(null);
  const [callerId, setCallerId] = useState<string | null>(null);
  const [enabledFeatures, setEnabledFeatures] = useState<string[]>(["whatsapp", "telecalling"]);
  const [isSystemAdmin, setIsSystemAdmin] = useState(false);
  const [pageToggles, setPageToggles] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Render free-tier sleeps after 15min idle and takes 30-60s to wake.
    // 12 retries × 5s = 60s window, generous enough to survive cold-start.
    async function fetchMe(retries = 12, delayMs = 5000): Promise<void> {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const currentUserId = session?.user?.id;

      // Apply cache only if it belongs to the current user — prevents stale owner
      // role from bleeding into a caller session when the same browser is reused.
      let appliedCachedRole: "owner" | "caller" | null = null;
      if (currentUserId) {
        const cached = readCache();
        if (cached && cached.userId === currentUserId) {
          appliedCachedRole = cached.role;
          setRole(cached.role);
          setCallerId(cached.callerId);
          setEnabledFeatures(cached.enabledFeatures);
          setIsSystemAdmin(cached.isSystemAdmin);
          setPageToggles(cached.pageToggles);
          setLoading(false);
        }
      }

      const auth: Record<string, string> = session ? { Authorization: `Bearer ${session.access_token}` } : {};
      for (let attempt = 1; attempt <= retries; attempt++) {
        try {
          const res = await fetch(`${API_URL}/api/v1/team/me`, { headers: auth });
          if (!res.ok) throw new Error(`team/me ${res.status}`);
          const d = await res.json();
          const newRole = d.role as "owner" | "caller";
          const newFeatures = d.enabled_features ?? ["whatsapp", "telecalling"];
          const newIsAdmin = d.is_system_admin ?? false;
          const newCallerId = d.caller_id ?? null;
          const newToggles = d.page_toggles || null;
          if (currentUserId) {
            writeCache({ userId: currentUserId, role: newRole, callerId: newCallerId, enabledFeatures: newFeatures, isSystemAdmin: newIsAdmin, pageToggles: newToggles });
          }
          // The cached role we already committed to was wrong (role changed
          // server-side since the cache was written). Reload so the page mounts
          // fresh with the corrected role instead of unmounting the owner-only
          // tree mid-render with requests still in flight.
          if (appliedCachedRole && appliedCachedRole !== newRole) {
            window.location.reload();
            return;
          }
          setRole(newRole);
          setCallerId(newCallerId);
          setEnabledFeatures(newFeatures);
          setIsSystemAdmin(newIsAdmin);
          setPageToggles(newToggles);
          return;
        } catch {
          if (attempt < retries) {
            await new Promise((r) => setTimeout(r, delayMs));
          }
        }
      }
    }

    fetchMe().finally(() => setLoading(false));
  }, []);

  return (
    <AuthRoleContext.Provider value={{ role, callerId, enabledFeatures, isSystemAdmin, pageToggles, loading }}>
      {children}
    </AuthRoleContext.Provider>
  );
}

export const useAuthRole = () => useContext(AuthRoleContext);
