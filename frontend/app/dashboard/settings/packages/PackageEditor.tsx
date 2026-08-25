"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { collectAllKeys, uniqueKey } from "./packageKeys";
import { slugify } from "../slugify";

export interface IntakeAddon {
  key: string;
  name: string;
  amount_paise: number;
  description: string;
  active: boolean;
  button_label?: string;
}

export interface IntakePackage {
  key: string;
  name: string;
  amount_paise: number;
  description: string;
  active: boolean;
  button_label?: string;
  options?: IntakePackage[];
  addons?: IntakeAddon[];
}

interface PackageEditorProps {
  packages: IntakePackage[];
  onChange: (packages: IntakePackage[]) => void;
  canManage: boolean;
}

export function PackageEditor({ packages, onChange, canManage }: PackageEditorProps) {
  function addRootPackage() {
    const existing = collectAllKeys(packages);
    const key = uniqueKey("package", existing);
    onChange([...packages, { key, name: "", amount_paise: 0, description: "", active: true }]);
  }

  function updateAt(index: number, next: IntakePackage) {
    onChange(packages.map((p, i) => (i === index ? next : p)));
  }

  function removeAt(index: number) {
    onChange(packages.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-2">
      {packages.map((pkg, index) => (
        <PackageNode
          key={pkg.key}
          node={pkg}
          depth={0}
          allKeys={collectAllKeys(packages)}
          onChange={(next) => updateAt(index, next)}
          onRemove={() => removeAt(index)}
          canManage={canManage}
        />
      ))}
      {packages.length === 0 && (
        <p className="font-body text-xs text-ink-muted italic">
          No packages yet — add at least one before enabling.
        </p>
      )}
      {canManage && (
        <button
          type="button"
          onClick={addRootPackage}
          className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700"
        >
          <Plus size={14} /> Add package
        </button>
      )}
    </div>
  );
}

function PackageNode({
  node, depth, allKeys, onChange, onRemove, canManage,
}: {
  node: IntakePackage; depth: number; allKeys: Set<string>;
  onChange: (next: IntakePackage) => void; onRemove: () => void; canManage: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const isLeaf = !node.options || node.options.length === 0;
  const hasAddons = !!node.addons && node.addons.length > 0;

  function commitName(name: string) {
    const others = new Set(allKeys);
    others.delete(node.key);
    onChange({ ...node, name, key: uniqueKey(slugify(name) || "package", others) });
  }

  function addSubPackage() {
    const key = uniqueKey("package", allKeys);
    const options = [...(node.options ?? []), { key, name: "", amount_paise: 0, description: "", active: true }];
    onChange({ ...node, options });
  }

  function updateOption(i: number, next: IntakePackage) {
    onChange({ ...node, options: (node.options ?? []).map((o, idx) => (idx === i ? next : o)) });
  }

  function removeOption(i: number) {
    const options = (node.options ?? []).filter((_, idx) => idx !== i);
    onChange({ ...node, options: options.length ? options : undefined });
  }

  function addAddon() {
    const key = uniqueKey("addon", allKeys);
    const addons = [...(node.addons ?? []), { key, name: "", amount_paise: 0, description: "", active: true }];
    onChange({ ...node, addons });
  }

  function updateAddon(i: number, patch: Partial<IntakeAddon>) {
    const addons = (node.addons ?? []).map((a, idx) => (idx === i ? { ...a, ...patch } : a));
    onChange({ ...node, addons });
  }

  function removeAddon(i: number) {
    const addons = (node.addons ?? []).filter((_, idx) => idx !== i);
    onChange({ ...node, addons: addons.length ? addons : undefined });
  }

  return (
    <div className="rounded-2xl border border-border bg-surface-subtle p-3 space-y-2" style={{ marginLeft: depth * 20 }}>
      <div className="flex items-center gap-2">
        {(!isLeaf || hasAddons) && (
          <button type="button" onClick={() => setExpanded(e => !e)} className="text-ink-muted">
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        )}
        <input
          type="text"
          value={node.name}
          onChange={(e) => onChange({ ...node, name: e.target.value })}
          onBlur={(e) => commitName(e.target.value)}
          placeholder="Package name (e.g. Basic)"
          disabled={!canManage}
          className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
        />
        {isLeaf && (
          <input
            type="number"
            min={1}
            value={node.amount_paise ? node.amount_paise / 100 : ""}
            onChange={(e) => onChange({ ...node, amount_paise: Math.round(Number(e.target.value) * 100) })}
            placeholder="₹"
            disabled={!canManage}
            className="w-24 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
          />
        )}
        <label className="flex items-center gap-1 text-xs font-body text-ink-muted whitespace-nowrap">
          <input type="checkbox" checked={node.active} disabled={!canManage} onChange={(e) => onChange({ ...node, active: e.target.checked })} />
          Active
        </label>
        {canManage && (
          <button type="button" onClick={onRemove} aria-label="Remove package" className="text-ink-muted hover:text-red-600">
            <Trash2 size={16} />
          </button>
        )}
      </div>

      <input
        type="text"
        value={node.description}
        onChange={(e) => onChange({ ...node, description: e.target.value })}
        placeholder="What's included"
        disabled={!canManage}
        className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
      />

      {isLeaf && (
        <input
          type="text"
          value={node.button_label ?? ""}
          onChange={(e) => onChange({ ...node, button_label: e.target.value || undefined })}
          placeholder="Short button label (optional, ≤20 chars — falls back to name)"
          maxLength={20}
          disabled={!canManage}
          className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
        />
      )}

      {canManage && (
        <div className="flex gap-3">
          {!hasAddons && (
            <button type="button" onClick={addSubPackage} className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700">
              <Plus size={12} /> Add sub-package
            </button>
          )}
          {isLeaf && !node.options && (
            <button type="button" onClick={addAddon} className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700">
              <Plus size={12} /> Add addon
            </button>
          )}
        </div>
      )}

      {expanded && node.options && node.options.length > 0 && (
        <div className="space-y-2 pt-1">
          {node.options.map((opt, i) => (
            <PackageNode
              key={opt.key}
              node={opt}
              depth={depth + 1}
              allKeys={allKeys}
              onChange={(next) => updateOption(i, next)}
              onRemove={() => removeOption(i)}
              canManage={canManage}
            />
          ))}
        </div>
      )}

      {expanded && hasAddons && (
        <div className="space-y-2 pt-1 pl-5 border-l-2 border-border">
          <div className="font-label text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Addons</div>
          {node.addons!.map((addon, i) => (
            <div key={addon.key} className="space-y-1">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={addon.name}
                  onChange={(e) => updateAddon(i, { name: e.target.value })}
                  onBlur={(e) => {
                    const others = new Set(allKeys);
                    others.delete(addon.key);
                    updateAddon(i, { key: uniqueKey(slugify(e.target.value) || "addon", others) });
                  }}
                  placeholder="Addon name"
                  disabled={!canManage}
                  className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                />
                <input
                  type="number"
                  min={0}
                  value={addon.amount_paise ? addon.amount_paise / 100 : ""}
                  onChange={(e) => updateAddon(i, { amount_paise: Math.round(Number(e.target.value) * 100) })}
                  placeholder="+₹"
                  disabled={!canManage}
                  className="w-20 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                />
                <label className="flex items-center gap-1 text-xs font-body text-ink-muted">
                  <input type="checkbox" checked={addon.active} disabled={!canManage} onChange={(e) => updateAddon(i, { active: e.target.checked })} />
                  Active
                </label>
                {canManage && (
                  <button type="button" onClick={() => removeAddon(i)} aria-label="Remove addon" className="text-ink-muted hover:text-red-600">
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
              <input
                type="text"
                value={addon.button_label ?? ""}
                onChange={(e) => updateAddon(i, { button_label: e.target.value || undefined })}
                placeholder="Short button label (optional, ≤20 chars — falls back to name)"
                maxLength={20}
                disabled={!canManage}
                className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
              />
            </div>
          ))}
          {canManage && (
            <button type="button" onClick={addAddon} className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700">
              <Plus size={12} /> Add another addon
            </button>
          )}
        </div>
      )}
    </div>
  );
}
