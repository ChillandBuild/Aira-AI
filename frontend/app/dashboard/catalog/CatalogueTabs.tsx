"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuthRole } from "../contexts/AuthRoleContext";

export function CatalogueTabs() {
  const pathname = usePathname();
  const { role, permissions } = useAuthRole();
  const canViewProducts = role === "owner" || permissions.includes("catalog.view") || permissions.includes("catalog.manage");
  const canViewServices = role === "owner" || permissions.includes("services.view") || permissions.includes("services.manage");

  const tabs = [
    {
      href: "/dashboard/catalog",
      label: "Products",
      visible: canViewProducts,
      active: pathname.startsWith("/dashboard/catalog"),
    },
    {
      href: "/dashboard/services",
      label: "Services",
      visible: canViewServices,
      active: pathname.startsWith("/dashboard/services"),
    },
  ].filter((tab) => tab.visible);

  if (tabs.length === 0) return null;

  return (
    <div className="flex w-full flex-wrap gap-1 rounded-xl border border-border bg-white p-1 shadow-sm md:w-fit">
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          aria-current={tab.active ? "page" : undefined}
          className={cn(
            "inline-flex min-h-9 items-center gap-2 rounded-lg px-3 text-sm font-semibold transition-colors",
            tab.active ? "bg-primary text-white" : "text-ink-muted hover:bg-surface-low hover:text-ink"
          )}
        >
          <span>{tab.label}</span>
        </Link>
      ))}
    </div>
  );
}
