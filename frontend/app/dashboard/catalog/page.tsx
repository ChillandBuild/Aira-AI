"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  CheckCircle2,
  ChevronDown,
  GripVertical,
  Image as ImageIcon,
  Layers,
  Loader2,
  Package,
  Pencil,
  Plus,
  Search,
  Sparkles,
  ToggleLeft,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { cn } from "@/lib/utils";
import { api, CatalogAiRules, CatalogItem, CatalogMedia, CatalogVariantGroup } from "@/lib/api";
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
  const { role, permissions, loading } = useAuthRole();
  const canViewCatalog = role === "owner" || permissions.includes("catalog.view") || permissions.includes("catalog.manage");
  const canManageCatalog = role === "owner" || permissions.includes("catalog.manage");
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

  if (!canViewCatalog) {
    return (
      <div className="py-20 text-center">
        <p className="font-body text-sm text-on-surface-muted">You do not have access to the catalog.</p>
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

      {tab === "items" && <ItemsTab canManage={canManageCatalog} />}
      {tab === "media" && <MediaTab canManage={canManageCatalog} />}
      {tab === "ai-rules" && <AiRulesTab canManage={canManageCatalog} />}
      {tab === "insights" && <InsightsTab />}
    </div>
  );
}

function ItemsTab({ canManage }: { canManage: boolean }) {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [variantGroups, setVariantGroups] = useState<CatalogVariantGroup[]>([]);
  const [isLoadingGroups, setIsLoadingGroups] = useState(true);
  const [groupsError, setGroupsError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingItem, setEditingItem] = useState<CatalogItem | null>(null);
  const [isReindexing, setIsReindexing] = useState(false);

  // Variant groups panel state
  const [newPanelGroupName, setNewPanelGroupName] = useState("");
  const [newPanelGroupType, setNewPanelGroupType] = useState(ITEM_TYPES[0]);
  const [isCreatingGroupFromPanel, setIsCreatingGroupFromPanel] = useState(false);
  const [panelGroupError, setPanelGroupError] = useState<string | null>(null);

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

  async function loadVariantGroups() {
    setIsLoadingGroups(true);
    setGroupsError(null);
    try {
      const data = await api.catalog.listVariantGroups();
      setVariantGroups(data);
    } catch (err) {
      setGroupsError(err instanceof Error ? err.message : "Failed to load variant groups");
    } finally {
      setIsLoadingGroups(false);
    }
  }

  useEffect(() => {
    const handle = setTimeout(() => loadItems(query || undefined), 300);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  useEffect(() => {
    loadVariantGroups();
  }, []);

  useEffect(() => {
    if (successMessage) {
      const t = setTimeout(() => setSuccessMessage(null), 5000);
      return () => clearTimeout(t);
    }
  }, [successMessage]);

  async function handleToggleStatus(item: CatalogItem) {
    if (!canManage) return;
    const nextStatus = item.status === "ready" ? "draft" : "ready";
    try {
      const updated = await api.catalog.updateItem(item.id, { status: nextStatus });
      setItems((prev) => prev.map((i) => (i.id === item.id ? updated : i)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update item status");
    }
  }

  async function handleDelete(item: CatalogItem) {
    if (!canManage) return;
    try {
      await api.catalog.deleteItem(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete item");
    }
  }

  async function handleReindex() {
    if (!canManage) return;
    setIsReindexing(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const res = await api.catalog.reindex();
      if (res.success) {
        setSuccessMessage(`Catalog reindexed successfully! Embedded ${res.items_embedded} of ${res.items_total} items.`);
      } else {
        setError("Reindexing failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reindex catalog");
    } finally {
      setIsReindexing(false);
    }
  }

  async function handleCreateGroupFromPanel() {
    if (!canManage || !newPanelGroupName.trim()) return;
    setIsCreatingGroupFromPanel(true);
    setPanelGroupError(null);
    try {
      const newGroup = await api.catalog.createVariantGroup({
        name: newPanelGroupName.trim(),
        item_type: newPanelGroupType,
      });
      setVariantGroups((prev) => [...prev, newGroup]);
      setNewPanelGroupName("");
    } catch (err) {
      setPanelGroupError(err instanceof Error ? err.message : "Failed to create group");
    } finally {
      setIsCreatingGroupFromPanel(false);
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
          {canManage && (
            <>
              <button
                type="button"
                onClick={handleReindex}
                disabled={isReindexing}
                className="btn-ghost border border-border bg-white text-ink inline-flex items-center justify-center gap-2 self-start md:self-auto h-10 px-4 rounded-xl text-sm transition-colors hover:bg-surface-low disabled:opacity-50"
                title="Reindex catalog items to refresh AI embeddings"
              >
                {isReindexing ? <Loader2 size={15} className="animate-spin text-ink-muted" /> : <Sparkles size={15} className="text-primary" />}
                <span>{isReindexing ? "Reindexing..." : "Reindex"}</span>
              </button>
              <button
                type="button"
                onClick={() => setShowAddModal(true)}
                className="btn-primary inline-flex items-center justify-center gap-2 self-start md:self-auto"
              >
                <Plus size={16} />
                Add item
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-card border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">{error}</div>
      )}

      {successMessage && (
        <div className="rounded-card border border-success/30 bg-success/5 px-4 py-3 text-sm text-success flex justify-between items-center">
          <span>{successMessage}</span>
          <button type="button" onClick={() => setSuccessMessage(null)} className="text-success hover:opacity-70">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Variant Groups Panel */}
      <div className="rounded-card border border-border bg-white p-4 shadow-sm">
        <details className="group">
          <summary className="flex cursor-pointer items-center justify-between font-display text-base font-bold text-ink list-none">
            <span className="flex items-center gap-2">
              <Layers size={18} className="text-primary" />
              <span>Variant Groups ({variantGroups.length})</span>
            </span>
            <span className="text-ink-muted transition-transform group-open:rotate-180">
              <ChevronDown size={18} />
            </span>
          </summary>
          <div className="mt-4 border-t border-border-subtle pt-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-4">
              <p className="text-sm text-ink-muted">
                Group variants (e.g. properties in different locations) so Aira can disambiguate them.
              </p>
              {canManage && (
                <div className="flex flex-wrap gap-2">
                  <input
                    value={newPanelGroupName}
                    onChange={(e) => setNewPanelGroupName(e.target.value)}
                    className="h-9 rounded-xl border border-border bg-surface-low px-3 text-sm outline-none focus:border-primary w-48"
                    placeholder="New group name"
                  />
                  <select
                    value={newPanelGroupType}
                    onChange={(e) => setNewPanelGroupType(e.target.value)}
                    className="h-9 rounded-xl border border-border bg-surface-low px-3 text-sm outline-none focus:border-primary capitalize"
                  >
                    {ITEM_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={handleCreateGroupFromPanel}
                    disabled={isCreatingGroupFromPanel || !newPanelGroupName.trim()}
                    className="btn-primary inline-flex items-center justify-center gap-1 px-3 py-1.5 text-xs"
                  >
                    <Plus size={12} />
                    Add Group
                  </button>
                </div>
              )}
            </div>
            {panelGroupError && <p className="mb-3 text-sm text-danger">{panelGroupError}</p>}
            {groupsError && (
              <p className="mb-3 text-sm text-danger">Failed to load variant groups: {groupsError}</p>
            )}
            {isLoadingGroups ? (
              <div className="flex items-center justify-center gap-2 py-4 text-sm text-ink-muted">
                <Loader2 size={15} className="animate-spin" />
                Loading variant groups...
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {variantGroups.map((group) => {
                  const count = items.filter((i) => i.variant_group_id === group.id).length;
                  return (
                    <div key={group.id} className="rounded-xl border border-border bg-surface-low p-3">
                      <p className="font-semibold text-ink truncate">{group.name}</p>
                      <div className="mt-1 flex items-center justify-between text-xs text-ink-muted">
                        <span className="capitalize">{group.item_type}</span>
                        <span>{count} {count === 1 ? "item" : "items"}</span>
                      </div>
                    </div>
                  );
                })}
                {variantGroups.length === 0 && !groupsError && (
                  <p className="text-sm text-ink-muted col-span-full text-center py-4">No variant groups created yet.</p>
                )}
              </div>
            )}
          </div>
        </details>
      </div>

      <div className="overflow-x-auto rounded-card border border-border bg-white shadow-sm">
        <div className="min-w-[640px]">
          <div className="grid grid-cols-[1.2fr_150px_120px_100px_80px_100px_80px] gap-3 border-b border-border bg-surface-low px-4 py-3 text-xs font-bold uppercase text-ink-muted">
            <span>Item</span>
            <span>Variant Group</span>
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
              <div key={item.id} className="grid grid-cols-[1.2fr_150px_120px_100px_80px_100px_80px] gap-3 border-b border-border-subtle px-4 py-3 text-sm last:border-b-0">
                <span className="font-semibold text-ink truncate" title={item.name}>{item.name}</span>
                <span className="text-ink-muted truncate" title={variantGroups.find((g) => g.id === item.variant_group_id)?.name || "Ungrouped"}>
                  {variantGroups.find((g) => g.id === item.variant_group_id)?.name || "—"}
                </span>
                <span className="capitalize text-ink-muted">{item.item_type}</span>
                <span>
                  <button
                    type="button"
                    onClick={() => handleToggleStatus(item)}
                    disabled={!canManage}
                    className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold transition-colors disabled:cursor-default",
                      item.status === "ready" ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
                    )}
                  >
                    {item.status === "ready" ? "Ready" : "Draft"}
                  </button>
                </span>
                <span className="text-ink-muted">—</span>
                <span className="text-ink-muted">{new Date(item.updated_at).toLocaleDateString()}</span>
                <div className="flex justify-end items-center gap-1">
                  {canManage && (
                    <>
                      <button
                        type="button"
                        onClick={() => setEditingItem(item)}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-surface-low hover:text-ink"
                        aria-label={`Edit ${item.name}`}
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(item)}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-danger/10 hover:text-danger"
                        aria-label={`Delete ${item.name}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
        </div>
      </div>

      {showAddModal && (
        <AddEditItemModal
          onClose={() => setShowAddModal(false)}
          onSaved={(item) => {
            setItems((prev) => [item, ...prev]);
            setShowAddModal(false);
          }}
          variantGroups={variantGroups}
          onGroupCreated={(newGroup) => setVariantGroups((prev) => [...prev, newGroup])}
        />
      )}

      {editingItem && (
        <AddEditItemModal
          itemToEdit={editingItem}
          onClose={() => setEditingItem(null)}
          onSaved={(updated) => {
            setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
            setEditingItem(null);
          }}
          variantGroups={variantGroups}
          onGroupCreated={(newGroup) => setVariantGroups((prev) => [...prev, newGroup])}
        />
      )}
    </div>
  );
}

function AddEditItemModal({
  onClose,
  onSaved,
  itemToEdit = null,
  variantGroups,
  onGroupCreated,
}: {
  onClose: () => void;
  onSaved: (item: CatalogItem) => void;
  itemToEdit?: CatalogItem | null;
  variantGroups: CatalogVariantGroup[];
  onGroupCreated: (group: CatalogVariantGroup) => void;
}) {
  const [name, setName] = useState(itemToEdit?.name || "");
  const [itemType, setItemType] = useState(itemToEdit?.item_type || ITEM_TYPES[0]);
  const [description, setDescription] = useState(itemToEdit?.description || "");
  const [variantGroupId, setVariantGroupId] = useState(itemToEdit?.variant_group_id || "");

  const nextAttrId = useRef(0);
  const [attributes, setAttributes] = useState<{ id: number; key: string; value: string }[]>(() => {
    if (itemToEdit?.attributes) {
      const entries = Object.entries(itemToEdit.attributes);
      return entries.length > 0
        ? entries.map(([key, value]) => ({ id: nextAttrId.current++, key, value }))
        : [{ id: nextAttrId.current++, key: "", value: "" }];
    }
    return [{ id: nextAttrId.current++, key: "", value: "" }];
  });

  const [showNewGroupInput, setShowNewGroupInput] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [isCreatingGroup, setIsCreatingGroup] = useState(false);
  const [groupError, setGroupError] = useState<string | null>(null);

  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreateGroup() {
    if (!newGroupName.trim()) return;
    setIsCreatingGroup(true);
    setGroupError(null);
    try {
      const newGroup = await api.catalog.createVariantGroup({
        name: newGroupName.trim(),
        item_type: itemType,
      });
      onGroupCreated(newGroup);
      setVariantGroupId(newGroup.id);
      setNewGroupName("");
      setShowNewGroupInput(false);
    } catch (err) {
      setGroupError(err instanceof Error ? err.message : "Failed to create group");
    } finally {
      setIsCreatingGroup(false);
    }
  }

  function handleAddAttribute() {
    setAttributes((prev) => [...prev, { id: nextAttrId.current++, key: "", value: "" }]);
  }

  function handleRemoveAttribute(id: number) {
    setAttributes((prev) => prev.filter((attr) => attr.id !== id));
  }

  function handleAttributeChange(id: number, field: "key" | "value", val: string) {
    setAttributes((prev) =>
      prev.map((attr) => (attr.id === id ? { ...attr, [field]: val } : attr))
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    setIsSaving(true);
    setError(null);

    const attrRecord: Record<string, string> = {};
    for (const attr of attributes) {
      const k = attr.key.trim();
      const v = attr.value.trim();
      if (k) {
        attrRecord[k] = v;
      }
    }

    try {
      let savedItem: CatalogItem;
      const payload = {
        name: name.trim(),
        item_type: itemType,
        description: description.trim() || null,
        variant_group_id: variantGroupId || null,
        attributes: attrRecord,
      };

      if (itemToEdit) {
        savedItem = await api.catalog.updateItem(itemToEdit.id, payload);
      } else {
        savedItem = await api.catalog.createItem(payload);
      }
      onSaved(savedItem);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save item");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-card bg-white p-5 shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-lg font-bold text-ink">
            {itemToEdit ? "Edit catalog item" : "Add catalog item"}
          </h3>
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

          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-ink-muted">Variant Group</label>
            {!showNewGroupInput ? (
              <select
                value={variantGroupId}
                onChange={(event) => {
                  const val = event.target.value;
                  if (val === "__new__") {
                    setShowNewGroupInput(true);
                  } else {
                    setVariantGroupId(val);
                  }
                }}
                className="h-10 w-full rounded-xl border border-border bg-surface-low px-3 text-sm outline-none focus:border-primary cursor-pointer"
              >
                <option value="">None (Ungrouped)</option>
                {variantGroups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name} ({group.item_type})
                  </option>
                ))}
                <option value="__new__">+ New group</option>
              </select>
            ) : (
              <div className="flex gap-2">
                <input
                  value={newGroupName}
                  onChange={(event) => setNewGroupName(event.target.value)}
                  className="h-10 flex-1 rounded-xl border border-border bg-surface-low px-3 text-sm outline-none focus:border-primary"
                  placeholder="New group name"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={handleCreateGroup}
                  disabled={isCreatingGroup}
                  className="btn-primary px-3 text-xs font-semibold shrink-0"
                >
                  {isCreatingGroup ? <Loader2 size={12} className="animate-spin" /> : "Create"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowNewGroupInput(false);
                    setNewGroupName("");
                  }}
                  className="btn-ghost px-3 text-xs shrink-0"
                >
                  Cancel
                </button>
              </div>
            )}
            {groupError && <p className="mt-1 text-xs text-danger">{groupError}</p>}
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-ink-muted">Attributes</label>
            <div className="space-y-2">
              {attributes.map((attr) => (
                <div key={attr.id} className="flex items-center gap-2">
                  <input
                    value={attr.key}
                    onChange={(e) => handleAttributeChange(attr.id, "key", e.target.value)}
                    className="h-9 flex-1 rounded-xl border border-border bg-surface-low px-3 text-xs outline-none focus:border-primary"
                    placeholder="Key (e.g. location)"
                  />
                  <input
                    value={attr.value}
                    onChange={(e) => handleAttributeChange(attr.id, "value", e.target.value)}
                    className="h-9 flex-1 rounded-xl border border-border bg-surface-low px-3 text-xs outline-none focus:border-primary"
                    placeholder="Value (e.g. Coimbatore)"
                  />
                  <button
                    type="button"
                    onClick={() => handleRemoveAttribute(attr.id)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-ink-muted hover:bg-danger/10 hover:text-danger"
                    aria-label="Remove attribute"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={handleAddAttribute}
                className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
              >
                <Plus size={12} />
                Add attribute
              </button>
            </div>
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn-ghost px-4 py-2">
              Cancel
            </button>
            <button type="submit" disabled={isSaving} className="btn-primary inline-flex items-center gap-2 px-4 py-2 disabled:opacity-60">
              {isSaving && <Loader2 size={14} className="animate-spin" />}
              {itemToEdit ? "Save changes" : "Add item"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function SortablePhoto({
  media,
  canManage,
  onLabelSave,
  onDelete,
}: {
  media: CatalogMedia;
  canManage: boolean;
  onLabelSave: (id: string, label: string) => void;
  onDelete: (id: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: media.id });
  const [isEditing, setIsEditing] = useState(false);
  const [draftLabel, setDraftLabel] = useState(media.label || "");

  useEffect(() => {
    setDraftLabel(media.label || "");
  }, [media.label]);

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  function commitLabel() {
    setIsEditing(false);
    const trimmed = draftLabel.trim();
    if (trimmed && trimmed !== (media.label || "")) {
      onLabelSave(media.id, trimmed);
    } else {
      setDraftLabel(media.label || "");
    }
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="group relative overflow-hidden rounded-card border border-border bg-surface-low p-2"
    >
      <div className="relative aspect-[4/3] overflow-hidden rounded-xl">
        {canManage && (
          <button
            type="button"
            {...attributes}
            {...listeners}
            className="absolute left-2 top-2 z-10 flex h-6 w-6 cursor-grab items-center justify-center rounded-md bg-white/90 text-ink-muted opacity-0 shadow-sm transition-opacity group-hover:opacity-100 active:cursor-grabbing"
            aria-label="Drag to reorder"
          >
            <GripVertical size={13} />
          </button>
        )}
        {canManage && (
          <button
            type="button"
            onClick={() => onDelete(media.id)}
            className="absolute right-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-md bg-white/90 text-danger opacity-0 shadow-sm transition-opacity hover:bg-danger hover:text-white group-hover:opacity-100"
            aria-label="Remove photo"
          >
            <X size={13} />
          </button>
        )}
        {media.url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={media.url} alt={media.label || "Catalog media"} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center border border-dashed border-border text-ink-muted">
            <ImageIcon size={26} />
          </div>
        )}
      </div>
      {isEditing ? (
        <input
          autoFocus
          value={draftLabel}
          onChange={(event) => setDraftLabel(event.target.value)}
          onBlur={commitLabel}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
            if (event.key === "Escape") {
              setDraftLabel(media.label || "");
              setIsEditing(false);
            }
          }}
          placeholder="Name this photo..."
          className="mt-2 w-full rounded-md border border-primary px-2 py-1.5 text-center text-xs font-semibold text-ink outline-none"
        />
      ) : (
        <button
          type="button"
          disabled={!canManage}
          onClick={() => canManage && setIsEditing(true)}
          className={cn(
            "mt-2 flex w-full items-center justify-center gap-1.5 truncate rounded-md border px-2 py-1.5 text-xs font-semibold transition-colors disabled:cursor-default",
            media.label
              ? "border-border bg-white text-ink hover:border-primary/40"
              : "border-dashed border-primary/40 bg-primary/5 text-primary hover:bg-primary/10"
          )}
          title={canManage ? "Click to rename this photo" : undefined}
        >
          {canManage && <Pencil size={11} className="shrink-0" />}
          <span className="truncate">{media.label || "Click to name this photo"}</span>
        </button>
      )}
    </div>
  );
}

function MediaItemGroup({
  photos,
  canManage,
  onReorder,
  onLabelSave,
  onDelete,
}: {
  photos: CatalogMedia[];
  canManage: boolean;
  onReorder: (orderedIds: string[]) => void;
  onLabelSave: (id: string, label: string) => void;
  onDelete: (id: string) => void;
}) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = photos.findIndex((p) => p.id === active.id);
    const newIndex = photos.findIndex((p) => p.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;
    onReorder(arrayMove(photos, oldIndex, newIndex).map((p) => p.id));
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={photos.map((p) => p.id)} strategy={rectSortingStrategy}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {photos.map((photo) => (
            <SortablePhoto key={photo.id} media={photo} canManage={canManage} onLabelSave={onLabelSave} onDelete={onDelete} />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}

function MediaTab({ canManage }: { canManage: boolean }) {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [media, setMedia] = useState<CatalogMedia[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadingItemId, setUploadingItemId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);

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

  async function handleUploadMultiple(itemId: string, files: FileList) {
    if (!canManage || files.length === 0) return;
    setUploadingItemId(itemId);
    setError(null);
    const fileList = Array.from(files);
    try {
      for (let i = 0; i < fileList.length; i++) {
        setUploadProgress({ current: i + 1, total: fileList.length });
        const uploaded = await api.catalog.uploadMedia(itemId, fileList[i]);
        setMedia((prev) => [...prev, uploaded]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploadingItemId(null);
      setUploadProgress(null);
    }
  }

  async function handleReorder(itemId: string, orderedIds: string[]) {
    setMedia((prev) => {
      const rank = new Map(orderedIds.map((id, index) => [id, index]));
      return prev
        .map((m) => (m.catalog_item_id === itemId && rank.has(m.id) ? { ...m, sort_order: rank.get(m.id)! } : m))
        .slice()
        .sort((a, b) => a.sort_order - b.sort_order);
    });
    try {
      await api.catalog.reorderMedia(itemId, orderedIds);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save photo order");
      loadAll();
    }
  }

  async function handleLabelSave(mediaId: string, label: string) {
    setMedia((prev) => prev.map((m) => (m.id === mediaId ? { ...m, label } : m)));
    try {
      await api.catalog.updateMedia(mediaId, { label });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save photo name");
      loadAll();
    }
  }

  async function handleDelete(mediaId: string) {
    const removed = media.find((m) => m.id === mediaId);
    setMedia((prev) => prev.filter((m) => m.id !== mediaId));
    try {
      await api.catalog.deleteMedia(mediaId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove photo");
      if (removed) setMedia((prev) => [...prev, removed]);
    }
  }

  const mediaCountByItem = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const m of media) {
      counts[m.catalog_item_id] = (counts[m.catalog_item_id] || 0) + 1;
    }
    return counts;
  }, [media]);

  const mediaGroupsByItem = useMemo(() => {
    const groups: Record<string, CatalogMedia[]> = {};
    for (const m of media) {
      (groups[m.catalog_item_id] ||= []).push(m);
    }
    for (const itemId of Object.keys(groups)) {
      groups[itemId].sort((a, b) => a.sort_order - b.sort_order);
    }
    return groups;
  }, [media]);

  const selectedItem = items.find((item) => item.id === selectedItemId) || null;
  const selectedPhotos = selectedItemId ? mediaGroupsByItem[selectedItemId] || [] : [];

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-card border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">{error}</div>
      )}
      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-card border border-border bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-display text-lg font-bold text-ink">
              Media Library{selectedItem ? ` — ${selectedItem.name}` : ""}
            </h2>
          </div>
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-muted">
              <Loader2 size={16} className="animate-spin" />
              Loading media...
            </div>
          )}
          {!isLoading && !selectedItem && (
            <p className="py-10 text-center text-sm text-ink-muted">Select an item on the right to view its photos.</p>
          )}
          {!isLoading && selectedItem && selectedPhotos.length === 0 && (
            <p className="py-10 text-center text-sm text-ink-muted">No photos yet for {selectedItem.name}. Upload some using the panel on the right.</p>
          )}
          {!isLoading && selectedItem && selectedPhotos.length > 0 && (
            <MediaItemGroup
              photos={selectedPhotos}
              canManage={canManage}
              onReorder={(orderedIds) => handleReorder(selectedItem.id, orderedIds)}
              onLabelSave={handleLabelSave}
              onDelete={handleDelete}
            />
          )}
        </div>
        <div className="rounded-card border border-border bg-white p-5 shadow-sm">
          <h3 className="font-display text-base font-bold text-ink">Attach Media</h3>
          <p className="mt-1 text-sm text-ink-muted">
            Each image belongs to an item so the AI can choose relevant visuals. Click an item to view its photos in
            the library on the left — select multiple photos to upload them all at once, drag to reorder, whoever is
            listed first gets sent first.
          </p>
          <div className="mt-5 space-y-3">
            {items.length === 0 && !isLoading && (
              <p className="text-sm text-ink-muted">Add a catalog item first, then come back here to attach photos.</p>
            )}
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedItemId(item.id)}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition-colors",
                  selectedItemId === item.id ? "bg-primary/10 ring-1 ring-primary/40" : "bg-surface-low hover:bg-surface-low/70"
                )}
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink">{item.name}</p>
                  <p className="text-xs font-medium text-ink-muted">
                    {uploadingItemId === item.id && uploadProgress
                      ? `Uploading ${uploadProgress.current}/${uploadProgress.total}...`
                      : `${mediaCountByItem[item.id] || 0} images`}
                  </p>
                </div>
                <label
                  onClick={(event) => event.stopPropagation()}
                  className={cn("btn-ghost inline-flex shrink-0 items-center gap-2 px-3 py-1.5 text-xs", canManage ? "cursor-pointer" : "cursor-not-allowed opacity-45 blur-[0.5px]")}
                >
                  {uploadingItemId === item.id ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                  Upload
                  <input
                    type="file"
                    accept="image/*"
                    multiple
                    className="hidden"
                    disabled={uploadingItemId === item.id || !canManage}
                    onChange={(event) => {
                      const files = event.target.files;
                      if (files && files.length > 0) {
                        setSelectedItemId(item.id);
                        handleUploadMultiple(item.id, files);
                      }
                      event.target.value = "";
                    }}
                  />
                </label>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function AiRulesTab({ canManage }: { canManage: boolean }) {
  const [rules, setRules] = useState<CatalogAiRules | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.catalog
      .getAiRules()
      .then(setRules)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load AI rules"));
  }, []);

  async function patch(update: Partial<Pick<CatalogAiRules, "can_recommend" | "can_send_images" | "max_images_per_reply">>) {
    if (!canManage) {
      setError("Read-only role: catalog AI rule changes are disabled.");
      return;
    }
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

  const controlsDisabled = !canManage || !rules.feature_enabled;

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-card border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">{error}</div>
      )}
      {!rules.feature_enabled && (
        <div className="rounded-card border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
          Catalog AI recommendations aren&apos;t enabled for your account. Your preferences below are saved but have no effect until support turns this on.
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <RuleCard
          title="AI Recommendations"
          description="Allow Aira to recommend matching catalog items when customers ask for options."
          checked={rules.can_recommend}
          disabled={controlsDisabled}
          onChange={(checked) => patch({ can_recommend: checked })}
        />
        <RuleCard
          title="Send Images"
          description="Allow Aira to send item images with its recommendation when the chat context calls for it."
          checked={rules.can_send_images}
          disabled={controlsDisabled}
          onChange={(checked) => patch({ can_send_images: checked })}
        />
        <div className="rounded-card border border-border bg-white p-5 shadow-sm">
          <h3 className="font-display text-base font-bold text-ink">Reply Limits</h3>
          <p className="mt-1 text-sm text-ink-muted">Default maximum images per AI reply (up to {rules.max_images_ceiling}).</p>
          <div className="mt-5 flex items-center gap-3">
            <button
              type="button"
              onClick={() => patch({ max_images_per_reply: Math.max(0, rules.max_images_per_reply - 1) })}
              disabled={controlsDisabled}
              className="h-9 w-9 rounded-xl border border-border text-lg font-bold text-ink-muted transition-colors hover:bg-surface-low disabled:opacity-40"
            >
              -
            </button>
            <span className="font-mono text-xl font-bold text-ink">{rules.max_images_per_reply}</span>
            <button
              type="button"
              onClick={() => patch({ max_images_per_reply: Math.min(rules.max_images_ceiling, rules.max_images_per_reply + 1) })}
              disabled={controlsDisabled || rules.max_images_per_reply >= rules.max_images_ceiling}
              className="h-9 w-9 rounded-xl border border-border text-lg font-bold text-ink-muted transition-colors hover:bg-surface-low disabled:opacity-40"
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
  disabled = false,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
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
          disabled={disabled}
          className={cn(
            "inline-flex h-8 w-14 shrink-0 items-center rounded-full p-1 transition-colors disabled:cursor-not-allowed disabled:opacity-45",
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
