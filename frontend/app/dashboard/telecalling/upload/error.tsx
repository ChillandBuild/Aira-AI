"use client";
import { useEffect } from "react";

export default function UploadError({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => {
    console.error("Telecalling upload page error:", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[40vh] text-center px-6">
      <p className="text-sm text-red-600 font-medium mb-2">Failed to load page</p>
      <p className="text-xs text-[#78716c] mb-4 max-w-md">{error?.message || "Unknown error"}</p>
      <button onClick={reset} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">
        Retry
      </button>
    </div>
  );
}
