"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, AlertCircle, AlertTriangle, Info, CheckCircle2 } from "lucide-react";
import { operatorFetch, relTime } from "@/lib/operator";

type AlertSeverity = "critical" | "warning" | "info";

interface OperatorAlert {
  id: string;
  severity: AlertSeverity;
  title: string;
  detail: string;
  tenant_id?: string | null;
  tenant_name?: string | null;
  source: string;
  created_at: string;
  href?: string | null;
}

const SEVERITY_ORDER: Record<AlertSeverity, number> = { critical: 0, warning: 1, info: 2 };

const SEVERITY_STYLE: Record<AlertSeverity, { badge: string; icon: typeof AlertCircle; iconClass: string }> = {
  critical: { badge: "bg-red-50 text-danger", icon: AlertCircle, iconClass: "text-danger" },
  warning: { badge: "bg-warning/10 text-warning", icon: AlertTriangle, iconClass: "text-warning" },
  info: { badge: "bg-surface-mid text-ink-secondary", icon: Info, iconClass: "text-ink-muted" },
};

const POLL_INTERVAL_MS = 60_000;

export function AlertBell() {
  const router = useRouter();
  const [alerts, setAlerts] = useState<OperatorAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await operatorFetch<{ data: OperatorAlert[] }>("/api/v1/operator/alerts");
      setAlerts(res.data || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load alerts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const criticalCount = alerts.filter((a) => a.severity === "critical").length;
  const badgeCount = criticalCount > 0 ? criticalCount : alerts.length;
  const sorted = [...alerts].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);

  function handleAlertClick(alert: OperatorAlert) {
    setOpen(false);
    if (alert.href) {
      router.push(alert.href);
    } else if (alert.tenant_id) {
      router.push(`/operator/client/${alert.tenant_id}`);
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={`Alerts${badgeCount > 0 ? ` (${badgeCount} unread)` : ""}`}
        aria-expanded={open}
        aria-haspopup="true"
        className="relative flex items-center justify-center w-[34px] h-[34px] rounded-lg border border-border text-ink-secondary hover:bg-surface-mid hover:text-ink transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <Bell size={16} />
        {badgeCount > 0 && (
          <span
            className={`absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full flex items-center justify-center text-[10px] font-bold text-white ring-2 ring-white ${
              criticalCount > 0 ? "bg-danger" : "bg-warning"
            }`}
          >
            {badgeCount > 99 ? "99+" : badgeCount}
          </span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-2 w-96 max-h-[28rem] overflow-hidden flex flex-col rounded-card border border-border bg-white shadow-xl z-50 animate-in fade-in slide-in-from-top-2 duration-150"
        >
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-bold text-ink">Alert Center</h3>
            {alerts.length > 0 && (
              <span className="text-[11px] text-ink-muted">{alerts.length} active</span>
            )}
          </div>

          <div className="overflow-y-auto flex-1">
            {loading ? (
              <div className="py-10 text-center text-sm text-ink-muted">Loading…</div>
            ) : error ? (
              <div className="py-10 px-4 text-center text-sm text-danger">{error}</div>
            ) : sorted.length === 0 ? (
              <div className="py-10 px-4 text-center flex flex-col items-center gap-2 text-sm text-ink-muted">
                <CheckCircle2 size={28} className="text-success" />
                You&apos;re all caught up
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {sorted.map((alert) => {
                  const style = SEVERITY_STYLE[alert.severity];
                  const Icon = style.icon;
                  const clickable = Boolean(alert.href || alert.tenant_id);
                  return (
                    <li key={alert.id}>
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => handleAlertClick(alert)}
                        disabled={!clickable}
                        className={`w-full text-left px-4 py-3 flex gap-3 transition-colors ${
                          clickable ? "hover:bg-surface-mid cursor-pointer" : "cursor-default"
                        }`}
                      >
                        <div className={`shrink-0 mt-0.5 w-7 h-7 rounded-full flex items-center justify-center ${style.badge}`}>
                          <Icon size={14} className={style.iconClass} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-xs font-semibold text-ink truncate">{alert.title}</p>
                            <span className="shrink-0 text-[10px] text-ink-muted">{relTime(alert.created_at)}</span>
                          </div>
                          <p className="text-[11px] text-ink-secondary mt-0.5 line-clamp-2">{alert.detail}</p>
                          {alert.tenant_name && (
                            <p className="text-[10px] text-ink-muted mt-1">{alert.tenant_name}</p>
                          )}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
