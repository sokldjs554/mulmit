"use client";

import { useId, useState } from "react";

import { cn } from "@/lib/utils";

export type BarDatum = { key: string; label: string; value: number; note?: string };

/**
 * Horizontal bars for one series (single hue, series-1): ≤ 16px thick, 4px rounded data end,
 * square at the baseline, value at the tip. Each bar row is its own hover/focus target with a
 * tooltip, and a "표로 보기" toggle exposes the same numbers without hovering.
 */
export function BarList({
  data,
  format,
  max,
  caption,
  className,
}: {
  data: BarDatum[];
  format: (v: number) => string;
  max?: number;
  caption: string;
  className?: string;
}) {
  const [asTable, setAsTable] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const id = useId();
  const top = max ?? Math.max(...data.map((d) => d.value), 0);

  return (
    <figure className={cn("space-y-2", className)} aria-labelledby={`${id}-cap`}>
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
                <td className="py-1.5 pl-3 text-right text-muted">{d.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <ul className="space-y-2.5">
          {data.map((d) => {
            const pct = top > 0 ? Math.max((d.value / top) * 100, d.value > 0 ? 1.5 : 0) : 0;
            const isActive = active === d.key;
            return (
              <li
                key={d.key}
                tabIndex={0}
                onPointerEnter={() => setActive(d.key)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(d.key)}
                onBlur={() => setActive(null)}
                className="relative rounded-md outline-none"
                aria-label={`${d.label} ${format(d.value)}${d.note ? `, ${d.note}` : ""}`}
              >
                <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
                  <span className="truncate text-ink-2">{d.label}</span>
                  <span className="tabular shrink-0 font-semibold text-ink">{format(d.value)}</span>
                </div>
                <div className="h-3 w-full rounded-r-[4px] bg-transparent">
                  <div
                    className="h-3 rounded-r-[4px] bg-series-1 transition-[filter]"
                    style={{ width: `${pct}%`, filter: isActive ? "brightness(1.12)" : undefined }}
                  />
                </div>
                {isActive && d.note ? (
                  <div
                    role="tooltip"
                    className="absolute top-0 right-0 z-10 -translate-y-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-[12px] shadow-lg"
                  >
                    <span className="font-semibold text-ink">{format(d.value)}</span>
                    <span className="ml-1.5 text-muted">{d.note}</span>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </figure>
  );
}
