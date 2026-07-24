"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { MetaAdsPerformanceTab } from "./MetaAdsPerformanceTab";
import { MetaAdsAnalyticsTab } from "./MetaAdsAnalyticsTab";
import { MetaAdsCreateTab } from "./MetaAdsCreateTab";

export function MetaAdsClient() {
  // Tab is driven by the shared AppHeader via the ?tab= query param
  // (same pattern as Outbound Leads): no ?tab → Ad Performance,
  // ?tab=create → Create, ?tab=analytics → Analytics.
  const searchParams = useSearchParams();
  const raw = searchParams.get("tab");
  const tab = raw === "analytics" ? "analytics" : raw === "create" ? "create" : "performance";

  // Date range is shared across the reporting tabs.
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  return (
    <div className="p-6 md:p-8">
      {tab === "create" ? (
        <MetaAdsCreateTab />
      ) : tab === "performance" ? (
        <MetaAdsPerformanceTab dateFrom={dateFrom} dateTo={dateTo}
          setDateFrom={setDateFrom} setDateTo={setDateTo} />
      ) : (
        <MetaAdsAnalyticsTab dateFrom={dateFrom} dateTo={dateTo}
          setDateFrom={setDateFrom} setDateTo={setDateTo} />
      )}
    </div>
  );
}
