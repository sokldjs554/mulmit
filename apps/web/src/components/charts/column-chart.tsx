"use client";

import { useId, useMemo, useState } from "react";

import { useWidth } from "./use-width";

export type ColumnDatum = { key: string; label: string; value: number; detail?: string };

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / exp;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * exp;
}

/**
 * Single-series columns over time (e.g. LLM spend per day). One y-axis, hairline grid,
 * columns ≤ 24px with 4px rounded caps and a 2px surface gap; each column is a hover/focus
 * target with a tooltip; the table view carries every value.
 */
export function ColumnChart({
  data,
  format,
  caption,
  height = 180,
}: {
  data: ColumnDatum[];
  format: (v: number) => string;
  caption: string;
  height?: number;
}) {
  const id = useId();
  const [active, setActive] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const top = useMemo(() => niceMax(Math.max(...data.map((d) => d.value), 0)), [data]);
  const ticks = [0, top / 2, top];
  const padLeft = 44;
  const padBottom = 22;
  const [ref, width] = useWidth<HTMLDivElement>(640);
  const plotW = width - padLeft - 8;
  const plotH = height - padBottom - 8;
  const band = data.length ? plotW / data.length : plotW;
  const barW = Math.min(24, Math.max(band - 2, 2));

  return (
    <figure aria-labelledby={`${id}-cap`} className="space-y-2">
      <div className="flex items-center justify-between">
        <figcaption id={`${id}-cap`} className="text-[12px] text-muted">
          {caption}
        </figcaption>
        <button
          type="button"
          className="text-[12px] text-accent-text hover:underline"
          onClick={() => setAsTable((v) => !v)}
        >
          {asTable ? "차트로 보기" : "표로 보기"}
        </button>
      </div>
      {asTable ? (
        <table className="w-full text-[13px]">
          <tbody>
            {data.map((d) => (
              <tr key={d.key} className="border-b border-line last:border-0">
                <th scope="row" className="py-1.5 text-left font-normal text-ink-2">
                  {d.label}
                </th>
                <td className="tabular py-1.5 text-right text-ink">{format(d.value)}</td>
                <td className="py-1.5 pl-3 text-right text-muted">{d.detail ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div ref={ref} className="relative">
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block" role="img" aria-label={caption}>
            {ticks.map((t) => {
              const y = 8 + plotH - (t / top) * plotH;
              return (
                <g key={t}>
                  <line x1={padLeft} x2={width - 8} y1={y} y2={y} stroke="var(--line)" strokeWidth={1} />
                  <text x={padLeft - 6} y={y + 4} textAnchor="end" fontSize={11} fill="var(--muted)" className="tabular">
                    {format(t)}
                  </text>
                </g>
              );
            })}
            {data.map((d, i) => {
              const h = top > 0 ? (d.value / top) * plotH : 0;
              const x = padLeft + i * band + (band - barW) / 2;
              const y = 8 + plotH - h;
              const r = Math.min(4, h / 2, barW / 2);
              const path =
                h <= 0
                  ? ""
                  : `M${x},${8 + plotH} V${y + r} Q${x},${y} ${x + r},${y} H${x + barW - r} Q${x + barW},${y} ${x + barW},${y + r} V${8 + plotH} Z`;
              const showLabel = i === 0 || i === data.length - 1 || i % Math.ceil(data.length / 6) === 0;
              return (
                <g
                  key={d.key}
                  tabIndex={0}
                  role="img"
                  aria-label={`${d.label}: ${format(d.value)}`}
                  onPointerEnter={() => setActive(i)}
                  onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive(null)}
                  className="outline-none"
                >
                  <rect x={padLeft + i * band} y={8} width={band} height={plotH} fill="transparent" />
                  {path ? (
                    <path d={path} fill="var(--series-1)" opacity={active === null || active === i ? 1 : 0.55} />
                  ) : null}
                  {showLabel ? (
                    <text x={x + barW / 2} y={height - 6} textAnchor="middle" fontSize={11} fill="var(--muted)">
                      {d.label}
                    </text>
                  ) : null}
                </g>
              );
            })}
            <line x1={padLeft} x2={width - 8} y1={8 + plotH} y2={8 + plotH} stroke="var(--line-strong)" />
          </svg>
          {active !== null && data[active] ? (
            <div
              role="tooltip"
              className="pointer-events-none absolute top-0 rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12px] shadow-lg"
              style={{ left: `${((padLeft + active * band + band / 2) / width) * 100}%`, transform: "translateX(-50%)" }}
            >
              <div className="font-semibold text-ink">{format(data[active].value)}</div>
              <div className="text-muted">
                {data[active].label}
                {data[active].detail ? ` · ${data[active].detail}` : ""}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </figure>
  );
}
