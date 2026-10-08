"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ChannelsPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard/settings/connect-channels");
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <p className="font-body text-sm text-[#475569]">Redirecting to Account Settings…</p>
    </div>
  );
}
