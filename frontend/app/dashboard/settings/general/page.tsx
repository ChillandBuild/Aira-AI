"use client";
import { Crown } from "lucide-react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { useSettingsForm } from "../SettingsFormContext";
import ChangePasswordCard from "../ChangePasswordCard";

export default function GeneralSettingsPage() {
  const { fullName, initials, email, memberSince } = useSettingsForm();
  const { tenantName } = useAuthRole();

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h1 className="break-words font-display text-2xl font-bold text-ink sm:text-3xl">
          {tenantName || "Your Workspace"}
        </h1>

        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#2e1065] to-primary text-sm font-bold text-white shadow-md shadow-primary/20">
            {initials}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-display text-sm font-bold text-ink">{fullName}</span>
              <span className="badge-violet inline-flex items-center gap-1 px-2 py-0.5 font-label text-[10px] font-bold uppercase tracking-wider">
                <Crown size={11} />
                Admin
              </span>
            </div>
            {email && <p className="break-all font-body text-xs text-ink-muted">{email}</p>}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 sm:gap-4">
          {memberSince && (
            <span className="font-label text-xs text-ink-muted">Member since {memberSince}</span>
          )}
          <span className="flex items-center gap-1.5 font-label text-xs text-emerald-600">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            All systems online
          </span>
        </div>
      </div>

      <ChangePasswordCard />
    </div>
  );
}
