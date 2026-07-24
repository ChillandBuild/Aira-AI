"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { MetaAdsPerformanceTab } from "./MetaAdsPerformanceTab";
import { MetaAdsAnalyticsTab } from "./MetaAdsAnalyticsTab";

export function MetaAdsClient() {
  // Tab is driven by the shared AppHeader via the ?tab= query param
  // (same pattern as Outbound Leads): no ?tab → Ad Performance, ?tab=analytics → Analytics.
  const searchParams = useSearchParams();
  const tab = searchParams.get("tab") === "analytics" ? "analytics" : "performance";

  // Date range is shared across both tabs.
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  return (
    <div className="p-6 md:p-8">
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
