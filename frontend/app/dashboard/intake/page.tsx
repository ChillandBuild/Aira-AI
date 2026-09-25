"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Intake is now a tab of Deals — this route only redirects old links/bookmarks. */
export default function IntakeRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboard/deals?tab=forms");
  }, [router]);
  return null;
}
