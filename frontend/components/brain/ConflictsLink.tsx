"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { useConsistencyCount } from "@/hooks/useBrainCount";
import { conflictsLinkText } from "./brainLogic";

/**
 * One line on Knowledge, Services and Catalog: how many things disagree with
 * Aira's setup, and a link to the hub, where they are fixed (blueprint 9A).
 * Draws nothing at 0, before the first count, or without knowledge access.
 */
export function ConflictsLink({ className }: { className?: string }) {
  const { role, permissions } = useAuthRole();
  const canView = role === "owner" || permissions.includes("knowledge.view") || permissions.includes("knowledge.manage");
  const count = useConsistencyCount(canView);
  if (count === null) return null;
  return (
    <p className={className ?? "mb-4"}>
      <Link
        href="/dashboard/brain"
        className="inline-flex max-w-full items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 font-body text-xs text-ink hover:border-amber-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <AlertTriangle size={14} className="mt-px shrink-0 text-amber-700" aria-hidden />
        <span className="min-w-0 break-words">
          {conflictsLinkText(count)} <span className="font-semibold text-primary underline-offset-2 hover:underline">open the Hub</span>
        </span>
      </Link>
    </p>
  );
}
