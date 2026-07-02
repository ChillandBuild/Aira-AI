"use client";
import { AlertTriangle, RefreshCw } from "lucide-react";

export function BackendUnreachable() {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-6 text-center">
      <div className="w-14 h-14 rounded-card bg-primary-light text-primary flex items-center justify-center mb-5">
        <AlertTriangle size={26} />
      </div>
      <h2 className="text-xl font-bold text-ink tracking-tight">Can&apos;t reach the server</h2>
      <p className="text-sm text-ink-secondary max-w-md mt-2 leading-relaxed">
        The backend may be waking up or briefly unavailable. Your session is safe — give it a few
        seconds and retry.
      </p>
      <button
        onClick={() => location.reload()}
        className="mt-6 flex items-center gap-2 px-5 py-2.5 bg-primary text-white rounded-xl text-sm font-medium hover:bg-primary-dark transition-colors shadow-card"
      >
        <RefreshCw size={15} />
        Retry
      </button>
    </div>
  );
}
