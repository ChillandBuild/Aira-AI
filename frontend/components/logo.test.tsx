import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AnrilLogo, AnrilMark } from "./logo";

const TEAL = "#038285";

function countFill(markup: string, color: string): number {
  return markup.split(`fill="${color}"`).length - 1;
}

describe("AnrilLogo", () => {
  it("is one labelled image: the square mark plus the anril AI wordmark", () => {
    const markup = renderToStaticMarkup(<AnrilLogo />);

    expect(markup).toContain('aria-label="Anril AI"');
    expect(markup.match(/<rect /g)).toHaveLength(4);
    // Teal: the mark's top-right square, the i-dot and "AI".
    expect(countFill(markup, TEAL)).toBe(3);
  });

  it("keeps the same teal on navy; only the letters and squares follow currentColor", () => {
    const markup = renderToStaticMarkup(<AnrilLogo className="text-white" />);

    expect(countFill(markup, TEAL)).toBe(3);
    expect(countFill(markup, "currentColor")).toBe(4);
  });

  it("sizes its width from the height so callers can pass height alone", () => {
    const markup = renderToStaticMarkup(<AnrilLogo height={40} />);

    expect(markup).toMatch(/width="(\d+)"/);
    const width = Number(markup.match(/width="(\d+)"/)?.[1]);
    expect(width).toBeGreaterThan(200);
  });
});

describe("AnrilMark", () => {
  it("is the four-square mark alone, top-right square teal", () => {
    const markup = renderToStaticMarkup(<AnrilMark />);

    expect(markup).toContain('aria-label="Anril AI"');
    expect(markup.match(/<rect /g)).toHaveLength(4);
    expect(countFill(markup, TEAL)).toBe(1);
    expect(markup).toContain('x="105" y="0"');
  });
});
