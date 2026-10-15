import Link from "next/link";
import { AdPerformanceTab } from "./AdPerformanceTab";
import { AllAdsTab } from "./AllAdsTab";

const TABS: { view: "whatsapp" | "all"; href: string; label: string }[] = [
  { view: "whatsapp", href: "/dashboard/meta-ads", label: "WhatsApp ads" },
  { view: "all", href: "/dashboard/meta-ads/all-ads", label: "All ads" },
];

export function MetaAdsClient({ view = "whatsapp" }: { view?: "whatsapp" | "all" }) {
  return (
    <div>
      <nav aria-label="Meta ads views" className="mb-5 inline-flex gap-1 rounded-xl border border-[#e2e8f0] bg-[#f8fafc] p-1">
        {TABS.map((tab) => {
          const active = tab.view === view;
          return (
            <Link
              key={tab.view}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              className={
                active
                  ? "flex items-center justify-center rounded-lg bg-white px-4 py-2 font-label text-xs font-bold text-primary shadow-sm transition-all"
                  : "flex items-center justify-center rounded-lg px-4 py-2 font-label text-xs font-bold text-[#64748b] transition-all hover:text-[#0A1528]"
              }
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      {view === "all" ? <AllAdsTab /> : <AdPerformanceTab />}
    </div>
  );
}
