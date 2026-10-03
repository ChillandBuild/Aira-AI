"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type AutoMessageEvent,
  type AutoMessageProduct,
  type AutoMessageRule,
  type AutoMessageTemplate,
  type AutoMessageVariable,
} from "@/lib/api";
import { DELAYS, EVENT_LABEL, VAR_SOURCES, inputCls, primaryBtn, splitBody } from "./shared";

const ANY = "__any__";

function defaultVariables(count: number): AutoMessageVariable[] {
  const defaults: AutoMessageVariable[] = [
    { source: "first_name", fallback: "there" },
    { source: "product", fallback: "our products" },
  ];
  return Array.from({ length: count }, (_, i) => defaults[i] ?? { source: "text", value: "" });
}

function VariableRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: AutoMessageVariable;
  onChange: (v: AutoMessageVariable) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-2 rounded-xl border border-border-subtle bg-surface-subtle p-3 sm:grid-cols-[72px_1fr_1fr] sm:items-center">
      <span className="font-mono text-xs font-bold text-primary">{label}</span>
      <select
        value={value.source}
        onChange={(e) => onChange({ ...value, source: e.target.value as AutoMessageVariable["source"] })}
        className={inputCls}
        aria-label={`What fills ${label}`}
      >
        {VAR_SOURCES.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </select>
      {value.source === "text" ? (
        <input
          value={value.value ?? ""}
          onChange={(e) => onChange({ ...value, value: e.target.value })}
          placeholder="Text to show"
          maxLength={200}
          className={inputCls}
        />
      ) : (
        <div className="grid grid-cols-1 gap-2">
          {value.source === "extra" && (
            <input
              value={value.key ?? ""}
              onChange={(e) => onChange({ ...value, key: e.target.value })}
              placeholder="Field name, e.g. order_id"
              maxLength={50}
              className={inputCls}
            />
          )}
          <input
            value={value.fallback ?? ""}
            onChange={(e) => onChange({ ...value, fallback: e.target.value })}
            placeholder="If empty, use…"
            maxLength={200}
            className={inputCls}
          />
        </div>
      )}
    </div>
  );
}

export function RuleEditor({
  event,
  rule,
  rules,
  templates,
  products,
  canEditAliases,
  onClose,
  onSaved,
}: {
  event: AutoMessageEvent;
  rule: AutoMessageRule | null;
  rules: AutoMessageRule[];
  templates: AutoMessageTemplate[];
  products: AutoMessageProduct[];
  canEditAliases: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const used = useMemo(
    () => new Set(rules.filter((r) => r.event === event && r.id !== rule?.id).map((r) => r.catalog_item_id ?? ANY)),
    [rules, event, rule]
  );
  const firstFree = used.has(ANY) ? products.find((p) => !used.has(p.id))?.id ?? ANY : ANY;
  const [productId, setProductId] = useState<string>(rule ? rule.catalog_item_id ?? ANY : firstFree);
  const [templateId, setTemplateId] = useState<string>(rule?.template_id ?? "");
  const [delay, setDelay] = useState<number>(rule?.delay_minutes ?? (event === "interested" ? 5 : 0));
  const [variables, setVariables] = useState<AutoMessageVariable[]>(rule?.variables ?? []);
  const [buttonParam, setButtonParam] = useState<AutoMessageVariable>(
    rule?.button_param ?? { source: "product", fallback: "" }
  );
  const product = products.find((p) => p.id === productId) ?? null;
  const [aliases, setAliases] = useState<string>((product?.aliases ?? []).join(", "));
  const [saving, setSaving] = useState(false);

  const template = templates.find((t) => t.id === templateId) ?? null;
  const vars = template
    ? variables.length === template.variable_count
      ? variables
      : [...variables, ...defaultVariables(template.variable_count)].slice(0, template.variable_count)
    : [];

  function pickProduct(id: string) {
    setProductId(id);
    setAliases((products.find((p) => p.id === id)?.aliases ?? []).join(", "));
  }

  function pickTemplate(id: string) {
    setTemplateId(id);
    const t = templates.find((x) => x.id === id);
    setVariables(defaultVariables(t?.variable_count ?? 0));
  }

  async function save() {
    if (!template) {
      toast.error("Pick a template");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        template_id: template.id,
        delay_minutes: delay,
        variables: vars,
        button_param: template.has_dynamic_button ? buttonParam : null,
      };
      if (rule) {
        await api.autoMessages.updateRule(rule.id, payload);
      } else {
        await api.autoMessages.createRule({
          ...payload,
          event,
          catalog_item_id: productId === ANY ? null : productId,
          enabled: true,
        });
      }
      if (product && canEditAliases) {
        const next = aliases.split(",").map((a) => a.trim()).filter(Boolean);
        if (next.join("|") !== product.aliases.join("|")) await api.autoMessages.setAliases(product.id, next);
      }
      toast.success("Saved");
      onSaved();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-dialog flex items-end justify-center bg-black/50 p-0 backdrop-blur-sm sm:items-center sm:p-4">
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl sm:rounded-3xl">
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="font-display text-lg font-bold text-ink">{rule ? "Edit message" : "New message"}</h2>
            <p className="font-body text-xs text-ink-secondary">When someone is: {EVENT_LABEL[event]}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-full p-2 text-ink-muted hover:bg-surface-subtle hover:text-ink">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {/* 1. Product */}
          <section className="space-y-2">
            <label className="font-label text-xs font-bold uppercase tracking-wide text-ink-secondary">1 · For which product?</label>
            <select
              value={productId}
              disabled={!!rule}
              onChange={(e) => pickProduct(e.target.value)}
              className={inputCls}
            >
              <option value={ANY} disabled={used.has(ANY)}>
                Any other product (default){used.has(ANY) ? " — already set up" : ""}
              </option>
              {products.map((p) => (
                <option key={p.id} value={p.id} disabled={used.has(p.id)}>
                  {p.name}
                  {used.has(p.id) ? " — already set up" : ""}
                </option>
              ))}
            </select>
            <p className="font-body text-xs text-ink-muted">
              {productId === ANY
                ? "Goes to everyone whose product has no message of its own, including names Aira doesn't recognise."
                : "Only people interested in this product get this message."}
            </p>
            {product && canEditAliases && (
              <div className="space-y-1 pt-1">
                <label className="font-body text-xs font-semibold text-ink">Other names customers might use</label>
                <input
                  value={aliases}
                  onChange={(e) => setAliases(e.target.value)}
                  placeholder={`e.g. ${product.name.toLowerCase()} s, new ${product.name.toLowerCase()}`}
                  className={inputCls}
                />
                <p className="font-body text-[11px] text-ink-muted">Separate with commas. Spelling and capitals don&apos;t matter.</p>
              </div>
            )}
          </section>

          {/* 2. Template */}
          <section className="space-y-2">
            <label className="font-label text-xs font-bold uppercase tracking-wide text-ink-secondary">2 · Which WhatsApp template?</label>
            {templates.length === 0 ? (
              <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 font-body text-xs text-amber-800">
                You have no approved templates yet.{" "}
                <Link href="/dashboard/templates" className="font-semibold underline">
                  Create one under Templates
                </Link>{" "}
                and come back once Meta approves it.
              </p>
            ) : (
              <select value={templateId} onChange={(e) => pickTemplate(e.target.value)} className={inputCls}>
                <option value="">Choose a template…</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                    {t.category ? ` · ${t.category.toLowerCase()}` : ""}
                  </option>
                ))}
              </select>
            )}
            {template && (
              <div className="rounded-2xl bg-[#e7ddd3] p-3">
                <div className="max-w-[92%] rounded-xl rounded-tl-sm bg-white px-3 py-2 shadow-sm">
                  {template.header_media_type && (
                    <div className="mb-2 flex h-20 items-center justify-center rounded-lg bg-surface-mid font-body text-[11px] text-ink-muted">
                      {template.header_media_type === "IMAGE"
                        ? product
                          ? `Photo of ${product.name} from Products`
                          : "Product photo (or the template's image)"
                        : `Template ${template.header_media_type.toLowerCase()}`}
                    </div>
                  )}
                  <p className="whitespace-pre-wrap font-body text-[13px] leading-relaxed text-ink">
                    {splitBody(template.body_text).map((part, i) =>
                      "text" in part ? (
                        <span key={i}>{part.text}</span>
                      ) : (
                        <span key={i} className="rounded bg-primary/10 px-1 font-semibold text-primary">
                          {VAR_SOURCES.find((s) => s.id === vars[part.variable - 1]?.source)?.label ?? `{{${part.variable}}}`}
                        </span>
                      )
                    )}
                  </p>
                </div>
                {template.buttons.length > 0 && (
                  <div className="mt-1 flex max-w-[92%] flex-col gap-1">
                    {template.buttons.map((b) => (
                      <span key={b} className="rounded-xl bg-white py-1.5 text-center font-body text-[13px] font-medium text-sky-600 shadow-sm">
                        {b}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

          {/* 3. Fill-ins */}
          {template && (vars.length > 0 || template.has_dynamic_button) && (
            <section className="space-y-2">
              <label className="font-label text-xs font-bold uppercase tracking-wide text-ink-secondary">3 · Fill in the blanks</label>
              {vars.map((v, i) => (
                <VariableRow
                  key={i}
                  label={`{{${i + 1}}}`}
                  value={v}
                  onChange={(next) => setVariables(vars.map((x, j) => (j === i ? next : x)))}
                />
              ))}
              {template.has_dynamic_button && (
                <>
                  <p className="pt-1 font-body text-xs text-ink-secondary">The end of the button&apos;s link:</p>
                  <VariableRow label="Button" value={buttonParam} onChange={setButtonParam} />
                </>
              )}
            </section>
          )}

          {/* 4. Timing */}
          <section className="space-y-2">
            <label className="font-label text-xs font-bold uppercase tracking-wide text-ink-secondary">
              {template && (vars.length > 0 || template.has_dynamic_button) ? "4" : "3"} · When to send
            </label>
            <div className="flex flex-wrap gap-2">
              {DELAYS.map((d) => (
                <button
                  key={d.minutes}
                  type="button"
                  onClick={() => setDelay(d.minutes)}
                  className={`rounded-full border px-3 py-1.5 font-label text-xs font-semibold transition-all ${
                    delay === d.minutes
                      ? "border-primary bg-primary text-white"
                      : "border-border bg-white text-ink-secondary hover:border-primary/40 hover:text-primary"
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
            <p className="font-body text-xs text-ink-muted">
              A short wait (like Ather&apos;s 5 minutes) feels natural after a website visit. Thank-you messages work best instantly.
            </p>
          </section>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border px-6 py-4">
          <button type="button" onClick={onClose} className="rounded-full px-4 py-2 font-label text-xs font-semibold text-ink-secondary hover:text-ink">
            Cancel
          </button>
          <button type="button" onClick={save} disabled={saving || !template} className={primaryBtn}>
            {saving ? "Saving…" : "Save message"}
          </button>
        </div>
      </div>
    </div>
  );
}
