"use client";

import { useMemo, useState } from "react";

import { BarList } from "@/components/charts/bar-list";
import { StatTile } from "@/components/charts/budget-line";
import { ColumnChart } from "@/components/charts/column-chart";
import { Segmented } from "@/components/ui/controls";
import { Card, CardHeader, ErrorNote, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useLlmUsage } from "@/lib/api/hooks";
import { formatPercent, formatUSD } from "@/lib/format";

type Days = "7" | "14" | "30";

export default function LlmPage() {
  const [days, setDays] = useState<Days>("14");
  const usage = useLlmUsage(Number(days));
  const data = usage.data;

  const perDay = useMemo(() => {
    const map = new Map<string, { cost: number; calls: number }>();
    const end = new Date();
    for (let i = Number(days) - 1; i >= 0; i--) {
      const d = new Date(end.getTime() - i * 86_400_000).toISOString().slice(0, 10);
      map.set(d, { cost: 0, calls: 0 });
    }
    for (const r of data?.rows ?? []) {
      const cur = map.get(r.day) ?? { cost: 0, calls: 0 };
      map.set(r.day, { cost: cur.cost + r.cost_usd, calls: cur.calls + r.calls });
    }
    return [...map.entries()].map(([day, v]) => ({
      key: day,
      label: `${Number(day.slice(5, 7))}/${Number(day.slice(8, 10))}`,
      value: v.cost,
      detail: `호출 ${v.calls.toLocaleString("ko-KR")}회`,
    }));
  }, [data, days]);

  const byTaskModel = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of data?.rows ?? []) map.set(`${r.task} · ${r.model}`, (map.get(`${r.task} · ${r.model}`) ?? 0) + r.cost_usd);
    return [...map.entries()].map(([k, v]) => ({ key: k, label: k, value: v })).sort((a, b) => b.value - a.value);
  }, [data]);

  const byStatus = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of data?.rows ?? []) map.set(r.status, (map.get(r.status) ?? 0) + r.calls);
    return [...map.entries()].map(([k, v]) => ({ key: k, label: k, value: v })).sort((a, b) => b.value - a.value);
  }, [data]);

  const total = perDay.reduce((a, d) => a + d.value, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="LLM 비용·품질"
        description="추출에는 가장 좋은 모델을 낮은 effort로 쓰고, 트리아지·프롬프트 캐싱·해시 캐시·하루 한도로 비용을 묶어 둬요."
        action={
          <Segmented<Days>
            ariaLabel="기간"
            value={days}
            onChange={setDays}
            options={[
              { key: "7", label: "7일" },
              { key: "14", label: "14일" },
              { key: "30", label: "30일" },
            ]}
          />
        }
      />
      {usage.error ? <ErrorNote error={usage.error} /> : null}
      {!data ? (
        <Skeleton className="h-96" />
      ) : (
        <div className={usage.isPlaceholderData ? "space-y-6 opacity-60" : "space-y-6"}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="오늘 사용액" value={formatUSD(data.spent_today_usd)} sub={`일 한도 ${formatUSD(data.daily_budget_usd)}`} />
            <StatTile label={`${days}일 합계`} value={formatUSD(total)} />
            <StatTile label="캐시 적중률" value={formatPercent(data.cache_hit_rate)} sub="같은 청크를 다시 처리할 때" />
            <StatTile
              label="폴백(규칙 기반) 비율"
              value={formatPercent(data.degraded_rate)}
              sub={data.extractor_mode === "heuristic" ? "LLM 키가 없어 규칙 기반으로 도는 중" : "장애·한도 초과·거절 때"}
            />
          </div>
          {data.extractor_mode === "heuristic" ? (
            <p className="rounded-lg border border-line bg-surface px-4 py-3 text-[13px] text-ink-2">
              이 환경에는 <code className="rounded bg-surface-2 px-1">APP_LLM_PROVIDER=anthropic</code>이 없어서 규칙 기반 추출기로 돌고
              있어요. 키를 넣으면 이 화면에 모델·작업별 비용과 캐시 효과가 쌓여요. 실제 Claude로 잰 정확도와 비용은{" "}
              <a
                href="https://github.com/sokldjs554/procurement-forecast/blob/main/docs/evaluation-llm.md"
                className="text-accent-text hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                모델 비교 결과
              </a>
              에서 볼 수 있어요.
            </p>
          ) : null}
          <Card>
            <CardHeader title="일별 비용 (USD)" />
            <div className="p-5">
              <ColumnChart data={perDay} format={(v) => formatUSD(v)} caption="일별 LLM 비용" />
            </div>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="작업·모델별 비용" />
              <div className="p-5">
                {byTaskModel.length ? (
                  <BarList data={byTaskModel} format={formatUSD} caption="기간 합계" />
                ) : (
                  <p className="text-sm text-muted">이 기간에는 유료 호출이 없어요.</p>
                )}
              </div>
            </Card>
            <Card>
              <CardHeader title="호출 결과" description="ok · cache_hit · budget_skip · refusal · error" />
              <div className="p-5">
                {byStatus.length ? (
                  <BarList data={byStatus} format={(v) => `${v.toLocaleString("ko-KR")}회`} caption="호출 수" />
                ) : (
                  <p className="text-sm text-muted">기록된 호출이 없어요.</p>
                )}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
