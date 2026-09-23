import { API_URL, getAuthHeaders } from "@/lib/api";

interface ScanResponse {
  csv_text: string;
  rows_found: number;
}

// Shared by the telecalling upload and outbound-leads pages: OCRs a photographed or
// scanned notebook page (image/PDF) into CSV text server-side, then wraps it as a
// File so it can drop straight into the existing CSV parse/upload pipeline unchanged.
export async function convertScanToCsv(file: File): Promise<File> {
  const headers = await getAuthHeaders();
  const fd = new FormData();
  fd.append("file", file);

  const res = await fetch(`${API_URL}/api/v1/upload/scan`, {
    method: "POST",
    body: fd,
    headers: { ...headers },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Could not read this scan" }));
    throw new Error(err.detail || `Scan failed (${res.status})`);
  }

  const data: ScanResponse = await res.json();
  if (!data.rows_found) {
    throw new Error("Could not find any phone numbers in this scan");
  }

  return new File([data.csv_text], `scan_${Date.now()}.csv`, { type: "text/csv" });
}
