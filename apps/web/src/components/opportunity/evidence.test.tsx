import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { EvidenceContext, highlightSegments } from "./evidence";

const ev = (start: number | null, end: number | null, found = true) => ({
  quote: "",
  found,
  score: 1,
  start,
  end,
  method: "exact",
});

describe("highlightSegments", () => {
  const context = "위원: 스마트쉘터를 내년에 확대할 계획입니까? 과장: 본예산에 반영하겠습니다.";

  it("maps document-level offsets into the context window", () => {
    // the context starts at document offset 1000
    const start = 1000 + context.indexOf("본예산에 반영하겠습니다");
    const segments = highlightSegments(context, 1000, [ev(start, start + "본예산에 반영하겠습니다".length)]);
    expect(segments.filter((s) => s.marked).map((s) => s.text)).toEqual(["본예산에 반영하겠습니다"]);
    expect(segments.map((s) => s.text).join("")).toBe(context);
  });

  it("merges overlapping evidence spans and ignores unverified quotes", () => {
    const a = context.indexOf("스마트쉘터");
    const segments = highlightSegments(context, 0, [
      ev(a, a + 8),
      ev(a + 4, a + 14),
      ev(0, 3, false),
      ev(null, null),
    ]);
    const marked = segments.filter((s) => s.marked);
    expect(marked).toHaveLength(1);
    expect(marked[0]?.text).toBe(context.slice(a, a + 14));
  });

  it("clamps spans that run past the context edges", () => {
    const segments = highlightSegments("abcdef", 10, [ev(8, 12), ev(15, 30)]);
    expect(segments).toEqual([
      { text: "ab", marked: true },
      { text: "cde", marked: false },
      { text: "f", marked: true },
    ]);
  });
});

describe("EvidenceContext", () => {
  it("highlights the quote with <mark> and expands long context on demand", async () => {
    const lead = "가".repeat(800);
    const context = `${lead} 과장: 본예산에 반영하겠습니다.`;
    const start = context.indexOf("본예산");
    render(<EvidenceContext context={context} contextOffset={0} evidence={[ev(start, start + 12)]} maxChars={100} />);

    expect(screen.queryByText("본예산에 반영하겠습니다")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByText("본예산에 반영하겠습니다").tagName).toBe("MARK");
  });

  it("falls back to the bare quote when no context was stored", () => {
    render(
      <EvidenceContext
        context={null}
        contextOffset={null}
        evidence={[{ ...ev(null, null), quote: "타당성 용역을 추진하겠습니다" }]}
      />,
    );
    expect(screen.getByText(/타당성 용역을 추진하겠습니다/)).toBeInTheDocument();
  });
});
