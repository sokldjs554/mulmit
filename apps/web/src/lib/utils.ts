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
  committed: "반영하겠다고 답함",
  planned: "추진하겠다고 답함",
  reviewing: "검토하겠다고 답함",
  declined: "어렵다고 답함",
};

export const STATUS_LABEL: Record<string, string> = {
  open: "공고 전",
  bid_open: "입찰 진행 중",
  closed: "종료",
  dormant: "한동안 소식 없음",
};
