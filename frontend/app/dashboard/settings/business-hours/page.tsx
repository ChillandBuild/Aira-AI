import { redirect } from "next/navigation";

// Business hours now live in the Description (one place, nothing to contradict).
export default function BusinessHoursRedirect() {
  redirect("/dashboard/knowledge?tab=description");
}
