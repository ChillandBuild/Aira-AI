import { redirect } from "next/navigation";

// TeleCMI credentials moved into Connect Channels as their own section —
// kept as a redirect so any bookmarked or hardcoded link still lands somewhere useful.
export default function TelecallingCredentialsRedirect() {
  redirect("/dashboard/settings/connect-channels#calling");
}
