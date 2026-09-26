import { redirect } from "next/navigation";

// "What Aira Sells" moved to the top-level Services page, next to Products —
// kept as a redirect so any bookmarked or hardcoded link still lands somewhere useful.
export default function PackagesRedirect() {
  redirect("/dashboard/services");
}
