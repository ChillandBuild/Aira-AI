"use client";
import { useEffect, useState, useCallback } from "react";
import {
  CalendarCheck, ChevronDown, Save, Loader2, CheckCircle2,
  Plus, Trash2, AlertCircle,
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

type BookingType = {
  name: string;
  amount_paise: number;
};

type SaveState = "idle" | "dirty" | "saving" | "saved";

async function fetchBookingTypes(): Promise<BookingType[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings`, { headers: auth });
  if (!res.ok) return [];
  const { settings } = await res.json();
  const row = settings.find((s: { key: string }) => s.key === "booking_types");
  if (!row || row.display_value === "Not set") return [];
  try {
    return JSON.parse(row.display_value);
  } catch {
    return [];
  }
}

async function saveBookingTypes(types: BookingType[]): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ updates: { booking_types: JSON.stringify(types) } }),
  });
  if (!res.ok) throw new Error("Failed to save booking types");
}

export function BookingConfigPanel() {
  const [types, setTypes] = useState<BookingType[]>([]);
  const [draft, setDraft] = useState<BookingType[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const t = await fetchBookingTypes();
      setTypes(t);
      setDraft(t);
    } catch {
      setError("Failed to load booking types");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(types);

  function updateType(index: number, field: keyof BookingType, value: string | number) {
    setDraft(prev => prev.map((t, i) =>
      i === index ? { ...t, [field]: value } : t
    ));
    setSaveState("dirty");
  }

  function addType() {
    setDraft(prev => [...prev, { name: "", amount_paise: 50000 }]);
    setSaveState("dirty");
  }

  function removeType(index: number) {
    setDraft(prev => prev.filter((_, i) => i !== index));
    setSaveState("dirty");
  }

  const hasEmptyNames = draft.some(t => !t.name.trim());
  const hasDuplicateNames = new Set(draft.map(t => t.name.trim().toLowerCase())).size !== draft.length && draft.length > 0;
  const hasInvalidAmounts = draft.some(t => !t.amount_paise || t.amount_paise < 100);
  const canSave = isDirty && !hasEmptyNames && !hasDuplicateNames && !hasInvalidAmounts;

  async function handleSave() {
    if (!canSave) return;
    setSaveState("saving");
    setError(null);
    try {
      const cleaned = draft.filter(t => t.name.trim());
      await saveBookingTypes(cleaned);
      setTypes(cleaned);
      setDraft(cleaned);
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setSaveState("dirty");
    }
  }

  return (
    <div className="card rounded-3xl animate-slide-up">
      <button
        type="button"
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center gap-3 text-left"
      >
        <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 bg-emerald-50">
          <CalendarCheck size={18} className="text-emerald-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="font-display font-bold text-ink" style={{ fontSize: "1rem", letterSpacing: "-0.02em" }}>
              Booking Types
            </h2>
            {types.length > 0 ? (
              <span className="badge badge-green inline-flex items-center gap-1">
                <CheckCircle2 size={10} /> {types.length} type{types.length !== 1 ? "s" : ""}
              </span>
            ) : (
              <span className="badge badge-gray">Default pricing</span>
            )}
          </div>
          <p className="font-body text-sm text-ink-muted mt-0.5">
            Define booking types with different prices. When multiple types exist, WhatsApp users choose before booking.
          </p>
        </div>
        <ChevronDown
          size={18}
          className={`text-ink-muted transition-transform flex-shrink-0 ${collapsed ? "" : "rotate-180"}`}
        />
      </button>

      {!collapsed && (
        <>
          {error && (
            <div className="mt-4 flex items-center gap-2 p-3 rounded-xl bg-red-50 text-red-700 border border-red-100">
              <AlertCircle size={14} />
              <span className="font-body text-sm">{error}</span>
            </div>
          )}

          <div className="mt-6 space-y-3">
            {draft.length === 0 && (
              <div className="p-4 rounded-2xl bg-surface-subtle border border-border-subtle text-center">
                <p className="font-body text-sm text-ink-muted">
                  No booking types configured. Using default flat pricing (₹500).
                </p>
                <p className="font-body text-xs text-ink-muted mt-1">
                  Add types below to offer multiple booking options.
                </p>
              </div>
            )}

            {draft.map((bt, i) => (
              <div
                key={i}
                className="flex items-center gap-3 p-3 rounded-2xl bg-surface-subtle border border-border-subtle"
              >
                <div className="flex-1 min-w-0 grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-label text-[11px] font-medium text-ink-muted uppercase tracking-wide">
                      Name
                    </label>
                    <input
                      type="text"
                      value={bt.name}
                      onChange={e => updateType(i, "name", e.target.value)}
                      placeholder="e.g. Standard Pooja"
                      className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm font-body text-ink placeholder:text-ink-muted/40 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 transition"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-label text-[11px] font-medium text-ink-muted uppercase tracking-wide">
                      Amount (₹)
                    </label>
                    <input
                      type="number"
                      min={1}
                      step={1}
                      value={bt.amount_paise / 100}
                      onChange={e => {
                        const rupees = parseFloat(e.target.value) || 0;
                        updateType(i, "amount_paise", Math.round(rupees * 100));
                      }}
                      placeholder="500"
                      className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm font-body text-ink font-mono placeholder:text-ink-muted/40 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 transition"
                    />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeType(i)}
                  className="p-2 rounded-xl text-ink-muted hover:text-red-600 hover:bg-red-50 transition flex-shrink-0"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}

            <button
              type="button"
              onClick={addType}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border-2 border-dashed border-border-subtle text-ink-muted hover:border-primary/40 hover:text-primary transition font-label text-sm font-semibold"
            >
              <Plus size={16} />
              Add Booking Type
            </button>

            {hasEmptyNames && draft.length > 0 && (
              <p className="text-[11px] text-amber-600 font-body font-medium pl-1">
                All booking types need a name.
              </p>
            )}
            {hasDuplicateNames && (
              <p className="text-[11px] text-amber-600 font-body font-medium pl-1">
                Booking type names must be unique.
              </p>
            )}
          </div>

          <div className="mt-6 flex items-center justify-between border-t border-border-subtle pt-5 gap-3 flex-wrap">
            <div className="min-h-[20px]">
              {saveState === "saved" && (
                <span className="inline-flex items-center gap-1.5 text-emerald-600 font-body text-sm font-medium">
                  <CheckCircle2 size={15} /> Saved successfully
                </span>
              )}
              {saveState === "dirty" && (
                <span className="text-[11px] text-amber-600 font-body font-medium">Unsaved changes</span>
              )}
              {saveState === "idle" && (
                <span className="text-[11px] text-ink-muted font-body">
                  {types.length > 0
                    ? `${types.length} type${types.length !== 1 ? "s" : ""} configured`
                    : "Using default ₹500 flat pricing"
                  }
                </span>
              )}
            </div>
            <button
              onClick={handleSave}
              disabled={!canSave || saveState === "saving" || saveState === "saved"}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all ${
                saveState === "saved"
                  ? "bg-emerald-100 text-emerald-700 cursor-default"
                  : canSave
                  ? "bg-primary text-white hover:bg-primary/90"
                  : "bg-surface-subtle text-ink-muted cursor-default"
              }`}
            >
              {saveState === "saving" ? (
                <><Loader2 size={14} className="animate-spin" />Saving…</>
              ) : saveState === "saved" ? (
                <><CheckCircle2 size={14} />Saved</>
              ) : (
                <><Save size={14} />Save Changes</>
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
