import { redirect } from "next/navigation";

// Merged into the Services page — kept as a redirect so any bookmarked or
// hardcoded link to this URL still lands somewhere useful.
export default function IntakeConfigRedirect() {
  redirect("/dashboard/services");
}
