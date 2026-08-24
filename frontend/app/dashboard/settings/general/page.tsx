"use client";
import { Crown } from "lucide-react";
import { useSettingsForm } from "../SettingsFormContext";
import ChangePasswordCard from "../ChangePasswordCard";

export default function GeneralSettingsPage() {
  const { fullName, initials, email, memberSince } = useSettingsForm();

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#1c1917] via-[#292524] to-[#1c1917] p-5 shadow-xl sm:rounded-[2rem] sm:p-8">
        <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-primary/10 to-transparent rounded-full -translate-y-1/2 translate-x-1/3" />
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-gradient-to-tr from-amber-500/10 to-transparent rounded-full translate-y-1/2 -translate-x-1/4" />

        <div className="relative flex min-w-0 flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#2e1065] to-primary shadow-lg shadow-primary/25 sm:h-20 sm:w-20">
            <span className="font-display text-2xl font-bold text-white sm:text-3xl">{initials}</span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h2 className="break-words font-display text-xl font-bold text-white sm:text-2xl">{fullName}</h2>
              <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/30">
                <Crown size={12} className="text-amber-400" />
                <span className="font-label text-xs font-bold text-amber-300 uppercase tracking-wider">Admin</span>
              </span>
            </div>
            {email && (
              <p className="mt-1 break-all font-body text-sm text-[#a8a29e]">{email}</p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-3 sm:gap-4">
              {memberSince && (
                <span className="font-label text-xs text-[#78716c]">Member since {memberSince}</span>
              )}
              <span className="flex items-center gap-1.5 font-label text-xs text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                All systems online
              </span>
            </div>
          </div>
        </div>

        <div className="relative mt-6 pt-6 border-t border-[#44403c]/50">
          <p className="font-body text-sm text-[#a8a29e] italic leading-relaxed">
            &quot;The best leaders don&apos;t create followers — they create more leaders.&quot;
          </p>
          <p className="font-label text-[10px] text-[#57534e] mt-1 uppercase tracking-widest">Your role: Empower your team</p>
        </div>
      </div>

      <ChangePasswordCard />
    </div>
  );
}
