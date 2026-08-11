"use client";
import { X, Loader2, ArrowRight } from "lucide-react";
import { Portal } from "./ui";
import type { MetaBusinessAssets } from "./channels";

export default function MetaAssetPickerModal({
  assets,
  selectedPageId,
  selectedAdAccountId,
  onSelectPage,
  onSelectAdAccount,
  onConfirm,
  onDismiss,
  isBusy,
  error,
  canManage,
}: {
  assets: MetaBusinessAssets;
  selectedPageId: string;
  selectedAdAccountId: string;
  onSelectPage: (id: string) => void;
  onSelectAdAccount: (id: string) => void;
  onConfirm: () => void;
  onDismiss: () => void;
  isBusy: boolean;
  error: string | null;
  canManage: boolean;
}) {
  return (
    <Portal>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-[3px]">
        <div className="w-full max-w-xl overflow-hidden rounded-card bg-surface shadow-card ring-1 ring-[#c4c7c7]/20">
          <div className="flex items-start justify-between border-b border-border-subtle p-6">
            <div>
              <h2 className="font-display text-lg font-bold text-ink">Choose your Meta Business assets</h2>
              <p className="mt-1 font-body text-xs text-ink-muted">WhatsApp is ready. Choose the Facebook Page for Messenger and its linked Instagram account. Existing separately connected assets stay as they are.</p>
            </div>
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-lg p-1.5 text-on-surface-muted transition-colors hover:bg-surface-low hover:text-on-surface"
              aria-label="Close Meta asset selection"
            >
              <X size={18} />
            </button>
          </div>
          <div className="max-h-[70vh] space-y-5 overflow-y-auto p-6">
            {error && <p className="rounded-xl bg-red-50 px-3 py-2 font-body text-xs text-red-700">{error}</p>}
            <label className="block">
              <span className="font-label text-xs font-bold uppercase tracking-wider text-ink">Facebook Page <span className="text-red-600">*</span></span>
              <select value={selectedPageId} onChange={event => onSelectPage(event.target.value)} className="mt-2 w-full rounded-xl border border-border bg-white px-3 py-2.5 font-body text-sm text-ink" disabled={isBusy}>
                <option value="">Choose a Page</option>
                {assets.pages.map(page => <option key={page.id} value={page.id}>{page.name}{page.instagram_business_account ? " · Instagram linked" : ""}</option>)}
              </select>
              <p className="mt-1.5 font-body text-[11px] text-ink-muted">Messenger is connected to this Page. Its linked Instagram business account is connected automatically.</p>
            </label>
            <label className="block">
              <span className="font-label text-xs font-bold uppercase tracking-wider text-ink">Ad account <span className="font-normal normal-case text-ink-muted">(optional)</span></span>
              <select value={selectedAdAccountId} onChange={event => onSelectAdAccount(event.target.value)} className="mt-2 w-full rounded-xl border border-border bg-white px-3 py-2.5 font-body text-sm text-ink" disabled={isBusy}>
                <option value="">Do not connect an ad account</option>
                {assets.ad_accounts.map(account => <option key={account.id} value={account.id}>{account.name}{account.account_id ? ` · ${account.account_id}` : ""}{account.currency ? ` · ${account.currency}` : ""}</option>)}
              </select>
              <p className="mt-1.5 font-body text-[11px] text-ink-muted">Aira reads reporting data from this account. It cannot create, edit, or publish ads.</p>
            </label>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-border-subtle bg-surface-low p-5">
            <button type="button" onClick={onDismiss} className="rounded-xl px-3 py-2 font-label text-sm font-semibold text-ink-muted hover:bg-white">Cancel</button>
            <button type="button" onClick={onConfirm} disabled={!canManage || !selectedPageId || isBusy} className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 font-label text-sm font-bold text-white transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60">
              {isBusy ? <><Loader2 size={16} className="animate-spin" />Connecting…</> : <>Connect Meta Business <ArrowRight size={16} /></>}
            </button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
