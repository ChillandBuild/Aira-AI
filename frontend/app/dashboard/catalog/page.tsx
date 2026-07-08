"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  CheckCircle2,
  Image as ImageIcon,
  Loader2,
  Package,
  Plus,
  Search,
  Sparkles,
  ToggleLeft,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { api, CatalogAiRules, CatalogItem, CatalogMedia } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";

type CatalogTab = "items" | "media" | "ai-rules" | "insights";

const TABS: { id: CatalogTab; label: string; icon: typeof Package }[] = [
  { id: "items", label: "Items", icon: Package },
  { id: "media", label: "Media", icon: ImageIcon },
  { id: "ai-rules", label: "AI Rules", icon: Sparkles },
  { id: "insights", label: "Insights", icon: BarChart3 },
];

const ITEM_TYPES = ["product", "service", "property", "course", "other"];

export default function CatalogPage() {
  const { role, loading } = useAuthRole();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab = (TABS.some((item) => item.id === rawTab) ? rawTab : "items") as CatalogTab;

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
      </div>

      {tab === "items" && <ItemsTab />}
      {tab === "media" && <MediaTab />}
      {tab === "ai-rules" && <AiRulesTab />}
      {tab === "insights" && <InsightsTab />}
    </div>
  );
}

function ItemsTab() {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);

  async function loadItems(q?: string) {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.catalog.listItems(q);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load catalog items");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    const handle = setTimeout(() => loadItems(query || undefined), 300);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  async function handleToggleStatus(item: CatalogItem) {
    const nextStatus = item.status === "ready" ? "draft" : "ready";
    try {
      const updated = await api.catalog.updateItem(item.id, { status: nextStatus });
      setItems((prev) => prev.map((i) => (i.id === item.id ? updated : i)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update item status");
    }
  }

  async function handleDelete(item: CatalogItem) {
    try {
      await api.catalog.deleteItem(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete item");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-card border border-border bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-lg font-bold text-ink">Catalog Items</h2>
          <p className="mt-1 text-sm text-ink-muted">Products, services, properties, cakes, courses and anything else Aira can recommend.</p>
        </div>
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <label className="relative block md:w-72">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search catalog"
              className="h-10 w-full rounded-xl border border-border bg-surface-low pl-9 pr-3 text-sm outline-none transition-colors focus:border-primary"
            />
          </label>
          <button
            type="button"
            onClick={() => setShowAddModal(true)}
            className="btn-primary inline-flex items-center justify-center gap-2 self-start md:self-auto"
          >
            <Plus size={16} />
            Add item
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-card border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">{error}</div>
      )}

      <div className="overflow-x-auto rounded-card border border-border bg-white shadow-sm">
        <div className="min-w-[640px]">
          <div className="grid grid-cols-[1fr_120px_100px_90px_110px_60px] gap-3 border-b border-border bg-surface-low px-4 py-3 text-xs font-bold uppercase text-ink-muted">
            <span>Item</span>
            <span>Type</span>
            <span>Status</span>
            <span>Images</span>
            <span>Updated</span>
            <span />
          </div>
          {isLoading && (
            <div className="flex items-center justify-center gap-2 px-4 py-10 text-sm text-ink-muted">
              <Loader2 size={16} className="animate-spin" />
              Loading catalog items...
            </div>
          )}
          {!isLoading && items.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-ink-muted">
              No catalog items yet. Click &ldquo;Add item&rdquo; to create your first one.
            </div>
          )}
          {!isLoading &&
            items.map((item) => (
              <div key={item.id} className="grid grid-cols-[1fr_120px_100px_90px_110px_60px] gap-3 border-b border-border-subtle px-4 py-3 text-sm last:border-b-0">
                <span className="font-semibold text-ink">{item.name}</span>
                <span className="capitalize text-ink-muted">{item.item_type}</span>
                <span>
                  <button
                    type="button"
                    onClick={() => handleToggleStatus(item)}
                    className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold transition-colors",
                      item.status === "ready" ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
                    )}
                  >
                    {item.status === "ready" ? "Ready" : "Draft"}
                  </button>
                </span>
                <span className="text-ink-muted">—</span>
                <span className="text-ink-muted">{new Date(item.updated_at).toLocaleDateString()}</span>
                <button
                  type="button"
                  onClick={() => handleDelete(item)}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-danger/10 hover:text-danger"
                  aria-label={`Delete ${item.name}`}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
        </div>
      </div>

      {showAddModal && (
        <AddItemModal
          onClose={() => setShowAddModal(false)}
          onCreated={(item) => {
            setItems((prev) => [item, ...prev]);
            setShowAddModal(false);
          }}
        />
      )}
    </div>
  );
}

function AddItemModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (item: CatalogItem) => void;
}) {
  const [name, setName] = useState("");
  const [itemType, setItemType] = useState(ITEM_TYPES[0]);
  const [description, setDescription] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const item = await api.catalog.createItem({ name: name.trim(), item_type: itemType, description: description.trim() || null });
      onCreated(item);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create item");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-card bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-lg font-bold text-ink">Add catalog item</h3>
          <button type="button" onClick={onClose} className="text-ink-muted hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-ink-muted">Name</label>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="h-10 w-full rounded-xl border border-border bg-surface-low px-3 text-sm outline-none focus:border-primary"
              placeholder="e.g. Chocolate Cake"
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-ink-muted">Type</label>
            <select
              value={itemType}
              onChange={(event) => setItemType(event.target.value)}
              className="h-10 w-full rounded-xl border border-border bg-surface-low px-3 text-sm capitalize outline-none focus:border-primary"
            >
              {ITEM_TYPES.map((type) => (
                <option key={type} value={type} className="capitalize">
                  {type}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-ink-muted">Description (optional)</label>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              className="w-full rounded-xl border border-border bg-surface-low px-3 py-2 text-sm outline-none focus:border-primary"
              placeholder="Short description Aira can use when recommending this item"
            />
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn-ghost px-4 py-2">
              Cancel
            </button>
            <button type="submit" disabled={isSaving} className="btn-primary inline-flex items-center gap-2 px-4 py-2 disabled:opacity-60">
              {isSaving && <Loader2 size={14} className="animate-spin" />}
              Add item
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function MediaTab() {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [media, setMedia] = useState<CatalogMedia[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadingItemId, setUploadingItemId] = useState<string | null>(null);

  async function loadAll() {
    setIsLoading(true);
    setError(null);
    try {
      const [itemsData, mediaData] = await Promise.all([api.catalog.listItems(), api.catalog.listMedia()]);
      setItems(itemsData);
      setMedia(mediaData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load media");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function handleUpload(itemId: string, file: File) {
    setUploadingItemId(itemId);
    setError(null);
    try {
      const uploaded = await api.catalog.uploadMedia(itemId, file);
      setMedia((prev) => [uploaded, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploadingItemId(null);
    }
  }

  const mediaCountByItem = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const m of media) {
      counts[m.catalog_item_id] = (counts[m.catalog_item_id] || 0) + 1;
    }
    return counts;
  }, [media]);

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-card border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">{error}</div>
      )}
      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-card border border-border bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-display text-lg font-bold text-ink">Media Library</h2>
          </div>
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-muted">
              <Loader2 size={16} className="animate-spin" />
              Loading media...
            </div>
          )}
          {!isLoading && media.length === 0 && (
            <p className="py-10 text-center text-sm text-ink-muted">No media uploaded yet. Attach images to an item using the panel on the right.</p>
          )}
          {!isLoading && media.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {media.map((item) => (
                <div key={item.id} className="aspect-[4/3] overflow-hidden rounded-card border border-border bg-surface-low p-2">
                  {item.url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={item.url} alt={item.label || "Catalog media"} className="h-full w-full rounded-xl object-cover" />
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-border text-ink-muted">
                      <ImageIcon size={26} />
                    </div>
                  )}
                  <p className="mt-2 truncate text-center text-xs font-semibold text-ink-muted">{item.item_name || item.label}</p>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="rounded-card border border-border bg-white p-5 shadow-sm">
          <h3 className="font-display text-base font-bold text-ink">Attach Media</h3>
          <p className="mt-1 text-sm text-ink-muted">Each image belongs to an item so the AI can choose relevant visuals.</p>
          <div className="mt-5 space-y-3">
            {items.length === 0 && !isLoading && (
              <p className="text-sm text-ink-muted">Add a catalog item first, then come back here to attach photos.</p>
            )}
            {items.map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-3 rounded-xl bg-surface-low px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink">{item.name}</p>
                  <p className="text-xs font-medium text-ink-muted">{mediaCountByItem[item.id] || 0} images</p>
                </div>
                <label className="btn-ghost inline-flex shrink-0 cursor-pointer items-center gap-2 px-3 py-1.5 text-xs">
                  {uploadingItemId === item.id ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                  Upload
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    disabled={uploadingItemId === item.id}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) handleUpload(item.id, file);
                      event.target.value = "";
                    }}
                  />
                </label>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function AiRulesTab() {
  const [rules, setRules] = useState<CatalogAiRules | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.catalog
      .getAiRules()
      .then(setRules)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load AI rules"));
  }, []);

  async function patch(update: Partial<CatalogAiRules>) {
    if (!rules) return;
    const optimistic = { ...rules, ...update };
    setRules(optimistic);
    try {
      const saved = await api.catalog.updateAiRules(update);
      setRules(saved);
    } catch (err) {
      setRules(rules);
      setError(err instanceof Error ? err.message : "Failed to save AI rules");
    }
  }

  if (!rules) {
    return <div className="min-h-[200px] animate-pulse rounded-card bg-surface-low" />;
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-card border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">{error}</div>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <RuleCard
          title="AI Recommendations"
          description="Allow Aira to recommend matching catalog items when customers ask for options."
          checked={rules.can_recommend}
          onChange={(checked) => patch({ can_recommend: checked })}
        />
        <RuleCard
          title="Send Images"
          description="Allow Aira to send item images with its recommendation when the chat context calls for it."
          checked={rules.can_send_images}
          onChange={(checked) => patch({ can_send_images: checked })}
        />
        <div className="rounded-card border border-border bg-white p-5 shadow-sm">
          <h3 className="font-display text-base font-bold text-ink">Reply Limits</h3>
          <p className="mt-1 text-sm text-ink-muted">Default maximum images per AI reply.</p>
          <div className="mt-5 flex items-center gap-3">
            <button
              type="button"
              onClick={() => patch({ max_images_per_reply: Math.max(0, rules.max_images_per_reply - 1) })}
              className="h-9 w-9 rounded-xl border border-border text-lg font-bold text-ink-muted transition-colors hover:bg-surface-low"
            >
              -
            </button>
            <span className="font-mono text-xl font-bold text-ink">{rules.max_images_per_reply}</span>
            <button
              type="button"
              onClick={() => patch({ max_images_per_reply: Math.min(10, rules.max_images_per_reply + 1) })}
              className="h-9 w-9 rounded-xl border border-border text-lg font-bold text-ink-muted transition-colors hover:bg-surface-low"
            >
              +
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function InsightsTab() {
  return (
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
