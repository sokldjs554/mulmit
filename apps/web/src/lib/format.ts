/** Korean-won and date formatting shared by the web app. */

export function formatKRW(value: number | null | undefined): string {
  if (value === null || value === undefined) return "금액 미상";
  if (value <= 0) return "0원";
  const eok = Math.floor(value / 100_000_000);
  const man = Math.floor((value % 100_000_000) / 10_000);
  const parts: string[] = [];
  if (eok) parts.push(`${eok.toLocaleString("ko-KR")}억`);
  if (man) parts.push(`${man.toLocaleString("ko-KR")}만`);
  if (!parts.length) return `${value.toLocaleString("ko-KR")}원`;
  return `${parts.join(" ")}원`;
}

/** Compact form for axes and tight UI: 350,000,000 → "3.5억", 48,000,000 → "4,800만". */
export function formatKRWCompact(value: number): string {
  if (value >= 100_000_000) {
    const eok = value / 100_000_000;
    return `${eok >= 10 ? Math.round(eok) : Number(eok.toFixed(1))}억`;
  }
  if (value >= 10_000) return `${Math.round(value / 10_000).toLocaleString("ko-KR")}만`;
  return value.toLocaleString("ko-KR");
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${y}.${m}.${d}`;
}

export function formatMonth(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [y, m] = iso.slice(0, 10).split("-");
  return `${y}.${m}`;
}

export function formatWindow(start: string | null, end: string | null): string {
  if (!start) return "미정";
  if (!end || start === end) return formatDate(start);
  return `${formatMonth(start)} ~ ${formatMonth(end)}`;
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "–";
  return `${(value * 100).toFixed(digits)}%`;
}

/** Time until the forecast bid window, read after "입찰" (입찰 임박 · 입찰 약 4개월 후). */
export function leadLabel(days: number | null | undefined): string | null {
  if (days === null || days === undefined) return null;
  if (days <= 0) return "임박";
  if (days < 45) return `약 ${days}일 후`;
  return `약 ${Math.round(days / 30)}개월 후`;
}

/** How far ahead of the tender the first signal came: 392 → "13개월", 40 → "40일". */
export function headStartLabel(days: number | null | undefined): string | null {
  if (!days || days <= 0) return null;
  if (days < 45) return `${days}일`;
  return `${Math.round(days / 30.4)}개월`;
}

export function formatUSD(value: number): string {
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
