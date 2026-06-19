"use client";
import { useEffect } from "react";
import { RefreshCw, AlertTriangle } from "lucide-react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Dashboard render error:", error);
  }, [error]);

  const isNetwork =
    /reach server|failed to fetch|networkerror|load failed/i.test(error?.message || "");

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-6 text-center">
      <div className="w-14 h-14 rounded-2xl bg-rose-100 text-rose-600 flex items-center justify-center mb-5">
        <AlertTriangle size={26} />
      </div>
      <h2 className="font-display text-xl font-extrabold text-[#1c1917] tracking-tight">
        {isNetwork ? "Can't reach the server" : "Something went wrong"}
      </h2>
      <p className="font-body text-sm text-[#78716c] max-w-md mt-2 leading-relaxed">
        {isNetwork
          ? "The backend may be waking up or briefly unavailable. Your data is safe — give it a few seconds and retry."
          : "This view hit an unexpected error and couldn't render. You can retry without losing your session."}
      </p>
      <button
        onClick={reset}
        className="mt-6 flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white rounded-2xl font-label text-sm font-bold transition-all shadow-sm hover:scale-[1.02] active:scale-[0.98]"
      >
        <RefreshCw size={15} />
        Retry
      </button>
    </div>
  );
}
