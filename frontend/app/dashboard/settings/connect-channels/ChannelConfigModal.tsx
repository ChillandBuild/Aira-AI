"use client";
import { X, XCircle, CheckCircle2, Loader2, Zap, Save, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Portal, OutlinedField, SecretField, timeAgo } from "./ui";
import WebhookConfigGuide from "./WebhookConfigGuide";
import type { ActivateResult, ChannelConfig, ConnectionSource, SaveState, Setting, SettingsMap, WebhookHealth } from "./channels";

export default function ChannelConfigModal({
  channel,
  settings,
  drafts,
  tenantId,
  canManage,
  configured,
  isDirty,
  saveState,
  activating,
  activateResult,
  webhookHealth,
  connectionSource,
  onDraftChange,
  onSave,
  onActivate,
  onClose,
}: {
  channel: ChannelConfig;
  settings: Setting[];
  drafts: SettingsMap;
  tenantId: string | null;
  canManage: boolean;
  configured: boolean;
  isDirty: boolean;
  saveState: SaveState;
  activating: boolean;
  activateResult: ActivateResult | null;
  webhookHealth: WebhookHealth | null;
  connectionSource: ConnectionSource;
  onDraftChange: (key: string, value: string) => void;
  onSave: () => void;
  onActivate: () => void;
  onClose: () => void;
}) {
  const isModalDirty = isDirty;
  return (
        <Portal>
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/45 backdrop-blur-[3px] animate-fade-in">
            <div className="bg-surface rounded-card shadow-card w-full max-w-2xl max-h-[85vh] overflow-y-auto ring-1 ring-[#c4c7c7]/20 flex flex-col">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-border-subtle">
              <div className="flex items-center gap-3">
                <div className={cn("w-10 h-10 rounded-2xl flex items-center justify-center", channel.iconBg)}>
                  <channel.icon size={20} className={channel.iconColor} />
                </div>
                <div>
                  <h2 className="font-display text-lg font-bold text-ink">{channel.name} Settings</h2>
                  <p className="font-body text-xs text-ink-muted">
                    {channel.id === "meta_ads"
                      ? "Connect and validate the ad account used for WhatsApp reporting."
                      : "Set up credentials and subscription webhooks."}
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg hover:bg-surface-low transition-colors text-on-surface-muted hover:text-on-surface"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-6 overflow-y-auto flex-1">
              {connectionSource === "embedded" && (
                <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5">
                  <AlertCircle size={14} className="mt-0.5 shrink-0 text-amber-600" />
                  <p className="font-body text-xs text-amber-800">
                    This channel was connected through Meta. Saving your own credentials here replaces
                    the ones Meta provisioned. You can restore them by reconnecting from Embedded Onboarding.
                  </p>
                </div>
              )}
              {/* Dynamic Webhook Guide */}
              <WebhookConfigGuide channelId={channel.id} tenantId={tenantId} />

              {/* Form Fields */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 mb-2">
                  <h4 className="font-label font-bold text-ink text-xs uppercase tracking-wider">Credentials</h4>
                  <div className="h-px flex-1 bg-border-subtle" />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {channel.fields.map((field) => {
                    const meta = settings.find(s => s.key === field.key);
                    const draft = drafts[field.key] ?? "";
                    if (field.secret) {
                      return (
                        <SecretField
                           key={field.key}
                           label={field.label}
                           storedMask={meta?.display_value ?? "Not set"}
                           isSet={!!meta?.is_set}
                           newValue={draft}
                           onChange={v => onDraftChange(field.key, v)}
                           hint={field.hint}
                           disabled={!canManage}
                        />
                      );
                    }
                    return (
                      <OutlinedField
                        key={field.key}
                        label={field.label}
                        value={draft}
                        onChange={v => onDraftChange(field.key, v)}
                        placeholder={field.placeholder}
                        hint={field.hint}
                        disabled={!canManage}
                      />
                    );
                  })}
                </div>
              </div>

              {/* Token Alerts */}
              {(() => {
                const tokenAlert = webhookHealth?.token_alerts?.find(a => a.channel === channel.id);
                if (!tokenAlert) return null;
                return (
                  <div className="flex items-start gap-2.5 p-3.5 rounded-2xl border bg-red-50 border-red-200 text-red-800 text-xs font-body">
                    <XCircle size={14} className="flex-shrink-0 mt-0.5 text-red-500" />
                    <div>
                      <p className="font-semibold">Token invalid — connection broken</p>
                      <p className="mt-0.5 opacity-80">{tokenAlert.error} · Detected {timeAgo(tokenAlert.created_at)}</p>
                      <p className="mt-1 opacity-70">Update your access token above, click Save Changes, then click Validate &amp; Activate.</p>
                    </div>
                  </div>
                );
              })()}

              {/* Activation Result */}
              {activateResult && (
                <div className={cn("flex items-start gap-2.5 p-3.5 rounded-2xl border text-xs font-body",
                  activateResult.success
                    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                    : "bg-red-50 border-red-200 text-red-700"
                )}>
                  {activateResult.success
                    ? <CheckCircle2 size={14} className="flex-shrink-0 mt-0.5 text-emerald-600" />
                    : <XCircle size={14} className="flex-shrink-0 mt-0.5 text-red-500" />
                  }
                  <div>
                    <p className="font-semibold">{activateResult.message}</p>
                    {activateResult.detail && <p className="mt-0.5 opacity-80">{activateResult.detail}</p>}
                  </div>
                </div>
              )}

              {/* Modal Footer */}
              <div className="p-6 border-t border-border-subtle bg-surface-low flex items-center justify-between gap-3 flex-wrap">
                <div className="min-h-[20px]">
                  {saveState === "saved" && (
                    <span className="inline-flex items-center gap-1.5 text-emerald-600 font-body text-sm font-medium animate-fade-in">
                      <CheckCircle2 size={14} /> Saved successfully
                    </span>
                  )}
                  {!isModalDirty && saveState === "idle" && configured && (
                    <span className="text-[11px] text-ink-muted font-body">No unsaved changes</span>
                  )}
                  {isModalDirty && saveState !== "saved" && (
                    <span className="text-[11px] text-amber-600 font-body font-medium animate-fade-in">Unsaved changes</span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {channel.hasActivation && (
                    <button
                      type="button"
                      onClick={onActivate}
                      disabled={!canManage || activating || !configured}
                      title={!canManage ? "Read-only role" : !configured ? "Save required fields first" : channel.id === "meta_ads" ? "Validate token and ad account" : "Validate token and register webhook"}
                      className={cn("inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all border",
                        canManage && configured
                          ? "border-violet-300 text-violet-700 bg-violet-50 hover:bg-violet-100"
                          : "border-border text-ink-muted bg-surface-subtle cursor-not-allowed opacity-50"
                      )}
                    >
                      {activating ? (
                        <><Loader2 size={14} className="animate-spin" />Validating…</>
                      ) : (
                        <><Zap size={14} />{channel.id === "meta_ads" ? "Validate account" : "Validate & Activate"}</>
                      )}
                    </button>
                  )}

                  <button
                    onClick={onSave}
                    disabled={!canManage || saveState === "saving" || saveState === "saved" || !isModalDirty}
                    className={cn("inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all",
                      saveState === "saved"
                        ? "bg-emerald-100 text-emerald-700 cursor-default"
                        : canManage && isModalDirty
                        ? "bg-primary text-white hover:bg-primary/90"
                        : "bg-surface-subtle text-ink-muted cursor-default"
                    )}
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
              </div>

            </div>
          </div>
        </div>
        </Portal>
  );
}
