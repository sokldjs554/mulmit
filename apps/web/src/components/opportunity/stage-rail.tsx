import { STAGES, cn, stageIndex } from "@/lib/utils";

/**
 * The procurement lifecycle as an ordinal progress rail: reached stages are filled with the
 * ordinal blue ramp (lighter = earlier), the current stage is labelled. Colour is never the
 * only cue — the current stage is named and reached stages carry a filled dot.
 */
export function StageRail({
  stage,
  reached,
  compact = false,
}: {
  stage: string;
  reached?: string[];
  compact?: boolean;
}) {
  const current = stageIndex(stage);
  const reachedSet = new Set(reached ?? STAGES.slice(0, current + 1).map((s) => s.key));
  return (
    <div className="w-full" aria-label={`현재 단계: ${STAGES[current]?.label ?? stage}`}>
      <ol className="flex items-center gap-[2px]">
        {STAGES.slice(0, 5).map((s, i) => {
          const on = reachedSet.has(s.key) || i <= current;
          return (
            <li
              key={s.key}
              className={cn("h-1.5 flex-1 first:rounded-l-full last:rounded-r-full", on ? "" : "bg-surface-2")}
              style={on ? { background: `var(--stage-${i + 1})` } : undefined}
              title={s.label}
            />
          );
        })}
      </ol>
      {!compact ? (
        <ol className="mt-1.5 grid grid-cols-5 text-[11px]">
          {STAGES.slice(0, 5).map((s, i) => (
            <li
              key={s.key}
              className={cn(
                "truncate",
                i === current ? "font-semibold text-ink" : reachedSet.has(s.key) ? "text-ink-2" : "text-muted",
              )}
            >
              {s.short}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
