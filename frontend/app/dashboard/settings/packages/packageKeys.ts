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
