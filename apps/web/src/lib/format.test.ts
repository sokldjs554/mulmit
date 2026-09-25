import { describe, expect, it } from "vitest";

import { formatKRW, formatKRWCompact, formatPercent, formatWindow, headStartLabel, leadLabel } from "./format";

describe("formatKRW", () => {
  it("renders 억/만 units the way budget books read aloud", () => {
    expect(formatKRW(1_250_000_000)).toBe("12억 5,000만원");
    expect(formatKRW(350_000_000)).toBe("3억 5,000만원");
    expect(formatKRW(48_000_000)).toBe("4,800만원");
    expect(formatKRW(200_000_000)).toBe("2억원");
  });

  it("does not invent a number when the amount is unknown", () => {
    expect(formatKRW(null)).toBe("금액 미상");
    expect(formatKRW(undefined)).toBe("금액 미상");
  });

  it("falls back to plain won below 만", () => {
    expect(formatKRW(9_500)).toBe("9,500원");
  });
});

describe("formatKRWCompact", () => {
  it("keeps one decimal under 10억 and rounds above", () => {
    expect(formatKRWCompact(350_000_000)).toBe("3.5억");
    expect(formatKRWCompact(1_260_000_000)).toBe("13억");
    expect(formatKRWCompact(48_000_000)).toBe("4,800만");
  });
});

describe("timing labels", () => {
  it("collapses a single-day window and shows month ranges otherwise", () => {
    expect(formatWindow("2027-03-01", "2027-03-01")).toBe("2027.03.01");
    expect(formatWindow("2027-03-01", "2027-06-30")).toBe("2027.03 ~ 2027.06");
    expect(formatWindow(null, null)).toBe("미정");
  });

  it("switches from days to months after ~6 weeks", () => {
    expect(leadLabel(0)).toBe("임박");
    expect(leadLabel(30)).toBe("약 30일 후");
    expect(leadLabel(300)).toBe("약 10개월 후");
    expect(leadLabel(null)).toBeNull();
  });

  it("formats probabilities as percentages", () => {
    expect(formatPercent(0.876)).toBe("88%");
    expect(formatPercent(0.876, 1)).toBe("87.6%");
    expect(formatPercent(null)).toBe("–");
  });
});

describe("headStartLabel", () => {
  it("reads in months once the head start is longer than about six weeks", () => {
    expect(headStartLabel(392)).toBe("13개월");
    expect(headStartLabel(193)).toBe("6개월");
    expect(headStartLabel(40)).toBe("40일");
  });

  it("shows nothing when the tender was the first thing we saw", () => {
    expect(headStartLabel(null)).toBeNull();
    expect(headStartLabel(0)).toBeNull();
  });
});
