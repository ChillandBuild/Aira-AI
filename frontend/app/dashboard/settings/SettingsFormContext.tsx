"use client";
import { createContext, useContext, useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { createClient } from "@/lib/supabase/client";
import ChangePasswordCard from "./ChangePasswordCard";

export type Setting = {
  key: string;
  display_value: string;
  is_secret: boolean;
  is_set: boolean;
  updated_at: string;
};

export type SettingsMap = Record<string, string>;
export type SaveState = "idle" | "dirty" | "saving" | "saved";

async function fetchSettings(): Promise<Setting[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings/`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load settings");
  return (await res.json()).settings;
}

async function saveSettings(updates: SettingsMap): Promise<void> {
  const auth = await getAuthHeaders();
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await fetch(`${API_URL}/api/v1/settings/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ updates }),
      });
      if (!res.ok) throw new Error("Failed to save settings");
      return;
    } catch {
      if (attempt === 2) throw new Error("Server unreachable — please try again");
    }
  }
}

interface SettingsFormContextValue {
  loading: boolean;
  error: string | null;
  canViewSettings: boolean;
  canManageSettings: boolean;
  settings: Setting[];
  drafts: SettingsMap;
  setDrafts: React.Dispatch<React.SetStateAction<SettingsMap>>;
  saveStates: Record<string, SaveState>;
  settingFor: (key: string) => Setting | undefined;
  handleSave: (sectionId: string, allKeys: string[], sectionFieldSecrets?: Record<string, boolean>) => Promise<void>;
  email: string;
  fullName: string;
  initials: string;
  memberSince: string | null;
  tenantId: string | null;
  hasNotifications: boolean;
  hasTelecmiConfig: boolean | null;
}

const SettingsFormCtx = createContext<SettingsFormContextValue | null>(null);

export function useSettingsForm(): SettingsFormContextValue {
  const ctx = useContext(SettingsFormCtx);
  if (!ctx) throw new Error("useSettingsForm must be used within SettingsFormProvider");
  return ctx;
}

export function SettingsFormProvider({ children }: { children: React.ReactNode }) {
  const { role, permissions, loading: roleLoading } = useAuthRole();
  const canViewSettings = role === "owner" || permissions.includes("settings.view") || permissions.includes("settings.manage");
  const canManageSettings = role === "owner" || permissions.includes("settings.manage");
  const [settings, setSettings] = useState<Setting[]>([]);
  const [drafts, setDrafts] = useState<SettingsMap>({});
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [email, setEmail] = useState<string>("");
  const [fullName, setFullName] = useState<string>("");
  const [createdAt, setCreatedAt] = useState<string>("");
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [purchasedFeatures, setPurchasedFeatures] = useState<string[]>([]);
  const [callingProvider, setCallingProvider] = useState<"telecmi" | "sim_basic" | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setPurchasedFeatures((data.items ?? []).map((i: { feature_key: string }) => i.feature_key));
        }
      } catch { /* fail open — pre-existing tenants have no items rows at all */ }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/settings/telecalling-config`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setCallingProvider((data.calling_provider as "telecmi" | "sim_basic" | undefined) ?? "telecmi");
        } else {
          setCallingProvider("telecmi");
        }
      } catch {
        setCallingProvider("telecmi");
      }
    })();
  }, []);

  const hasNotifications = purchasedFeatures.length === 0 || purchasedFeatures.includes("inbound_messaging") || purchasedFeatures.includes("outbound_messaging");
  const hasTelecmiConfig = callingProvider === null ? null : callingProvider === "telecmi";

  const load = useCallback(async () => {
    try {
      const s = await fetchSettings();
      setSettings(s);
      setDrafts((prev) => {
        const next: SettingsMap = { ...prev };
        s.forEach((row) => {
          if (!row.is_secret) {
            const value = row.display_value === "Not set" ? "" : row.display_value;
            if (!(row.key in next) || next[row.key] === "") next[row.key] = value;
          } else {
            if (!(row.key in next)) next[row.key] = "";
          }
        });
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/onboarding/status`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          if (data.tenant_id) setTenantId(data.tenant_id);
        }
      } catch {}
    })();
    const supabase = createClient();
    const loadUser = async () => {
      const { data } = await supabase.auth.getUser();
      const userEmail = data.user?.email ?? "";
      setEmail(userEmail);
      setCreatedAt(data.user?.created_at ?? "");
      const metaName = data.user?.user_metadata?.full_name;
      if (metaName) {
        setFullName(metaName);
      } else {
        const parts = userEmail.split("@")[0].split(/[._-]/);
        const capitalized = parts.map((p: string) => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
        setFullName(capitalized || "Admin User");
      }
    };
    loadUser();
  }, [load]);

  const initials = fullName.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2) || "AD";
  const memberSince = createdAt ? new Date(createdAt).toLocaleDateString("en-IN", { month: "long", year: "numeric" }) : null;

  function settingFor(key: string) {
    return settings.find(s => s.key === key);
  }

  async function handleSave(sectionId: string, allKeys: string[], sectionFieldSecrets: Record<string, boolean> = {}) {
    if (!canManageSettings) return;
    setSaveStates(s => ({ ...s, [sectionId]: "saving" }));
    setError(null);
    const updates: SettingsMap = {};
    allKeys.forEach(k => {
      const draft = drafts[k];
      const current = settingFor(k);
      const isSecret = sectionFieldSecrets[k] ?? current?.is_secret ?? false;
      if (isSecret) {
        if (draft && draft.length > 0) updates[k] = draft;
      } else {
        const stored = current ? (current.display_value === "Not set" ? "" : current.display_value) : "";
        if (draft !== undefined && draft !== stored) updates[k] = draft;
      }
    });

    try {
      if (Object.keys(updates).length > 0) await saveSettings(updates);
      setDrafts(prev => {
        const next = { ...prev };
        allKeys.forEach(k => delete next[k]);
        return next;
      });
      await load();
      setSaveStates(s => ({ ...s, [sectionId]: "saved" }));
      setTimeout(() => setSaveStates(s => ({ ...s, [sectionId]: "idle" })), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setSaveStates(s => ({ ...s, [sectionId]: "idle" }));
    }
  }

  const value = useMemo<SettingsFormContextValue>(() => ({
    loading, error, canViewSettings, canManageSettings, settings, drafts, setDrafts,
    saveStates, settingFor, handleSave, email, fullName, initials, memberSince,
    tenantId, hasNotifications, hasTelecmiConfig,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [loading, error, canViewSettings, canManageSettings, settings, drafts, saveStates, email, fullName, initials, memberSince, tenantId, hasNotifications, hasTelecmiConfig]);

  if (roleLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (!canViewSettings) {
    return (
      <div>
        <ChangePasswordCard />
      </div>
    );
  }

  return <SettingsFormCtx.Provider value={value}>{children}</SettingsFormCtx.Provider>;
}
