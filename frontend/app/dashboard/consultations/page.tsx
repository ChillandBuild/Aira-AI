import { redirect } from "next/navigation";

export default function ConsultationsRedirect() {
  redirect("/dashboard/deals?tab=forms");
}
