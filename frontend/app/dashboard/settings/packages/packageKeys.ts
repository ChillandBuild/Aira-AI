interface KeyedNode {
  key: string;
  options?: KeyedNode[];
  addons?: { key: string }[];
}

export function collectAllKeys(packages: KeyedNode[]): Set<string> {
  const keys = new Set<string>();
  const visit = (nodes: KeyedNode[]) => {
    for (const n of nodes) {
      keys.add(n.key);
      if (n.options) visit(n.options);
      if (n.addons) n.addons.forEach(a => keys.add(a.key));
    }
  };
  visit(packages);
  return keys;
}

export function uniqueKey(base: string, existing: Set<string>): string {
  if (!existing.has(base)) return base;
  let n = 2;
  while (existing.has(`${base}_${n}`)) n++;
  return `${base}_${n}`;
}

interface ActiveNode {
  active: boolean;
  options?: ActiveNode[];
  addons?: { active: boolean }[];
}

const WHATSAPP_LIST_MAX = 10;
// The backend always adds one synthetic "No thanks" tap target to an addons menu
// (see _send_menu / _NO_ADDONS_OPTION in intake.py) -- so a level of addons only
// has headroom for 9 active entries before that decline option pushes it over
// WhatsApp's real 10-row cap.
const ADDON_LIST_MAX = WHATSAPP_LIST_MAX - 1;

function countActive(nodes: { active: boolean }[]): number {
  return nodes.filter((n) => n.active).length;
}

export function hasOversizedLevel(packages: ActiveNode[]): boolean {
  if (countActive(packages) > WHATSAPP_LIST_MAX) return true;
  for (const node of packages) {
    if (node.options && node.options.length > 0 && hasOversizedLevel(node.options)) {
      return true;
    }
    if (node.addons && countActive(node.addons) > ADDON_LIST_MAX) return true;
  }
  return false;
}
