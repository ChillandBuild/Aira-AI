export type ComparisonSelection = {
  mode: "off" | "previous" | "custom";
  start: string;
  end: string;
};

type ReportingSelection = {
  preset: string;
  start: string;
  end: string;
};

function hasChronologicalDates(start: string, end: string): boolean {
  return Boolean(start && end && start <= end);
}

export function isCompleteSelection(selection: ReportingSelection): boolean {
  return selection.preset !== "custom"
    || hasChronologicalDates(selection.start, selection.end);
}

export function canLoadComparison(
  reporting: ReportingSelection,
  comparison: ComparisonSelection,
): boolean {
  return isCompleteSelection(reporting)
    && (comparison.mode !== "custom"
      || hasChronologicalDates(comparison.start, comparison.end));
}
