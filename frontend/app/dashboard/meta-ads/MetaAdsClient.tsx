"use client";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { MetaAdsPerformanceTab } from "./MetaAdsPerformanceTab";
import { MetaAdsAnalyticsTab } from "./MetaAdsAnalyticsTab";

type Tab = "performance" | "analytics";

export function MetaAdsClient() {
  const [tab, setTab] = useState<Tab>("performance");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const pill = (t: Tab, label: string) => (
    <button
      onClick={() => setTab(t)}
      className={cn(
        "px-4 py-2 rounded-full font-label text-sm font-bold transition-all",
        tab === t ? "bg-primary text-white shadow-sm" : "text-on-surface-muted hover:bg-surface-low",
      )}
    >
      {label}
    </button>
  );

  return (
    <div className="p-6 md:p-8">
      <header className="mb-6">
        <h1 className="font-display text-2xl font-bold text-on-surface">Meta Ads</h1>
        <p className="font-body text-sm text-on-surface-muted mt-1">
          Full-account ad performance and lead-quality analytics across your Meta campaigns.
        </p>
      </header>

      <div className="mb-5 flex flex-wrap items-center gap-2 rounded-full bg-surface-low/60 p-1 w-fit">
        {pill("performance", "Ad Performance")}
        {pill("analytics", "Analytics")}
      </div>

      {tab === "performance" ? (
        <MetaAdsPerformanceTab dateFrom={dateFrom} dateTo={dateTo}
          setDateFrom={setDateFrom} setDateTo={setDateTo} />
      ) : (
        <MetaAdsAnalyticsTab dateFrom={dateFrom} dateTo={dateTo}
          setDateFrom={setDateFrom} setDateTo={setDateTo} />
      )}
    </div>
  );
}
