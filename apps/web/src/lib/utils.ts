import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export const STAGES = [
  { key: "council_mention", label: "의회 발언", short: "의회" },
  { key: "budget_line", label: "예산 편성", short: "예산" },
  { key: "order_plan", label: "발주계획", short: "발주계획" },
  { key: "prespec", label: "사전규격", short: "사전규격" },
  { key: "bid_notice", label: "입찰공고", short: "입찰" },
  { key: "award", label: "낙찰·계약", short: "계약" },
] as const;

export type StageKey = (typeof STAGES)[number]["key"];

export function stageIndex(stage: string): number {
  return STAGES.findIndex((s) => s.key === stage);
}

export const COMMITMENT_LABEL: Record<string, string> = {
  committed: "확약 (반영·편성)",
  planned: "추진 계획",
  reviewing: "검토 수준",
  declined: "난색 표명",
};

export const STATUS_LABEL: Record<string, string> = {
  open: "진행 중",
  bid_open: "입찰 진행",
  closed: "종료",
  dormant: "휴면",
};
