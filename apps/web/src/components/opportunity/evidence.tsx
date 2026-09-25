"use client";

import { useState } from "react";

import type { Schemas } from "@/lib/api/client";

type Evidence = Schemas["EvidenceOut"];

type Segment = { text: string; marked: boolean };

/** Split `context` into plain/highlighted segments from document-level evidence offsets. */
export function highlightSegments(context: string, contextOffset: number, evidence: Evidence[]): Segment[] {
  const spans = evidence
    .filter((e) => e.found && e.start !== null && e.end !== null)
    .map((e) => [Math.max(0, (e.start as number) - contextOffset), Math.min(context.length, (e.end as number) - contextOffset)] as const)
    .filter(([s, e]) => e > s)
    .sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const [s, e] of spans) {
    const lastSpan = merged[merged.length - 1];
    if (lastSpan && s <= lastSpan[1]) lastSpan[1] = Math.max(lastSpan[1], e);
    else merged.push([s, e]);
  }
  const out: Segment[] = [];
  let pos = 0;
  for (const [s, e] of merged) {
    if (s > pos) out.push({ text: context.slice(pos, s), marked: false });
    out.push({ text: context.slice(s, e), marked: true });
    pos = e;
  }
  if (pos < context.length) out.push({ text: context.slice(pos), marked: false });
  return out;
}

export function EvidenceContext({
  context,
  contextOffset,
  evidence,
  maxChars = 700,
}: {
  context: string | null;
  contextOffset: number | null;
  evidence: Evidence[];
  maxChars?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!context || contextOffset === null) {
    const quote = evidence.find((e) => e.found)?.quote;
    return quote ? <blockquote className="text-[13px] text-ink-2">「{quote}」</blockquote> : null;
  }
  const segments = highlightSegments(context, contextOffset, evidence);
  const long = context.length > maxChars;
  let budget = expanded || !long ? Number.POSITIVE_INFINITY : maxChars;
  const visible: Segment[] = [];
  for (const seg of segments) {
    if (budget <= 0) break;
    const text = seg.text.length > budget && !seg.marked ? `${seg.text.slice(0, budget)}…` : seg.text;
    visible.push({ ...seg, text });
    budget -= seg.text.length;
  }
  return (
    <div className="rounded-lg border border-line bg-surface-2/60 px-3.5 py-3">
      <p className="text-[13px] leading-6 whitespace-pre-line text-ink-2">
        {visible.map((seg, i) =>
          seg.marked ? (
            <mark key={i} className="text-ink">
              {seg.text}
            </mark>
          ) : (
            <span key={i}>{seg.text}</span>
          ),
        )}
      </p>
      {long ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 text-[12px] text-accent-text hover:underline"
        >
          {expanded ? "접기" : "원문 더 보기"}
        </button>
      ) : null}
    </div>
  );
}
