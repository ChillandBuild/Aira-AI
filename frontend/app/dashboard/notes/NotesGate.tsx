"use client";
import { Loader2 } from "lucide-react";
import type { Lead } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { NotesClient } from "./NotesClient";
import CallReview from "./review/CallReview";

/** Owners and managers review the team in Call Review; telecallers keep their notes page. */
export function NotesGate({ fallbackLeads }: { fallbackLeads: { data: Lead[] } | null }) {
  const { role, permissions, loading } = useAuthRole();
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center py-24">
        <Loader2 size={20} className="animate-spin text-primary" />
      </div>
    );
  }
  if (role === "owner" || permissions.includes("team.manage")) return <CallReview />;
  return <NotesClient fallbackLeads={fallbackLeads} />;
}
