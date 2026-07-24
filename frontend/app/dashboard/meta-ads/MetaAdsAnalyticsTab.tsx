"use client";
type Props = {
  dateFrom: string; dateTo: string;
  setDateFrom: (v: string) => void; setDateTo: (v: string) => void;
};
export function MetaAdsAnalyticsTab(props: Props) {
  void props;
  return <div className="text-sm text-on-surface-muted">Analytics tab — built in Task 8.</div>;
}
