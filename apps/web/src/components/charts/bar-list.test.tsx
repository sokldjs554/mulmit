import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { BarList } from "./bar-list";

const data = [
  { key: "semantic", label: "의미 유사도", value: 21.4, note: "신호 86점 × 가중치 25%" },
  { key: "region", label: "관심 지역", value: 10 },
];

describe("BarList", () => {
  it("exposes each bar's value to assistive tech and offers a table view", async () => {
    render(<BarList data={data} format={(v) => `${v.toFixed(1)}점`} caption="적합도 기여" />);

    expect(screen.getByLabelText("의미 유사도 21.4점, 신호 86점 × 가중치 25%")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "표로 보기" }));

    const table = screen.getByRole("table");
    const row = within(table).getByRole("row", { name: /관심 지역/ });
    expect(within(row).getByText("10.0점")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "차트로 보기" })).toBeInTheDocument();
  });
});
