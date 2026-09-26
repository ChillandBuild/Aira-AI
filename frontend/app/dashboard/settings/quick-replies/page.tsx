import { redirect } from "next/navigation";

// Saved quick replies were removed: Aira turns every choice it offers into buttons itself,
// and a saved message could quote prices that disagree with the Services page.
export default function QuickRepliesRedirect() {
  redirect("/dashboard/services");
}
