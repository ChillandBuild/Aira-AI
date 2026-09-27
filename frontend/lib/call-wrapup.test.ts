import { describe, expect, it } from "vitest";
import {
  RESULT_OPTIONS,
  callResultKey,
  callResultLabel,
  callResultTone,
  formatIstWhen,
  fromIstInputs,
  isClosedLeadStatus,
  isWorkingLeadStatus,
  leadStatusTone,
  LEAD_STATUS_LABEL,
  quickTimes,
  resultOption,
  toIstInputs,
} from "./call-wrapup";

const NOW = new Date("2026-09-27T08:30:00Z"); // Sunday 14:00 IST

describe("quick times (IST, whatever the machine's time zone)", () => {
  it("offers in 1 hour, this evening 6 PM and tomorrow 10 AM", () => {
    const [hour, evening, tomorrow] = quickTimes(NOW);
    expect(hour.at.toISOString()).toBe("2026-09-27T09:30:00.000Z");
    expect(evening.at.toISOString()).toBe("2026-09-27T12:30:00.000Z");
    expect(evening.disabled).toBe(false);
    expect(tomorrow.at.toISOString()).toBe("2026-09-28T04:30:00.000Z");
  });

  it("disables this evening once 6 PM IST has passed", () => {
    expect(quickTimes(new Date("2026-09-27T13:30:00Z"))[1].disabled).toBe(true);
  });

  it("round-trips date and time inputs as IST", () => {
    expect(toIstInputs(new Date("2026-09-28T04:30:00Z"))).toEqual({ date: "2026-09-28", time: "10:00" });
    expect(fromIstInputs("2026-10-02", "11:00")?.toISOString()).toBe("2026-10-02T05:30:00.000Z");
    expect(fromIstInputs("", "11:00")).toBeNull();
  });

  it("formats times for people", () => {
    expect(formatIstWhen(new Date("2026-09-27T12:30:00Z"), NOW)).toBe("Today, 6:00 PM");
    expect(formatIstWhen(new Date("2026-09-28T04:30:00Z"), NOW)).toBe("Tomorrow, 10:00 AM");
    expect(formatIstWhen(new Date("2026-10-02T05:30:00Z"), NOW)).toBe("Fri 2 Oct, 11:00 AM");
  });
});

describe("labels and tones", () => {
  it("has the ten results with their rules", () => {
    expect(RESULT_OPTIONS.map((o) => o.value)).toHaveLength(10);
    expect(resultOption("interested_booked")).toMatchObject({ time: "required", notes: true });
    expect(resultOption("maybe_later").time).toBe("optional");
    expect(resultOption("converted")).toMatchObject({ time: null, notes: true });
  });

  it("labels a call by its result, else by whether it connected", () => {
    expect(callResultLabel(callResultKey({ outcome: "interested_booked", manual_status: "connected" }))).toBe("Interested, next step booked");
    expect(callResultLabel(callResultKey({ outcome: null, manual_status: "busy" }))).toBe("Busy");
    expect(callResultLabel(null)).toBeNull();
    expect(callResultTone("converted")).toBe("won");
    expect(callResultTone("not_picked")).toBe("missed");
    expect(callResultTone("something_old")).toBe("neutral");
  });

  it("groups lead statuses", () => {
    expect(LEAD_STATUS_LABEL.callback).toBe("Call later");
    expect(leadStatusTone("hot")).toBe("hot");
    expect(isClosedLeadStatus("disqualified")).toBe(true);
    expect(isClosedLeadStatus("warm")).toBe(false);
    expect(isWorkingLeadStatus("language_barrier")).toBe(true);
    expect(isWorkingLeadStatus(null)).toBe(false);
  });
});
