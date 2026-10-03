"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, Store } from "lucide-react";
import { toast } from "sonner";
import { api, type AutoMessageEvent, type AutoMessageProduct, type AutoMessageSend } from "@/lib/api";
import { EVENT_LABEL, STATUS_STYLE, formatWhen, inputCls, primaryBtn, reasonText } from "./shared";

/** Built for a phone at the billing counter: big inputs, one tap to save. */
export function CounterTab() {
  const [products, setProducts] = useState<AutoMessageProduct[]>([]);
  const [recent, setRecent] = useState<AutoMessageSend[]>([]);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [productId, setProductId] = useState("");
  const [event, setEvent] = useState<AutoMessageEvent>("purchased");
  const [saving, setSaving] = useState(false);
  const [last, setLast] = useState<{ ok: boolean; text: string } | null>(null);

  function loadRecent() {
    api.autoMessages
      .counterRecent()
      .then((r) => setRecent(r.sends.slice(0, 8)))
      .catch(() => setRecent([]));
  }

  useEffect(() => {
    api.autoMessages
      .counterProducts()
      .then((r) => setProducts(r.products))
      .catch(() => setProducts([]));
    loadRecent();
  }, []);

  const digits = phone.replace(/\D/g, "");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (digits.length < 10) {
      toast.error("Enter a 10-digit mobile number");
      return;
    }
    setSaving(true);
    try {
      const r = await api.autoMessages.quickAdd({
        phone,
        name: name.trim() || undefined,
        event,
        catalog_item_id: productId || null,
      });
      const why = reasonText(r.message_status, r.reason);
      setLast({
        ok: r.message_status === "sent" || r.message_status === "queued",
        text:
          r.message_status === "sent"
            ? `Saved and WhatsApp sent to ${phone}.`
            : r.message_status === "queued"
              ? `Saved. WhatsApp will go to ${phone} shortly.`
              : `Saved the customer. ${why ?? "No WhatsApp sent."}`,
      });
      setPhone("");
      setName("");
      loadRecent();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,440px)_1fr]">
      <form onSubmit={submit} className="space-y-4 rounded-[24px] border border-border-subtle bg-white p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Store size={18} />
          </span>
          <div>
            <h3 className="font-display text-base font-bold text-ink">Add a customer at the counter</h3>
            <p className="mt-0.5 font-body text-xs text-ink-secondary">
              Ask: &ldquo;Can we send your bill and offers on WhatsApp?&rdquo; Then enter their number.
            </p>
          </div>
        </div>

        <div className="flex gap-1 rounded-xl border border-border bg-surface-subtle p-1">
          {(["purchased", "interested"] as AutoMessageEvent[]).map((ev) => (
            <button
              key={ev}
              type="button"
              onClick={() => setEvent(ev)}
              className={`flex-1 rounded-lg px-3 py-2 font-label text-xs font-bold transition-all ${
                event === ev ? "bg-white text-ink shadow-sm" : "text-ink-muted hover:text-ink"
              }`}
            >
              {ev === "purchased" ? "Bought something" : "Just enquiring"}
            </button>
          ))}
        </div>

        <label className="block space-y-1">
          <span className="font-body text-xs font-semibold text-ink">WhatsApp number</span>
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            inputMode="tel"
            autoComplete="off"
            placeholder="98765 43210"
            className={`${inputCls} py-3 text-lg tracking-wide`}
            required
          />
        </label>
        <label className="block space-y-1">
          <span className="font-body text-xs font-semibold text-ink">
            Name <span className="font-normal text-ink-muted">(optional)</span>
          </span>
          <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" className={`${inputCls} py-2.5`} />
        </label>
        <label className="block space-y-1">
          <span className="font-body text-xs font-semibold text-ink">
            Product <span className="font-normal text-ink-muted">(optional)</span>
          </span>
          <select value={productId} onChange={(e) => setProductId(e.target.value)} className={`${inputCls} py-2.5`}>
            <option value="">—</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <button type="submit" disabled={saving || digits.length < 10} className={`${primaryBtn} w-full py-3 text-sm`}>
          {saving ? "Saving…" : "Save & send WhatsApp"}
        </button>

        {last && (
          <p
            role="status"
            className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 font-body text-xs ${
              last.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"
            }`}
          >
            {last.ok && <CheckCircle2 size={14} className="mt-px shrink-0" />}
            {last.text}
          </p>
        )}
      </form>

      <section className="rounded-[24px] border border-border-subtle bg-white p-5 sm:p-6">
        <h3 className="font-display text-sm font-bold text-ink">Added at the counter recently</h3>
        {recent.length === 0 ? (
          <p className="mt-6 text-center font-body text-sm text-ink-muted">No one yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-border-subtle">
            {recent.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate font-body text-sm font-semibold text-ink">{s.name || s.phone}</p>
                  <p className="truncate font-body text-xs text-ink-muted">
                    {s.name ? `${s.phone} · ` : ""}
                    {EVENT_LABEL[s.event]}
                    {s.product_raw ? ` · ${s.product_raw}` : ""} · {formatWhen(s.created_at)}
                  </p>
                </div>
                <span className={`shrink-0 rounded-full border px-2 py-0.5 font-label text-[10px] font-bold ${STATUS_STYLE[s.status].cls}`}>
                  {STATUS_STYLE[s.status].label}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
