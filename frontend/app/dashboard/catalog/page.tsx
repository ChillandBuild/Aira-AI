"use client";

import { useMemo, useState } from "react";
import {
  BarChart3,
  CheckCircle2,
  Image as ImageIcon,
  Package,
  Plus,
  Search,
  Sparkles,
  ToggleLeft,
  Upload,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuthRole } from "../contexts/AuthRoleContext";

type CatalogTab = "items" | "media" | "ai-rules" | "insights";

const TABS: { id: CatalogTab; label: string; icon: typeof Package }[] = [
  { id: "items", label: "Items", icon: Package },
  { id: "media", label: "Media", icon: ImageIcon },
  { id: "ai-rules", label: "AI Rules", icon: Sparkles },
  { id: "insights", label: "Insights", icon: BarChart3 },
];

const SAMPLE_ITEMS = [
  { name: "Chocolate Cake", type: "Product", status: "Ready", images: 4, updated: "Today" },
  { name: "3BHK Lake View Apartment", type: "Property", status: "Draft", images: 8, updated: "Yesterday" },
  { name: "IELTS Weekend Course", type: "Course", status: "Ready", images: 2, updated: "2 days ago" },
];

export default function CatalogPage() {
  const { role, loading } = useAuthRole();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab = (TABS.some((item) => item.id === rawTab) ? rawTab : "items") as CatalogTab;
  const [query, setQuery] = useState("");
  const [canRecommend, setCanRecommend] = useState(true);
  const [canSendImages, setCanSendImages] = useState(true);

  const filteredItems = useMemo(
    () => SAMPLE_ITEMS.filter((item) => item.name.toLowerCase().includes(query.toLowerCase())),
    [query]
  );

  function setTab(nextTab: CatalogTab) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", nextTab);
    router.replace(`/dashboard/catalog?${params.toString()}`, { scroll: false });
  }

  if (loading) {
    return <div className="min-h-[320px] animate-pulse rounded-card bg-surface-low" />;
  }

  if (role !== "owner") {
    return (
      <div className="py-20 text-center">
        <p className="font-body text-sm text-on-surface-muted">This section is only available for owners/admins.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex w-full flex-wrap gap-1 rounded-xl border border-border bg-white p-1 shadow-sm md:w-fit">
          {TABS.map((item) => {
            const Icon = item.icon;
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={cn(
                  "inline-flex min-h-9 items-center gap-2 rounded-lg px-3 text-sm font-semibold transition-colors",
                  active ? "bg-primary text-white" : "text-ink-muted hover:bg-surface-low hover:text-ink"
                )}
              >
                <Icon size={15} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
        <button className="btn-primary inline-flex items-center gap-2 self-start md:self-auto">
          <Plus size={16} />
          Add item
        </button>
      </div>

      {tab === "items" && (
        <div className="space-y-4">
          <div className="flex flex-col gap-3 rounded-card border border-border bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="font-display text-lg font-bold text-ink">Catalog Items</h2>
              <p className="mt-1 text-sm text-ink-muted">Products, services, properties, cakes, courses and anything else Aira can recommend.</p>
            </div>
            <label className="relative block md:w-72">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search catalog"
                className="h-10 w-full rounded-xl border border-border bg-surface-low pl-9 pr-3 text-sm outline-none transition-colors focus:border-primary"
              />
            </label>
          </div>

          <div className="overflow-x-auto rounded-card border border-border bg-white shadow-sm">
            <div className="min-w-[640px]">
              <div className="grid grid-cols-[1fr_120px_100px_90px_110px] gap-3 border-b border-border bg-surface-low px-4 py-3 text-xs font-bold uppercase text-ink-muted">
                <span>Item</span>
                <span>Type</span>
                <span>Status</span>
                <span>Images</span>
                <span>Updated</span>
              </div>
              {filteredItems.map((item) => (
                <div key={item.name} className="grid grid-cols-[1fr_120px_100px_90px_110px] gap-3 border-b border-border-subtle px-4 py-3 text-sm last:border-b-0">
                  <span className="font-semibold text-ink">{item.name}</span>
                  <span className="text-ink-muted">{item.type}</span>
                  <span>
                    <span className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold",
                      item.status === "Ready" ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
                    )}>
                      {item.status}
                    </span>
                  </span>
                  <span className="text-ink-muted">{item.images}</span>
                  <span className="text-ink-muted">{item.updated}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "media" && (
        <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-card border border-border bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-display text-lg font-bold text-ink">Media Library</h2>
              <button className="btn-ghost inline-flex items-center gap-2 px-3 py-2">
                <Upload size={15} />
                Upload
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {["Hero image", "Front view", "Detail shot", "Variant photo", "Menu card", "Proof image"].map((label) => (
                <div key={label} className="aspect-[4/3] rounded-card border border-border bg-surface-low p-3">
                  <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-border text-ink-muted">
                    <ImageIcon size={26} />
                    <span className="mt-2 text-xs font-semibold">{label}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-card border border-border bg-white p-5 shadow-sm">
            <h3 className="font-display text-base font-bold text-ink">Attach Media</h3>
            <p className="mt-1 text-sm text-ink-muted">Each image belongs to an item so the AI can choose relevant visuals.</p>
            <div className="mt-5 space-y-3">
              {SAMPLE_ITEMS.map((item) => (
                <div key={item.name} className="flex items-center justify-between rounded-xl bg-surface-low px-3 py-2">
                  <span className="text-sm font-semibold text-ink">{item.name}</span>
                  <span className="text-xs font-medium text-ink-muted">{item.images} images</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "ai-rules" && (
        <div className="grid gap-4 lg:grid-cols-3">
          <RuleCard
            title="AI Recommendations"
            description="Allow Aira to recommend matching catalog items when customers ask for options."
            checked={canRecommend}
            onChange={setCanRecommend}
          />
          <RuleCard
            title="Send Images"
            description="Allow Aira to send item images with its recommendation when the chat context calls for it."
            checked={canSendImages}
            onChange={setCanSendImages}
          />
          <div className="rounded-card border border-border bg-white p-5 shadow-sm">
            <h3 className="font-display text-base font-bold text-ink">Reply Limits</h3>
            <p className="mt-1 text-sm text-ink-muted">Default maximum images per AI reply.</p>
            <div className="mt-5 flex items-center gap-3">
              <button className="h-9 w-9 rounded-xl border border-border text-lg font-bold text-ink-muted">-</button>
              <span className="font-mono text-xl font-bold text-ink">3</span>
              <button className="h-9 w-9 rounded-xl border border-border text-lg font-bold text-ink-muted">+</button>
            </div>
          </div>
        </div>
      )}

      {tab === "insights" && (
        <div className="grid gap-4 md:grid-cols-3">
          {[
            ["Views", "Coming soon"],
            ["Sent images", "Coming soon"],
            ["Most requested", "Coming soon"],
          ].map(([label, value]) => (
            <div key={label} className="rounded-card border border-border bg-white p-5 shadow-sm">
              <p className="text-xs font-bold uppercase text-ink-muted">{label}</p>
              <p className="mt-3 font-display text-2xl font-bold text-ink">{value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RuleCard({
  title,
  description,
  checked,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="rounded-card border border-border bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-display text-base font-bold text-ink">{title}</h3>
          <p className="mt-1 text-sm leading-relaxed text-ink-muted">{description}</p>
        </div>
        <button
          type="button"
          onClick={() => onChange(!checked)}
          className={cn(
            "inline-flex h-8 w-14 shrink-0 items-center rounded-full p-1 transition-colors",
            checked ? "bg-primary" : "bg-surface-mid"
          )}
          aria-label={`Toggle ${title}`}
        >
          <span className={cn("h-6 w-6 rounded-full bg-white shadow-sm transition-transform", checked && "translate-x-6")} />
        </button>
      </div>
      <div className="mt-5 inline-flex items-center gap-2 rounded-full bg-surface-low px-3 py-1 text-xs font-semibold text-ink-muted">
        {checked ? <CheckCircle2 size={13} className="text-success" /> : <ToggleLeft size={13} />}
        {checked ? "Enabled" : "Disabled"}
      </div>
    </div>
  );
}
