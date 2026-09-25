"use client";

import { useId, useState } from "react";

import { formatDate, formatKRW, formatKRWCompact } from "@/lib/format";

import { useWidth } from "./use-width";

export type BudgetPoint = { observed_at: string; amount: number; stage_label: string };

/**
 * How the amount moved as the project travelled through the lifecycle (spoken estimate in
 * council → exact 천원 figure in the budget book → 배정예산 in the notice). One series, 2px line,
 * 8px markers with a 2px surface ring, a crosshair that snaps to the nearest point, and a
 * direct label on the latest value only.
 */
export function BudgetLine({ points }: { points: BudgetPoint[] }) {
  const id = useId();
  const [active, setActive] = useState<number | null>(null);
  const [ref, width] = useWidth<HTMLDivElement>(320);
  const first = points[0];
  const lastPoint = points[points.length - 1];
  if (points.length < 2 || !first || !lastPoint) return null;

  const height = 170;
  const pad = { l: 44, r: 52, t: 14, b: 26 };
  const pts = points.map((p) => ({ ...p, t: new Date(p.observed_at).getTime() }));
  const t0 = Math.min(...pts.map((p) => p.t));
  const t1 = Math.max(...pts.map((p) => p.t));
  const vMin = Math.min(...pts.map((p) => p.amount));
  const vMax = Math.max(...pts.map((p) => p.amount));
  const span = Math.max(vMax - vMin, vMax * 0.1);
  const lo = Math.max(0, vMin - span * 0.35);
  const hi = vMax + span * 0.35;
  const x = (t: number) => pad.l + ((t - t0) / Math.max(t1 - t0, 1)) * (width - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo)) * (height - pad.t - pad.b);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(p.t)},${y(p.amount)}`).join(" ");
  const ticks = [lo, (lo + hi) / 2, hi];
  const lastPt = pts[pts.length - 1] ?? pts[0]!;
  const activePt = active !== null ? pts[active] : undefined;

  const onMove = (clientX: number, rect: DOMRect) => {
    const px = ((clientX - rect.left) / rect.width) * width;
    let best = 0;
    let bestDist = Number.POSITIVE_INFINITY;
    pts.forEach((p, i) => {
      const dist = Math.abs(x(p.t) - px);
      if (dist < bestDist) {
        best = i;
        bestDist = dist;
      }
    });
    setActive(best);
  };

  return (
    <figure aria-labelledby={`${id}-cap`} className="space-y-2">
      <figcaption id={`${id}-cap`} className="text-[12px] text-muted">
        단계별로 확인된 금액의 변화
      </figcaption>
      <div ref={ref} className="relative">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          className="block touch-none"
          role="img"
          aria-label={`금액 추이: ${points.map((p) => `${p.stage_label} ${formatKRW(p.amount)}`).join(", ")}`}
          onPointerMove={(e) => onMove(e.clientX, e.currentTarget.getBoundingClientRect())}
          onPointerLeave={() => setActive(null)}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} stroke="var(--line)" />
              <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--muted)" className="tabular">
                {formatKRWCompact(t)}
              </text>
            </g>
          ))}
          <path d={d} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {activePt ? (
            <line x1={x(activePt.t)} x2={x(activePt.t)} y1={pad.t} y2={height - pad.b} stroke="var(--line-strong)" />
          ) : null}
          {pts.map((p, i) => (
            <circle
              key={`${p.observed_at}-${i}`}
              cx={x(p.t)}
              cy={y(p.amount)}
              r={active === i ? 5.5 : 4}
              fill="var(--series-1)"
              stroke="var(--surface)"
              strokeWidth={2}
            />
          ))}
          <text x={x(lastPt.t) + 10} y={y(lastPt.amount) + 4} fontSize={12} fontWeight={600} fill="var(--ink)">
            {formatKRWCompact(lastPt.amount)}
          </text>
          <text x={pad.l} y={height - 6} fontSize={11} fill="var(--muted)">
            {formatDate(first.observed_at)}
          </text>
          <text x={width - pad.r} y={height - 6} fontSize={11} fill="var(--muted)" textAnchor="end">
            {formatDate(lastPoint.observed_at)}
          </text>
        </svg>
        {activePt ? (
          <div
            role="tooltip"
            className="pointer-events-none absolute top-0 rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12px] shadow-lg"
            style={{ left: `${(x(activePt.t) / width) * 100}%`, transform: "translateX(-50%)" }}
          >
            <div className="font-semibold text-ink">{formatKRW(activePt.amount)}</div>
            <div className="text-muted">
              {activePt.stage_label} · {formatDate(activePt.observed_at)}
            </div>
          </div>
        ) : null}
      </div>
    </figure>
  );
}

export function StatTile({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-line bg-surface px-4 py-3.5 shadow-card">
      <div className="text-[12px] text-muted">{label}</div>
      <div className="mt-1 text-[22px] font-semibold tracking-tight text-ink">{value}</div>
      {sub ? <div className="mt-0.5 text-[12px] text-muted">{sub}</div> : null}
    </div>
  );
}
