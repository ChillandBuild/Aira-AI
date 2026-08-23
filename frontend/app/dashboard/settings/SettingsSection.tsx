"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";
import { CheckCircle2, ChevronDown, ChevronsDownUp, ChevronsUpDown, Loader2, Save } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ *
 * Accordion group
 *
 * Sections keep their own open state when rendered standalone. Wrapped
 * in <SettingsAccordion>, they hand that state to the group so the
 * toolbar can expand/collapse everything at once. Every section starts
 * closed — the settings tabs are long, and a wall of open forms was the
 * thing that made them unreadable.
 * ------------------------------------------------------------------ */

type AccordionCtx = {
  isOpen: (id: string) => boolean;
  toggle: (id: string) => void;
  register: (id: string) => () => void;
};

const Ctx = createContext<AccordionCtx | null>(null);

export function SettingsAccordion({ children }: { children: React.ReactNode }) {
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set());
  const [ids, setIds] = useState<string[]>([]);

  const register = useCallback((id: string) => {
    setIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    return () => setIds((prev) => prev.filter((x) => x !== id));
  }, []);

  const toggle = useCallback((id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const isOpen = useCallback((id: string) => openIds.has(id), [openIds]);

  const value = useMemo<AccordionCtx>(() => ({ isOpen, toggle, register }), [isOpen, toggle, register]);

  const allOpen = ids.length > 0 && ids.every((id) => openIds.has(id));

  return (
    <Ctx.Provider value={value}>
      <div className="space-y-4 sm:space-y-5">
        {ids.length > 1 && (
          <div className="flex items-center justify-between gap-3 px-1">
            <p className="font-label text-[11px] font-bold uppercase tracking-[0.14em] text-ink-muted">
              {ids.length} section{ids.length === 1 ? "" : "s"}
              {openIds.size > 0 && (
                <span className="ml-2 font-mono text-[10px] font-semibold normal-case tracking-normal text-primary">
                  {openIds.size} open
                </span>
              )}
            </p>
            <button
              type="button"
              onClick={() => setOpenIds(allOpen ? new Set() : new Set(ids))}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-white px-3 py-1.5 font-label text-[11px] font-bold text-ink-secondary transition-all hover:border-primary/40 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
            >
              {allOpen ? <ChevronsDownUp size={13} /> : <ChevronsUpDown size={13} />}
              {allOpen ? "Collapse all" : "Expand all"}
            </button>
          </div>
        )}
        {children}
      </div>
    </Ctx.Provider>
  );
}

/* ------------------------------------------------------------------ */

export type SectionAccent = "violet" | "amber" | "sky" | "emerald";

const ACCENTS: Record<SectionAccent, { tile: string; icon: string; rail: string; glow: string }> = {
  violet: {
    tile: "bg-gradient-to-br from-[#f5f3ff] to-[#e9e2ff] ring-[#ddd4fb]",
    icon: "text-primary",
    rail: "from-primary/70 via-violet-400/60 to-transparent",
    glow: "group-hover/section:shadow-[0_0_0_4px_rgba(91,33,182,0.06)]",
  },
  amber: {
    tile: "bg-gradient-to-br from-[#fffbeb] to-[#fdefc8] ring-[#f8e3ae]",
    icon: "text-amber-600",
    rail: "from-amber-500/70 via-amber-300/60 to-transparent",
    glow: "group-hover/section:shadow-[0_0_0_4px_rgba(217,119,6,0.06)]",
  },
  sky: {
    tile: "bg-gradient-to-br from-[#f0f9ff] to-[#dcedfd] ring-[#c3e0f8]",
    icon: "text-sky-600",
    rail: "from-sky-500/70 via-sky-300/60 to-transparent",
    glow: "group-hover/section:shadow-[0_0_0_4px_rgba(2,132,199,0.06)]",
  },
  emerald: {
    tile: "bg-gradient-to-br from-[#ecfdf5] to-[#d3f5e5] ring-[#b6ecd3]",
    icon: "text-emerald-600",
    rail: "from-emerald-500/70 via-emerald-300/60 to-transparent",
    glow: "group-hover/section:shadow-[0_0_0_4px_rgba(5,150,105,0.06)]",
  },
};

export type SectionStatus = {
  label: string;
  tone: "on" | "off" | "warn";
};

const STATUS_STYLES: Record<SectionStatus["tone"], string> = {
  on: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  off: "bg-[#f0ece4] text-ink-secondary ring-border",
  warn: "bg-amber-50 text-amber-700 ring-amber-200",
};

export function SettingsSection({
  id,
  icon: Icon,
  title,
  description,
  accent = "violet",
  status,
  dirty = false,
  defaultOpen = false,
  children,
}: {
  /** Stable id — required for the group toolbar to drive this section. */
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  accent?: SectionAccent;
  status?: SectionStatus;
  /** Shows an "Unsaved" marker on the header so it survives collapsing. */
  dirty?: boolean;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const group = useContext(Ctx);
  const [localOpen, setLocalOpen] = useState(defaultOpen);
  const panelId = `${useId()}-panel`;
  const a = ACCENTS[accent];

  const register = group?.register;
  useEffect(() => {
    if (!register) return;
    return register(id);
  }, [register, id]);

  const open = group ? group.isOpen(id) : localOpen;
  const onToggle = () => (group ? group.toggle(id) : setLocalOpen((o) => !o));

  return (
    <section
      className={cn(
        "group/section relative overflow-hidden rounded-2xl border bg-white transition-all duration-300 sm:rounded-3xl",
        open
          ? "border-primary/20 shadow-[0_2px_4px_rgba(28,25,23,0.03),0_18px_40px_-24px_rgba(28,25,23,0.28)]"
          : "border-border/70 shadow-[0_1px_2px_rgba(28,25,23,0.03)] hover:border-border hover:shadow-[0_2px_4px_rgba(28,25,23,0.04),0_14px_32px_-24px_rgba(28,25,23,0.25)]"
      )}
    >
      {/* Accent rail — fades in only while the section is open */}
      <span
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r transition-opacity duration-300",
          a.rail,
          open ? "opacity-100" : "opacity-0"
        )}
      />

      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        className={cn(
          "flex w-full items-start gap-3.5 p-4 text-left transition-colors duration-200 sm:gap-4 sm:p-6",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/30",
          open ? "bg-white" : "hover:bg-surface-subtle/70"
        )}
      >
        <span
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ring-1 transition-all duration-300 sm:h-11 sm:w-11",
            a.tile,
            a.glow
          )}
        >
          <Icon size={18} className={a.icon} strokeWidth={2} />
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <h2 className="font-display text-[0.9375rem] font-bold tracking-[-0.02em] text-ink sm:text-base">
              {title}
            </h2>
            {status && (
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-label text-[10px] font-bold uppercase tracking-wider ring-1 ring-inset",
                  STATUS_STYLES[status.tone]
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    status.tone === "on"
                      ? "bg-emerald-500"
                      : status.tone === "warn"
                      ? "bg-amber-500"
                      : "bg-ink-muted"
                  )}
                />
                {status.label}
              </span>
            )}
            {dirty && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2 py-0.5 font-label text-[10px] font-bold uppercase tracking-wider text-amber-700 ring-1 ring-inset ring-amber-200">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
                Unsaved
              </span>
            )}
          </span>
          <span
            className={cn(
              "mt-1 block max-w-2xl font-body text-[13px] leading-relaxed text-ink-secondary sm:text-sm",
              !open && "line-clamp-2"
            )}
          >
            {description}
          </span>
        </span>

        <span
          className={cn(
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-all duration-300",
            open
              ? "border-primary/25 bg-primary-light text-primary"
              : "border-border/80 bg-surface-subtle text-ink-muted group-hover/section:border-primary/25 group-hover/section:text-primary"
          )}
        >
          <ChevronDown
            size={16}
            className={cn("transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]", open && "rotate-180")}
          />
        </span>
      </button>

      {/* grid-rows 0fr → 1fr animates to the content's natural height */}
      <div
        id={panelId}
        role="region"
        className={cn(
          "grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        )}
      >
        {/* visibility (not display) keeps collapsed content out of the tab
            order without killing the closing animation */}
        <div
          className={cn(
            "overflow-hidden transition-[opacity,visibility] duration-300",
            open ? "visible opacity-100" : "invisible opacity-0"
          )}
        >
          <div className="border-t border-border-subtle px-4 pb-5 pt-5 sm:px-6 sm:pb-6 sm:pt-6">{children}</div>
        </div>
      </div>
    </section>
  );
}

/**
 * Footer used inside a section body: status text on the left, save button
 * on the right, separated by a hairline. Keeps every panel's save row
 * identical instead of five near-copies.
 */
export function SectionFooter({
  children,
  status,
}: {
  children: React.ReactNode;
  status?: React.ReactNode;
}) {
  return (
    <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle pt-5">
      <div className="min-h-[20px] flex items-center">{status}</div>
      {children}
    </div>
  );
}

/** Off/On segmented pill — the app's standard binary control. */
export function SwitchPill({
  on,
  onChange,
  disabled = false,
  labels = ["Off", "On"],
}: {
  on: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  labels?: [string, string];
}) {
  return (
    <div
      className={cn(
        "relative inline-flex shrink-0 select-none rounded-full border border-border/50 bg-border-subtle p-0.5",
        disabled && "opacity-50"
      )}
    >
      {([false, true] as const).map((value) => {
        const active = on === value;
        return (
          <button
            key={String(value)}
            type="button"
            disabled={disabled}
            aria-pressed={active}
            onClick={() => !active && onChange(value)}
            className={cn(
              "relative z-10 rounded-full px-3.5 py-1 font-label text-xs font-bold transition-all duration-300",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
              active
                ? value
                  ? "bg-gradient-to-r from-primary to-violet-500 text-white shadow-[0_2px_10px_rgba(91,33,182,0.28)]"
                  : "bg-white text-ink shadow-[0_2px_8px_rgba(28,25,23,0.08)]"
                : "text-ink-muted hover:text-ink-secondary",
              disabled && "cursor-not-allowed"
            )}
          >
            {value ? labels[1] : labels[0]}
          </button>
        );
      })}
    </div>
  );
}

export type SaveState = "idle" | "dirty" | "saving" | "saved";

/** The one Save button every settings panel uses. */
export function SaveButton({
  state,
  dirty,
  disabled = false,
  onClick,
}: {
  state: SaveState;
  dirty: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  const active = !disabled && dirty && state !== "saving" && state !== "saved";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!active}
      className={cn(
        "inline-flex items-center gap-2 rounded-xl px-4 py-2 font-label text-sm font-semibold transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
        state === "saved"
          ? "cursor-default bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200"
          : active
          ? "bg-gradient-to-br from-[#2e1065] to-primary text-white shadow-[0_6px_16px_-8px_rgba(91,33,182,0.7)] hover:shadow-[0_10px_22px_-8px_rgba(91,33,182,0.75)] hover:brightness-110 active:scale-[0.98]"
          : "cursor-default bg-surface-subtle text-ink-muted ring-1 ring-inset ring-border/70"
      )}
    >
      {state === "saving" ? (
        <>
          <Loader2 size={14} className="animate-spin" />
          Saving…
        </>
      ) : state === "saved" ? (
        <>
          <CheckCircle2 size={14} />
          Saved
        </>
      ) : (
        <>
          <Save size={14} />
          Save Changes
        </>
      )}
    </button>
  );
}

/** Left-hand status line in a SectionFooter: "Unsaved changes" / "Saved" / resting hint. */
export function SaveStatus({
  state,
  dirty,
  idleLabel,
}: {
  state: SaveState;
  dirty: boolean;
  idleLabel?: string;
}) {
  if (state === "saved") {
    return (
      <span className="inline-flex items-center gap-1.5 font-body text-sm font-medium text-emerald-600">
        <CheckCircle2 size={15} /> Saved successfully
      </span>
    );
  }
  if (dirty) {
    return (
      <span className="inline-flex items-center gap-1.5 font-body text-[11px] font-semibold text-amber-600">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
        Unsaved changes
      </span>
    );
  }
  return idleLabel ? <span className="font-body text-[11px] text-ink-muted">{idleLabel}</span> : null;
}
