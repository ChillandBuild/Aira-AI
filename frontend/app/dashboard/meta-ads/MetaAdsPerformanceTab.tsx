"use client";
type Props = {
  dateFrom: string; dateTo: string;
  setDateFrom: (v: string) => void; setDateTo: (v: string) => void;
};
export function MetaAdsPerformanceTab(props: Props) {
  void props;
  return <div className="text-sm text-on-surface-muted">Performance tab — built in Task 7.</div>;
}
