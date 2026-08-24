# Settings Navigation Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single tabbed `/dashboard/settings` page (5 tabs, 10 stacked panels, reached only via a hidden `MoreMenu` link) with one route per settings section, reachable from a new collapsible "Settings" entry in the main sidebar.

**Architecture:** A Next.js `layout.tsx` wraps every `/dashboard/settings/*` route in a `SettingsFormProvider` that owns the one shared fetch/save state today's `page.tsx` holds. 6 of the 10 sections are already self-contained components and just get a thin route wrapper. The other 4 (admin identity, TeleCMI credentials, AI Auto-Reply, Silence-Nudge) are raw JSX currently inline in `page.tsx` sharing that state directly — they move into their own pages, consuming the new context instead of local page state. The sidebar gets a new "Settings" entry using the same expand-in-place pattern already built for "Telecalling".

**Tech Stack:** Next.js 14 (App Router), React, TypeScript, Tailwind. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-23-nested-packages-and-settings-nav-design.md` (section 7 — this plan implements that section only; nested packages is a separate plan)

## Global Constraints

- No new npm dependencies. This codebase has no `@testing-library/react` — route-wrapper pages have no existing unit-test pattern in this repo (confirmed: no `page.tsx` anywhere under `frontend/app/` has a companion test file). Verify page-shell changes by running the dev server and navigating to the route, not by inventing a new test harness.
- Pure, dependency-free logic (e.g. `parseSilenceDelays`) does get a vitest unit test — that pattern already exists in this codebase (`frontend/app/dashboard/settings/connect-channels/metaSignupMode.test.ts` tests a plain function next to its source file).
- Every relocated JSX block must be moved verbatim (same classNames, same structure) — this is a relocation, not a redesign.
- Old `?tab=` query-param links break silently once this ships — acceptable, this is operator-only tooling, confirmed in the spec.

---

## Task 1: `SettingsFormContext` — shared load/save state

**Files:**
- Create: `frontend/app/dashboard/settings/SettingsFormContext.tsx`
- Test: `frontend/app/dashboard/settings/parseSilenceDelays.test.ts` (extracted pure function, see Task 4 — not part of this task's deliverable, listed here only so Task 4 doesn't re-explain it)

**Interfaces:**
- Produces: `SettingsFormProvider({ children }): JSX.Element`, `useSettingsForm(): SettingsFormContextValue` — every later task in this plan consumes `useSettingsForm()`.
- `SettingsFormContextValue` (exact shape below) is the contract every other task's page component is written against.

- [ ] **Step 1: Create the context file with types and the fetch helpers, moved verbatim from `page.tsx:27-139`**

```tsx
// frontend/app/dashboard/settings/SettingsFormContext.tsx
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
  hasTelecmiConfig: boolean;
}

const SettingsFormCtx = createContext<SettingsFormContextValue | null>(null);

export function useSettingsForm(): SettingsFormContextValue {
  const ctx = useContext(SettingsFormCtx);
  if (!ctx) throw new Error("useSettingsForm must be used within SettingsFormProvider");
  return ctx;
}
```

- [ ] **Step 2: Add the state/effects block, moved verbatim from `page.tsx:225-344` (drop the tab-routing bits — `router`/`pathname`/`searchParams`/`activeTab` stay in the redirect stub, not here)**

Append inside the same file, after the context declaration:

```tsx
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
  const hasTelecmiConfig = callingProvider === "telecmi";

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
```

Note: `handleSave` takes an explicit `sectionFieldSecrets` map now instead of looking up a page-local `SECTIONS` array (that array moves to `telecalling/page.tsx` in Task 4, where it's the only consumer — the context can't reference a type that no longer lives here).

- [ ] **Step 3: Verify it builds**

Run: `cd frontend && npm run typecheck`
Expected: no new errors referencing `SettingsFormContext.tsx`. (Consumers don't exist yet — this step only confirms the file itself is syntactically and structurally valid; wire it up in Task 2.)

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/settings/SettingsFormContext.tsx
git commit -m "feat: extract settings load/save state into SettingsFormContext"
```

---

## Task 2: `layout.tsx` wrapping every settings route

**Files:**
- Create: `frontend/app/dashboard/settings/layout.tsx`

**Interfaces:**
- Consumes: `SettingsFormProvider` from Task 1.
- Produces: every route under `/dashboard/settings/*` is now inside `SettingsFormProvider` automatically (Next.js layout nesting) — later tasks' pages can call `useSettingsForm()` without importing the provider themselves.

- [ ] **Step 1: Create the layout**

```tsx
// frontend/app/dashboard/settings/layout.tsx
"use client";
import { SettingsFormProvider } from "./SettingsFormContext";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return <SettingsFormProvider>{children}</SettingsFormProvider>;
}
```

- [ ] **Step 2: Verify it builds**

Run: `cd frontend && npm run typecheck`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/settings/layout.tsx
git commit -m "feat: wrap all settings routes in SettingsFormProvider"
```

---

## Task 3: `general/page.tsx` — admin identity card + password change

**Files:**
- Create: `frontend/app/dashboard/settings/general/page.tsx`

**Interfaces:**
- Consumes: `useSettingsForm()` → `{ fullName, initials, email, memberSince }`.

- [ ] **Step 1: Create the page, moving the admin identity card JSX verbatim from `page.tsx:542-582`**

```tsx
// frontend/app/dashboard/settings/general/page.tsx
"use client";
import { Crown } from "lucide-react";
import { useSettingsForm } from "../SettingsFormContext";
import ChangePasswordCard from "../ChangePasswordCard";

export default function GeneralSettingsPage() {
  const { fullName, initials, email, memberSince } = useSettingsForm();

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#1c1917] via-[#292524] to-[#1c1917] p-5 shadow-xl sm:rounded-[2rem] sm:p-8">
        <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-primary/10 to-transparent rounded-full -translate-y-1/2 translate-x-1/3" />
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-gradient-to-tr from-amber-500/10 to-transparent rounded-full translate-y-1/2 -translate-x-1/4" />

        <div className="relative flex min-w-0 flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#2e1065] to-primary shadow-lg shadow-primary/25 sm:h-20 sm:w-20">
            <span className="font-display text-2xl font-bold text-white sm:text-3xl">{initials}</span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h2 className="break-words font-display text-xl font-bold text-white sm:text-2xl">{fullName}</h2>
              <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/30">
                <Crown size={12} className="text-amber-400" />
                <span className="font-label text-xs font-bold text-amber-300 uppercase tracking-wider">Admin</span>
              </span>
            </div>
            {email && (
              <p className="mt-1 break-all font-body text-sm text-[#a8a29e]">{email}</p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-3 sm:gap-4">
              {memberSince && (
                <span className="font-label text-xs text-[#78716c]">Member since {memberSince}</span>
              )}
              <span className="flex items-center gap-1.5 font-label text-xs text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                All systems online
              </span>
            </div>
          </div>
        </div>

        <div className="relative mt-6 pt-6 border-t border-[#44403c]/50">
          <p className="font-body text-sm text-[#a8a29e] italic leading-relaxed">
            &quot;The best leaders don&apos;t create followers — they create more leaders.&quot;
          </p>
          <p className="font-label text-[10px] text-[#57534e] mt-1 uppercase tracking-widest">Your role: Empower your team</p>
        </div>
      </div>

      <ChangePasswordCard />
    </div>
  );
}
```

- [ ] **Step 2: Manual verification**

Run: `cd frontend && npm run dev`, navigate to `/dashboard/settings/general`.
Expected: identity card renders with real name/email/initials, password card below it, matches what the old `?tab=general` view looked like.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/settings/general/page.tsx
git commit -m "feat: add /dashboard/settings/general route"
```

---

## Task 4: `telecalling/page.tsx` — TeleCMI credentials

**Files:**
- Create: `frontend/app/dashboard/settings/telecalling/page.tsx`

**Interfaces:**
- Consumes: `useSettingsForm()` → `{ settingFor, drafts, setDrafts, saveStates, canManageSettings, tenantId, handleSave }`.

- [ ] **Step 1: Create the page — `SECTIONS`, `OutlinedField`, `SecretField` move here from `page.tsx:59-73` and `:141-214` verbatim (only consumer), voice-credentials JSX moves from `page.tsx:590-680`**

```tsx
// frontend/app/dashboard/settings/telecalling/page.tsx
"use client";
import { useState } from "react";
import { Phone, Eye, EyeOff } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useSettingsForm } from "../SettingsFormContext";
import {
  SaveButton, SaveStatus, SectionFooter, SettingsAccordion, SettingsSection,
} from "../SettingsSection";

type FieldDef = {
  key: string; label: string; placeholder?: string; secret: boolean;
  required?: boolean; hint?: string;
};

const VOICE_SECTION = {
  id: "voice",
  label: "Voice Calling (Cloud Telephony)",
  icon: Phone,
  description: "Cloud Telephony credentials for click-to-call telecalling. Per-caller Agent IDs are set on the Team page.",
  fields: [
    { key: "telecmi_secret", label: "App Secret", secret: true, required: true },
    { key: "telecmi_callerid", label: "Caller ID (DID shown to leads)", secret: false, required: false, hint: "The outbound number leads see when you call them" },
    { key: "telecmi_webhook_secret", label: "Webhook Secret", secret: true, required: false, hint: "Appended as ?webhook_secret= to your Cloud Telephony CDR webhook URL" },
  ] as FieldDef[],
};

function OutlinedField({
  label, value, onChange, placeholder, type = "text", rightSlot, hint, disabled = false,
}: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; type?: "text" | "password"; rightSlot?: React.ReactNode; hint?: string; disabled?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="relative">
        <input
          type={type}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder ?? " "}
          className="peer w-full px-4 pt-5 pb-2 pr-10 rounded-xl bg-white border border-border text-sm font-body text-ink placeholder:text-ink-muted/40 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 transition disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-ink-muted"
        />
        <label className="pointer-events-none absolute left-3 -top-2 px-1.5 text-[11px] font-label font-medium text-ink-muted bg-white tracking-wide">
          {label}
        </label>
        {rightSlot && (
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center">
            {rightSlot}
          </div>
        )}
      </div>
      {hint && <p className="text-[11px] text-ink-muted font-body pl-1">{hint}</p>}
    </div>
  );
}

function SecretField({
  label, storedMask, isSet, newValue, onChange, hint, disabled = false,
}: {
  label: string; storedMask: string; isSet: boolean;
  newValue: string; onChange: (v: string) => void; hint?: string; disabled?: boolean;
}) {
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(false);
  const showInput = editing || newValue.length > 0 || !isSet;

  return (
    <div className="space-y-1">
      {!showInput ? (
        <button type="button" disabled={disabled} onClick={() => setEditing(true)} className="relative w-full text-left group disabled:cursor-not-allowed">
          <div className="w-full px-4 pt-5 pb-2 rounded-xl bg-white border border-border font-mono text-sm text-ink-secondary cursor-text group-hover:border-primary/40 transition group-disabled:cursor-not-allowed group-disabled:bg-surface-subtle group-disabled:text-ink-muted">
            {storedMask}
          </div>
          <span className="pointer-events-none absolute left-3 -top-2 px-1.5 text-[11px] font-label font-medium text-ink-muted bg-white tracking-wide">
            {label}
          </span>
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] font-label font-semibold text-primary opacity-0 group-hover:opacity-100 transition">
            Edit
          </span>
        </button>
      ) : (
        <OutlinedField
          label={label}
          value={newValue}
          onChange={onChange}
          type={show ? "text" : "password"}
          placeholder={isSet ? "Enter new value to replace existing" : "Paste your value here"}
          rightSlot={
            <button type="button" onClick={() => setShow(s => !s)} className="p-1 text-ink-muted hover:text-ink-secondary" tabIndex={-1}>
              {show ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          }
          disabled={disabled}
        />
      )}
      {hint && <p className="text-[11px] text-ink-muted font-body pl-1">{hint}</p>}
    </div>
  );
}

export default function TelecallingSettingsPage() {
  const { settingFor, drafts, setDrafts, saveStates, canManageSettings, tenantId, handleSave } = useSettingsForm();

  const voiceConfigured = VOICE_SECTION.fields.filter(f => f.required !== false).every(f => settingFor(f.key)?.is_set);
  const dirty = VOICE_SECTION.fields.some(f => {
    const meta = settingFor(f.key);
    const draft = drafts[f.key] ?? "";
    if (f.secret) return draft.length > 0;
    const stored = meta?.display_value === "Not set" ? "" : (meta?.display_value ?? "");
    return draft !== stored;
  });
  const secretMap = Object.fromEntries(VOICE_SECTION.fields.map(f => [f.key, f.secret]));

  return (
    <SettingsAccordion>
      <SettingsSection
        id="voice-credentials"
        icon={VOICE_SECTION.icon}
        accent="amber"
        title={VOICE_SECTION.label}
        description={VOICE_SECTION.description}
        status={{ label: voiceConfigured ? "Configured" : "Not configured", tone: voiceConfigured ? "on" : "warn" }}
        dirty={dirty}
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {VOICE_SECTION.fields.map((field) => {
            const meta = settingFor(field.key);
            const draft = drafts[field.key] ?? "";
            const labelWithOptional = field.required === false ? `${field.label} (optional)` : field.label;
            if (field.secret) {
              return (
                <SecretField
                  key={field.key}
                  label={labelWithOptional}
                  storedMask={meta?.display_value ?? "Not set"}
                  isSet={!!meta?.is_set}
                  newValue={draft}
                  onChange={v => setDrafts(d => ({ ...d, [field.key]: v }))}
                  hint={field.hint}
                  disabled={!canManageSettings}
                />
              );
            }
            return (
              <OutlinedField
                key={field.key}
                label={labelWithOptional}
                value={draft}
                onChange={v => setDrafts(d => ({ ...d, [field.key]: v }))}
                placeholder={field.placeholder}
                hint={field.hint}
                disabled={!canManageSettings}
              />
            );
          })}
        </div>

        <div className="mt-5 space-y-2 rounded-2xl border border-border bg-surface-subtle p-4 font-body text-xs">
          <p className="font-label text-[10px] font-bold uppercase tracking-wider text-ink-secondary">Setup Guide</p>
          <ol className="list-inside list-decimal space-y-1 text-ink-secondary">
            <li>Log in to your <span className="font-semibold">Cloud Telephony dashboard</span> → Settings → Webhook</li>
            <li>Set CDR Webhook URL to:<br />
              <code className="mt-1 inline-block select-all break-all rounded border border-border bg-white px-2 py-1 font-mono text-[11px] text-ink">
                {tenantId ? `${API_URL}/api/v1/calls/telecmi-cdr/${tenantId}` : "Retrieving webhook URL…"}
              </code>
            </li>
            <li>If using a Webhook Secret, append it: <code className="rounded border border-border bg-white px-1 py-0.5 font-mono text-[10px]">?webhook_secret=YOUR_SECRET</code></li>
            <li>Set your <span className="font-semibold">App Secret</span> above (from Cloud Telephony dashboard → API Keys)</li>
            <li>Per-caller <span className="font-semibold">Agent IDs</span> are configured on the <span className="font-semibold">Team page</span></li>
          </ol>
        </div>

        <SectionFooter
          status={<SaveStatus state={saveStates.voice ?? "idle"} dirty={dirty} idleLabel={voiceConfigured ? "Credentials are set" : "Credentials not set yet"} />}
        >
          <SaveButton
            state={saveStates.voice ?? "idle"}
            dirty={dirty}
            disabled={!canManageSettings}
            onClick={() => handleSave("voice", VOICE_SECTION.fields.map(f => f.key), secretMap)}
          />
        </SectionFooter>
      </SettingsSection>
    </SettingsAccordion>
  );
}
```

- [ ] **Step 2: Manual verification**

Run: `cd frontend && npm run dev`, navigate to `/dashboard/settings/telecalling`.
Expected: renders identically to the old `?tab=telecalling` view — same fields, same webhook guide, save button works (test by changing a field and saving, confirm `SaveStatus` flips to "saved").

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/settings/telecalling/page.tsx
git commit -m "feat: add /dashboard/settings/telecalling route"
```

---

## Task 5: `auto-reply/page.tsx` and `follow-ups/page.tsx`

**Files:**
- Create: `frontend/app/dashboard/settings/auto-reply/page.tsx`
- Create: `frontend/app/dashboard/settings/follow-ups/page.tsx`
- Create: `frontend/app/dashboard/settings/parseSilenceDelays.ts` (extracted pure function)
- Test: `frontend/app/dashboard/settings/parseSilenceDelays.test.ts`

**Interfaces:**
- Consumes: `useSettingsForm()` → `{ settingFor, drafts, setDrafts, saveStates, canManageSettings, handleSave }`.
- Produces: `parseSilenceDelays(raw: string): number[] | null`, importable by `follow-ups/page.tsx`.

- [ ] **Step 1: Extract `parseSilenceDelays` into its own file (pure function, moved from `page.tsx:100-115`)**

```ts
// frontend/app/dashboard/settings/parseSilenceDelays.ts

/** Mirrors _parse_delays in backend/app/services/silence_nudge.py: up to three
 *  whole minutes, 1-1440, strictly increasing. Returns null when invalid so the
 *  UI can reject on save rather than let the backend silently fall back. */
export function parseSilenceDelays(raw: string): number[] | null {
  const MAX_RUNGS = 3;
  const parts = raw.split(",").map(s => s.trim()).filter(Boolean);
  if (parts.length === 0 || parts.length > MAX_RUNGS) return null;
  const nums: number[] = [];
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return null;
    const n = parseInt(part, 10);
    if (n < 1 || n > 1440) return null;
    if (nums.length > 0 && n <= nums[nums.length - 1]) return null;
    nums.push(n);
  }
  return nums;
}
```

- [ ] **Step 2: Write the failing test**

```ts
// frontend/app/dashboard/settings/parseSilenceDelays.test.ts
import { describe, it, expect } from "vitest";
import { parseSilenceDelays } from "./parseSilenceDelays";

describe("parseSilenceDelays", () => {
  it("parses a single delay", () => {
    expect(parseSilenceDelays("5")).toEqual([5]);
  });

  it("parses multiple strictly increasing delays", () => {
    expect(parseSilenceDelays("5,60")).toEqual([5, 60]);
  });

  it("rejects non-increasing values", () => {
    expect(parseSilenceDelays("60,5")).toBeNull();
  });

  it("rejects more than 3 values", () => {
    expect(parseSilenceDelays("1,2,3,4")).toBeNull();
  });

  it("rejects values outside 1-1440", () => {
    expect(parseSilenceDelays("0")).toBeNull();
    expect(parseSilenceDelays("1441")).toBeNull();
  });

  it("rejects empty input", () => {
    expect(parseSilenceDelays("")).toBeNull();
  });
});
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd frontend && npx vitest run app/dashboard/settings/parseSilenceDelays.test.ts`
Expected: PASS (this is a characterization test of pre-existing, already-correct logic being relocated — it should pass immediately, confirming the extraction didn't change behavior).

- [ ] **Step 4: Create `auto-reply/page.tsx`, moving the AI Auto-Reply JSX verbatim from `page.tsx:686-724`, with `AI_AUTO_REPLY_TOGGLE` and its derived dirty/enabled logic moved from `page.tsx:75-80` and `:372-385`**

```tsx
// frontend/app/dashboard/settings/auto-reply/page.tsx
"use client";
import { Sparkles } from "lucide-react";
import { useSettingsForm } from "../SettingsFormContext";
import { SaveButton, SaveStatus, SectionFooter, SettingsAccordion, SettingsSection, SwitchPill } from "../SettingsSection";

const AI_AUTO_REPLY_KEY = "ai_auto_reply_enabled";
const AI_AUTO_REPLY_DEFAULT_ENABLED = true;

export default function AutoReplySettingsPage() {
  const { settingFor, drafts, setDrafts, saveStates, canManageSettings, handleSave } = useSettingsForm();

  const stored = settingFor(AI_AUTO_REPLY_KEY)?.display_value;
  const enabled = drafts[AI_AUTO_REPLY_KEY] !== undefined
    ? drafts[AI_AUTO_REPLY_KEY] === "true"
    : (stored === "Not set" || !stored ? AI_AUTO_REPLY_DEFAULT_ENABLED : stored === "true");
  const dirty = (() => {
    const draft = drafts[AI_AUTO_REPLY_KEY];
    if (draft === undefined) return false;
    const storedNormalized = stored === "Not set" || !stored
      ? (AI_AUTO_REPLY_DEFAULT_ENABLED ? "true" : "false")
      : (stored === "true" ? "true" : "false");
    return draft !== storedNormalized;
  })();

  return (
    <SettingsAccordion>
      <SettingsSection
        id="ai-auto-reply"
        icon={Sparkles}
        accent="violet"
        title="AI Auto-Reply"
        description="Turn on automatic AI replies for inbound WhatsApp messages. Voice delivery is controlled by your operator plan settings."
        status={{ label: enabled ? "On" : "Off", tone: enabled ? "on" : "off" }}
        dirty={dirty}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border-subtle bg-surface-subtle p-4">
          <div className="min-w-0">
            <p className="font-body text-sm font-semibold text-ink">Reply automatically with AI</p>
            <p className="mt-0.5 font-body text-xs text-ink-muted">
              When off, inbound messages sit in the inbox until a teammate answers them.
            </p>
          </div>
          <SwitchPill
            on={enabled}
            disabled={!canManageSettings}
            onChange={(next) => setDrafts(d => ({ ...d, [AI_AUTO_REPLY_KEY]: next ? "true" : "false" }))}
          />
        </div>

        <SectionFooter
          status={<SaveStatus state={saveStates.automations_ai ?? "idle"} dirty={dirty} idleLabel={enabled ? "AI replies are enabled" : "AI replies are disabled"} />}
        >
          <SaveButton
            state={saveStates.automations_ai ?? "idle"}
            dirty={dirty}
            disabled={!canManageSettings}
            onClick={() => handleSave("automations_ai", [AI_AUTO_REPLY_KEY])}
          />
        </SectionFooter>
      </SettingsSection>
    </SettingsAccordion>
  );
}
```

- [ ] **Step 5: Create `follow-ups/page.tsx`, moving the Silence-Nudge JSX verbatim from `page.tsx:726-841`, with `SILENCE_NUDGE_KEYS`/`SILENCE_NUDGE_DEFAULTS` moved from `page.tsx:82-96`**

```tsx
// frontend/app/dashboard/settings/follow-ups/page.tsx
"use client";
import { Timer } from "lucide-react";
import { useSettingsForm } from "../SettingsFormContext";
import { parseSilenceDelays } from "../parseSilenceDelays";
import { SaveButton, SaveStatus, SectionFooter, SettingsAccordion, SettingsSection, SwitchPill } from "../SettingsSection";

const SILENCE_NUDGE_KEYS = {
  enabled: "silence_nudge_enabled",
  delays: "silence_nudge_delays",
  cap: "silence_nudge_daily_cap",
  quietStart: "silence_nudge_quiet_start",
  quietEnd: "silence_nudge_quiet_end",
} as const;

const SILENCE_NUDGE_DEFAULTS: Record<string, string> = {
  [SILENCE_NUDGE_KEYS.enabled]: "false",
  [SILENCE_NUDGE_KEYS.delays]: "5",
  [SILENCE_NUDGE_KEYS.cap]: "1",
  [SILENCE_NUDGE_KEYS.quietStart]: "21:00",
  [SILENCE_NUDGE_KEYS.quietEnd]: "09:00",
};

export default function FollowUpsSettingsPage() {
  const { settingFor, drafts, setDrafts, saveStates, canManageSettings, handleSave } = useSettingsForm();

  const stored = (key: string) => {
    const s = settingFor(key)?.display_value;
    return !s || s === "Not set" ? SILENCE_NUDGE_DEFAULTS[key] : s;
  };
  const value = (key: string) => drafts[key] ?? stored(key);
  const enabled = value(SILENCE_NUDGE_KEYS.enabled) === "true";
  const dirty = Object.values(SILENCE_NUDGE_KEYS).some(key => drafts[key] !== undefined && drafts[key] !== stored(key));
  const delaysValid = parseSilenceDelays(value(SILENCE_NUDGE_KEYS.delays)) !== null;
  const capValid = (() => {
    const raw = value(SILENCE_NUDGE_KEYS.cap);
    if (!/^\d+$/.test(raw)) return false;
    const n = parseInt(raw, 10);
    return n >= 1 && n <= 10;
  })();

  return (
    <SettingsAccordion>
      <SettingsSection
        id="silence-nudge"
        icon={Timer}
        accent="emerald"
        title="Auto follow-up when a lead goes quiet"
        description="After the AI answers, if the lead stays silent, send one short message about what they were discussing. Never sent while your team has taken over the chat, or during a paid consultation."
        status={{ label: enabled ? "On" : "Off", tone: enabled ? "on" : "off" }}
        dirty={dirty}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border-subtle bg-surface-subtle p-4">
          <div className="min-w-0">
            <p className="font-body text-sm font-semibold text-ink">Send a quiet-lead follow-up</p>
            <p className="mt-0.5 font-body text-xs text-ink-muted">
              One short nudge per lead, on the topic they were already asking about.
            </p>
          </div>
          <SwitchPill
            on={enabled}
            disabled={!canManageSettings}
            onChange={(next) => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.enabled]: next ? "true" : "false" }))}
          />
        </div>

        {enabled && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Wait time (minutes)</span>
              <input
                type="text"
                inputMode="numeric"
                disabled={!canManageSettings}
                value={value(SILENCE_NUDGE_KEYS.delays)}
                onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.delays]: e.target.value }))}
                className={`mt-1.5 w-full rounded-xl border bg-white px-3 py-2 font-body text-sm text-ink transition focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60 ${
                  delaysValid ? "border-border focus:border-primary" : "border-red-400 focus:ring-red-200"
                }`}
              />
              <span className={`mt-1 block font-body text-[11px] ${delaysValid ? "text-ink-muted" : "text-red-600"}`}>
                {delaysValid ? "5 sends one message after 5 minutes. 5,60 adds a second an hour later." : "Up to 3 whole numbers, 1–1440, increasing. e.g. 5 or 5,60"}
              </span>
            </label>

            <label className="block">
              <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Daily limit per lead</span>
              <input
                type="number"
                min={1}
                max={10}
                disabled={!canManageSettings}
                value={value(SILENCE_NUDGE_KEYS.cap)}
                onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.cap]: e.target.value }))}
                className={`mt-1.5 w-full rounded-xl border bg-white px-3 py-2 font-body text-sm text-ink transition focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60 ${
                  capValid ? "border-border focus:border-primary" : "border-red-400 focus:ring-red-200"
                }`}
              />
              <span className={`mt-1 block font-body text-[11px] ${capValid ? "text-ink-muted" : "text-red-600"}`}>
                {capValid ? "Most follow-ups one lead can get in 24 hours." : "Must be a whole number between 1 and 10."}
              </span>
            </label>

            <label className="block">
              <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Quiet hours start (IST)</span>
              <input
                type="time"
                disabled={!canManageSettings}
                value={value(SILENCE_NUDGE_KEYS.quietStart)}
                onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.quietStart]: e.target.value }))}
                className="mt-1.5 w-full rounded-xl border border-border bg-white px-3 py-2 font-body text-sm text-ink transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60"
              />
            </label>

            <label className="block">
              <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Quiet hours end (IST)</span>
              <input
                type="time"
                disabled={!canManageSettings}
                value={value(SILENCE_NUDGE_KEYS.quietEnd)}
                onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.quietEnd]: e.target.value }))}
                className="mt-1.5 w-full rounded-xl border border-border bg-white px-3 py-2 font-body text-sm text-ink transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60"
              />
              <span className="mt-1 block font-body text-[11px] text-ink-muted">
                The first follow-up always sends — quiet hours only delay later ones.
              </span>
            </label>
          </div>
        )}

        <SectionFooter
          status={<SaveStatus state={saveStates.automations_silence ?? "idle"} dirty={dirty} idleLabel={enabled ? "Quiet-lead follow-ups are enabled" : "Quiet-lead follow-ups are off"} />}
        >
          <SaveButton
            state={saveStates.automations_silence ?? "idle"}
            dirty={dirty && delaysValid && capValid}
            disabled={!canManageSettings}
            onClick={() => handleSave("automations_silence", Object.values(SILENCE_NUDGE_KEYS))}
          />
        </SectionFooter>
      </SettingsSection>
    </SettingsAccordion>
  );
}
```

- [ ] **Step 6: Manual verification**

Run: `cd frontend && npm run dev`, navigate to `/dashboard/settings/auto-reply` and `/dashboard/settings/follow-ups`.
Expected: both render identically to their old tab views; toggling the switch and saving works; invalid delay/cap input shows the red validation state.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/dashboard/settings/parseSilenceDelays.ts frontend/app/dashboard/settings/parseSilenceDelays.test.ts frontend/app/dashboard/settings/auto-reply/page.tsx frontend/app/dashboard/settings/follow-ups/page.tsx
git commit -m "feat: add /dashboard/settings/auto-reply and /follow-ups routes"
```

---

## Task 6: Thin wrapper pages for the 6 self-contained panels

**Files:**
- Create: `frontend/app/dashboard/settings/connect-channels/page.tsx`
- Create: `frontend/app/dashboard/settings/inbox/page.tsx`
- Create: `frontend/app/dashboard/settings/telecalling-behavior/page.tsx`
- Create: `frontend/app/dashboard/settings/intake-config/page.tsx`
- Create: `frontend/app/dashboard/settings/business-hours/page.tsx`
- Create: `frontend/app/dashboard/settings/notifications/page.tsx`

**Interfaces:**
- Consumes: `useSettingsForm()` → `{ canManageSettings }` only (each panel is self-contained and manages its own fetch/save internally, confirmed by `IntakeConfigPanel.tsx:53-92` and the same shape in the other 5).

These 6 are mechanically identical — one panel component that already manages itself, just needs `canManageSettings` passed through as `canManage`.

- [ ] **Step 1: `connect-channels/page.tsx`**

```tsx
// frontend/app/dashboard/settings/connect-channels/page.tsx
"use client";
import { useSettingsForm } from "../SettingsFormContext";
import ConnectChannelsPanel from "./Panel";

export default function ConnectChannelsSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <ConnectChannelsPanel canManage={canManageSettings} />;
}
```

- [ ] **Step 2: `inbox/page.tsx`**

```tsx
// frontend/app/dashboard/settings/inbox/page.tsx
"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { InboxConfigPanel } from "../InboxConfigPanel";

export default function InboxSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <InboxConfigPanel canManage={canManageSettings} />;
}
```

- [ ] **Step 3: `telecalling-behavior/page.tsx`**

```tsx
// frontend/app/dashboard/settings/telecalling-behavior/page.tsx
"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { TelecallingConfigPanel } from "../TelecallingConfigPanel";

export default function TelecallingBehaviorSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <TelecallingConfigPanel canManage={canManageSettings} />;
}
```

- [ ] **Step 4: `intake-config/page.tsx`**

```tsx
// frontend/app/dashboard/settings/intake-config/page.tsx
"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { IntakeConfigPanel } from "../IntakeConfigPanel";

export default function IntakeConfigSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <IntakeConfigPanel canManage={canManageSettings} />;
}
```

Note: `IntakeConfigPanel` still renders its own packages editor inline at this point — the nested-packages plan (separate document) is what carves the packages section out into `intake-config/packages/page.tsx` and replaces it with a link. Don't remove the inline packages section here.

- [ ] **Step 5: `business-hours/page.tsx`**

```tsx
// frontend/app/dashboard/settings/business-hours/page.tsx
"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { BusinessHoursPanel } from "../BusinessHoursPanel";

export default function BusinessHoursSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <BusinessHoursPanel canManage={canManageSettings} />;
}
```

- [ ] **Step 6: `notifications/page.tsx`**

```tsx
// frontend/app/dashboard/settings/notifications/page.tsx
"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { NotificationConfigPanel } from "../NotificationConfigPanel";

export default function NotificationsSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <NotificationConfigPanel canManage={canManageSettings} />;
}
```

- [ ] **Step 7: Manual verification**

Run: `cd frontend && npm run dev`, navigate to all 6 new routes.
Expected: each renders exactly what its old tab showed (channels connection cards, inbox config, telecalling behavior config, intake config incl. its inline packages section for now, business hours, notifications).

- [ ] **Step 8: Commit**

```bash
git add frontend/app/dashboard/settings/connect-channels/page.tsx frontend/app/dashboard/settings/inbox/page.tsx frontend/app/dashboard/settings/telecalling-behavior/page.tsx frontend/app/dashboard/settings/intake-config/page.tsx frontend/app/dashboard/settings/business-hours/page.tsx frontend/app/dashboard/settings/notifications/page.tsx
git commit -m "feat: add thin route wrappers for the 6 self-contained settings panels"
```

---

## Task 7: Collapse `page.tsx` into a redirect

**Files:**
- Modify: `frontend/app/dashboard/settings/page.tsx` (replace entire file contents)

**Interfaces:**
- None — this is the last consumer of the old tabbed UI; nothing downstream depends on `SettingsPage`'s internals after this.

- [ ] **Step 1: Replace the whole file**

```tsx
// frontend/app/dashboard/settings/page.tsx
"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SettingsPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboard/settings/general");
  }, [router]);
  return null;
}
```

- [ ] **Step 2: Manual verification**

Run: `cd frontend && npm run dev`, navigate to `/dashboard/settings` (no sub-path).
Expected: immediately redirects to `/dashboard/settings/general`.

- [ ] **Step 3: Verify `MoreMenu`/`ProfileMenu` still work unchanged**

Run: in the dev server, open the "More" menu and Profile menu, click "Settings".
Expected: both land on `/dashboard/settings`, which redirects to `/dashboard/settings/general` — no code change needed in `MoreMenu.tsx`/`ProfileMenu.tsx` (confirmed both just link to `/dashboard/settings`).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/settings/page.tsx
git commit -m "refactor: collapse settings page.tsx into a redirect to /general"
```

---

## Task 8: Clean up `AppHeader.tsx` — remove dead tab-nav, add per-route titles

**Files:**
- Modify: `frontend/components/AppHeader.tsx`

**Interfaces:**
- None — purely presentational cleanup + title lookup table.

- [ ] **Step 1: Replace the single `/dashboard/settings` title entry (`AppHeader.tsx:120-129`) with per-route entries**

Old code being replaced:
```tsx
if (pathname === "/dashboard/settings") {
  let tabLabel = "General";
  if (tab === "channels") tabLabel = "Integrations";
  if (tab === "telecalling") tabLabel = "Telecalling Config";
  if (tab === "ai" || tab === "automations") tabLabel = "Automations";
  return {
    title: `Account Settings / ${tabLabel}`,
    description: "Configure global parameters, voice calling and AI behavior.",
  };
}
```

New code:
```tsx
const SETTINGS_ROUTE_LABELS: Record<string, string> = {
  general: "General",
  "connect-channels": "Connect Channels",
  telecalling: "Telecalling Credentials",
  "auto-reply": "Auto-Reply",
  "follow-ups": "Follow-Ups",
  inbox: "Inbox",
  "telecalling-behavior": "Telecalling Behavior",
  "intake-config": "Intake Config",
  "business-hours": "Business Hours",
  notifications: "Notifications",
};

if (pathname?.startsWith("/dashboard/settings/")) {
  const segment = pathname.split("/")[3] ?? "general";
  const label = SETTINGS_ROUTE_LABELS[segment] ?? "Settings";
  return {
    title: `Account Settings / ${label}`,
    description: "Configure global parameters, voice calling and AI behavior.",
  };
}
```

(Place this where the old block was, inside `getRouteMetadata`. The `SETTINGS_ROUTE_LABELS` map can live at module scope above `getRouteMetadata`, next to `TC_FEATURE_MAP`.)

- [ ] **Step 2: Delete the dead settings-header-state effect, its state, and the desktop tab-nav render block**

Remove (all three, they only existed to power the deleted tab-nav):
- State declarations at `AppHeader.tsx:211-212` (`settingsHasTelecmiConfig`, `settingsHasNotifications`)
- The effect at `AppHeader.tsx:239-279` (`loadSettingsHeaderState`)
- The render block at `AppHeader.tsx:332-361` (the `{pathname === "/dashboard/settings" && (<nav ...>...)}` block)

- [ ] **Step 3: Verify it builds and typechecks**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors, no unused-variable warnings for the removed state/effect.

- [ ] **Step 4: Manual verification**

Run: `cd frontend && npm run dev`, navigate through all settings routes.
Expected: header title reads "Account Settings / General", "Account Settings / Telecalling Credentials", etc. per route. No leftover pill-nav in the header (the sidebar now owns navigation between settings pages, added in Task 9).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/AppHeader.tsx
git commit -m "refactor: replace settings tab-nav header state with per-route titles"
```

---

## Task 9: Sidebar "Settings" group

**Files:**
- Modify: `frontend/components/sidebar.tsx`

**Interfaces:**
- Consumes: existing `expandedGroups`/`toggleGroup` state (`sidebar.tsx:72-78`), existing `canAny` helper (`sidebar.tsx:130`).

- [ ] **Step 1: Add `Settings` to the icon imports and the `NavItem` list, and default it to collapsed**

```tsx
// sidebar.tsx:7-11 — add Settings to the lucide-react import
import {
  LayoutDashboard, MessageSquare, Users, Phone,
  BarChart2, Upload, BookOpen, Layers, FileCheck, StickyNote, Package,
  ChevronDown, ChevronRight, RadioTower, Calendar, CreditCard, ShieldCheck, Megaphone, Headset,
  Settings,
} from "lucide-react";
```

```tsx
// sidebar.tsx:39-44 — add alongside TELECALLING_ITEMS
const SETTINGS_ITEMS: NavItem[] = [
  { href: "/dashboard/settings/general", icon: Users, label: "General" },
  { href: "/dashboard/settings/connect-channels", icon: RadioTower, label: "Connect Channels" },
  { href: "/dashboard/settings/telecalling", icon: Phone, label: "Telecalling Credentials" },
  { href: "/dashboard/settings/auto-reply", icon: Sparkles, label: "Auto-Reply" },
  { href: "/dashboard/settings/follow-ups", icon: Calendar, label: "Follow-Ups" },
  { href: "/dashboard/settings/inbox", icon: MessageSquare, label: "Inbox" },
  { href: "/dashboard/settings/telecalling-behavior", icon: Headset, label: "Telecalling Behavior" },
  { href: "/dashboard/settings/intake-config", icon: FileCheck, label: "Intake Config" },
  { href: "/dashboard/settings/business-hours", icon: Calendar, label: "Business Hours" },
  { href: "/dashboard/settings/notifications", icon: Megaphone, label: "Notifications" },
];
```

`Sparkles` isn't currently imported in `sidebar.tsx` — add it to the same lucide-react import block as `Settings`.

- [ ] **Step 2: Add `expandedGroups` default entry**

```tsx
// sidebar.tsx:72-74
const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
  Telecalling: true,
  Settings: false,
});
```

- [ ] **Step 3: Add the active/show derivation, next to the existing `tcGroupItems`/`isTcActive`/`showTc` block (`sidebar.tsx:141-149`)**

```tsx
const canSettings = canAny(["settings.view", "settings.manage"]);
const isSettingsActive = SETTINGS_ITEMS.some(item => pathname.startsWith(item.href));
const showSettings = expandedGroups.Settings || isSettingsActive;
```

- [ ] **Step 4: Add the render block, right after the Telecalling group (`sidebar.tsx:417-477`, insert before the closing `</div>` at `:478`) — identical structure, `Settings` in place of `Telecalling`**

```tsx
{/* GROUP: Settings */}
{isSubscribed && canSettings && (
  <div className="space-y-0.5">
    <button
      onClick={() => toggleGroup("Settings")}
      className={cn(
        "flex items-center gap-3 px-3 py-2 w-full rounded-xl text-sm font-semibold text-left transition-all group",
        isSettingsActive ? "text-[#5b21b6]" : "text-[#1c1917] hover:bg-[#f0ece4]"
      )}
    >
      <Settings size={16} className={isSettingsActive ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
      <span className="flex-1">Settings</span>
      {showSettings ? <ChevronDown size={14} className="text-[#a8a29e]" /> : <ChevronRight size={14} className="text-[#a8a29e]" />}
    </button>

    {showSettings && (
      <div className="space-y-0.5">
        {SETTINGS_ITEMS.map((item, idx) => {
          const matches = SETTINGS_ITEMS.filter(i => pathname === i.href || pathname.startsWith(i.href + "/"));
          const bestMatch = matches.reduce<NavItem | null>(
            (best, i) => (!best || i.href.length > best.href.length ? i : best), null
          );
          const active = bestMatch?.href === item.href;
          const isLast = idx === SETTINGS_ITEMS.length - 1;

          return (
            <div key={item.href} className="relative pl-6 flex items-center h-9">
              <div
                className={cn(
                  "absolute left-3 w-px bg-[#d6cfc9]",
                  isLast ? "top-0 h-[18px]" : "-top-1 bottom-0"
                )}
              />
              <div className="absolute left-3 top-1/2 -translate-y-1 w-3.5 h-3.5 border-l border-b border-[#d6cfc9] rounded-bl-lg" />

              <Link
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 ml-3.5 px-3 py-1.5 w-[175px] rounded-xl text-[13px] transition-all duration-150 group",
                  active
                    ? "bg-white shadow-md border border-[#e8e3db] text-[#5b21b6] font-bold"
                    : "text-[#1c1917] hover:text-[#1c1917] hover:bg-[#f0ece4]"
                )}
              >
                <span className="truncate flex-1">{item.label}</span>
              </Link>
            </div>
          );
        })}
      </div>
    )}
  </div>
)}
```

(`w-[175px]` instead of Telecalling's `w-[145px]` — "Telecalling Behavior" and "Telecalling Credentials" are longer labels than the Telecalling group's own children; widen so they don't truncate.)

- [ ] **Step 5: Verify it builds**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Manual verification**

Run: `cd frontend && npm run dev`.
Expected: sidebar shows a "Settings" row near the bottom. Clicking it expands to show all 10 sub-items with the same branch-line tree styling as Telecalling. Clicking a sub-item navigates and highlights correctly. Main sidebar items (Conversations, Leads, etc.) stay visible and clickable the whole time — confirms this is the in-place expand, not a Vercel-style full swap.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/sidebar.tsx
git commit -m "feat: add collapsible Settings group to main sidebar"
```

---

## Self-Review Notes

- **Spec coverage:** every bullet in spec section 7 has a task — context/layout extraction (Tasks 1-2), the 4 raw-JSX pages (Tasks 3-5), the 6 self-contained panels (Task 6), the redirect (Task 7), header cleanup (Task 8), sidebar group (Task 9).
- **Placeholder scan:** none — every step has real, complete code moved from files read this session, or new code grounded in the same patterns.
- **Type consistency:** `useSettingsForm()`'s returned shape (Task 1) is used identically by every consuming page in Tasks 3-6 — checked each call site pulls only fields the context actually exposes.
- **Known follow-up, not a gap in this plan:** `intake-config/page.tsx` (Task 6) still renders the packages section inline. The separate nested-packages plan removes it and adds `intake-config/packages/page.tsx` — sequencing note for whoever picks that plan up next: do it after this one ships, since it depends on `intake-config/page.tsx` existing.
