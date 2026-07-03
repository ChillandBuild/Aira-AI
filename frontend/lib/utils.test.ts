import { describe, expect, it } from "vitest";
import { getHomeHref, isActive } from "./utils";

describe("isActive", () => {
  it("returns true for an exact path match", () => {
    expect(isActive("/dashboard/telecalling", "/dashboard/telecalling")).toBe(true);
  });

  it("returns true for a nested path under href", () => {
    expect(isActive("/dashboard/telecalling/scheduled", "/dashboard/telecalling")).toBe(true);
  });

  it("returns false for an unrelated path", () => {
    expect(isActive("/dashboard/conversations", "/dashboard/telecalling")).toBe(false);
  });

  it("returns false for a path that merely starts with the same characters", () => {
    expect(isActive("/dashboard/telecallingX", "/dashboard/telecalling")).toBe(false);
  });
});

describe("getHomeHref", () => {
  it("returns /dashboard/profile for callers", () => {
    expect(getHomeHref("caller")).toBe("/dashboard/profile");
  });

  it("returns /dashboard for owners", () => {
    expect(getHomeHref("owner")).toBe("/dashboard");
  });

  it("returns /dashboard while role is still loading (null)", () => {
    expect(getHomeHref(null)).toBe("/dashboard");
  });
});
