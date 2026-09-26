import { redirect } from "next/navigation";

// Moved into the Knowledge page, next to the handover line — kept as a
// redirect so any bookmarked or hardcoded link still lands somewhere useful.
export default function BusinessHoursRedirect() {
  redirect("/dashboard/knowledge#business-hours");
}
