"use client";

import { cn } from "@/lib/utils";

function initialsFor(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean).slice(0, 2);
  const letters = words.map((w) => w[0]?.toUpperCase() ?? "").join("");
  return letters || "?";
}

/** Product thumbnail cell: real photo when we have one, otherwise a violet initials tile. */
export function ItemThumb({
  name,
  thumbnailUrl,
  size = 40,
  className,
}: {
  name: string;
  thumbnailUrl?: string | null;
  size?: number;
  className?: string;
}) {
  if (thumbnailUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={thumbnailUrl}
        alt={name}
        className={cn("shrink-0 rounded-lg object-cover", className)}
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center rounded-lg bg-primary/10 font-label text-xs font-bold text-primary",
        className
      )}
      style={{ width: size, height: size }}
      aria-hidden
    >
      {initialsFor(name)}
    </div>
  );
}
