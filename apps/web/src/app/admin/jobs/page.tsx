"use client";

import { RotateCcw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/controls";
import { Badge, Card, EmptyState, ErrorNote, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { useAdminJobs, useRetryJob } from "@/lib/api/hooks";
import { formatDateTime } from "@/lib/format";

type Filter = "all" | "failed" | "retrying";
const TONE: Record<string, "good" | "critical" | "warning" | "neutral"> = {
  succeeded: "good",
  failed: "critical",
  retrying: "warning",
  running: "neutral",
};

export default function JobsPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const jobs = useAdminJobs(filter === "all" ? undefined : filter);
  const retry = useRetryJob();
  const toast = useToast();
  return (
    <div className="space-y-6">
      <PageHeader
        title="작업 로그"
        description="arq 작업마다 시작, 끝, 오류를 남겨요. 일시적인 오류는 간격을 늘려 가며 알아서 다시 시도하고, 끝내 실패한 것만 여기서 직접 다시 돌려요."
        action={
          <Segmented<Filter>
            ariaLabel="상태 필터"
            value={filter}
            onChange={setFilter}
            options={[
              { key: "all", label: "전체" },
              { key: "failed", label: "실패" },
              { key: "retrying", label: "재시도 중" },
            ]}
          />
        }
      />
      {jobs.error ? <ErrorNote error={jobs.error} /> : null}
      <Card className="overflow-x-auto">
        {jobs.isLoading ? (
          <Skeleton className="m-5 h-48" />
        ) : jobs.data?.length === 0 ? (
          <EmptyState title="기록된 작업이 없어요" />
        ) : (
          <table className="w-full min-w-[820px] text-[13px]">
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th className="px-5 py-3 font-medium">작업</th>
                <th className="py-3 font-medium">상태</th>
                <th className="py-3 font-medium">시작</th>
                <th className="py-3 text-right font-medium">소요</th>
                <th className="py-3 pl-6 font-medium">결과 / 오류</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {jobs.data?.map((j) => (
                <tr key={j.id} className="border-b border-line align-top last:border-0">
                  <td className="px-5 py-2.5">
                    <div className="font-medium text-ink">{j.job}</div>
                    <div className="max-w-[220px] truncate text-[12px] text-muted">{j.job_id}</div>
                  </td>
                  <td className="py-2.5">
                    <Badge tone={TONE[j.status] ?? "neutral"}>{j.status}</Badge>
                    {j.attempt > 1 ? <span className="ml-1 text-[12px] text-muted">#{j.attempt}</span> : null}
                  </td>
                  <td className="tabular py-2.5 text-ink-2">{formatDateTime(j.started_at)}</td>
                  <td className="tabular py-2.5 text-right text-ink-2">{j.duration_ms !== null ? `${(j.duration_ms / 1000).toFixed(1)}초` : "–"}</td>
                  <td className="max-w-md py-2.5 pl-6">
                    {j.error ? (
                      <span className="text-critical">{j.error}</span>
                    ) : (
                      <span className="text-ink-2">
                        {Object.entries(j.result)
                          .map(([k, v]) => `${k} ${String(v)}`)
                          .join(" · ")}
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-2.5 text-right">
                    {j.status === "failed" ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={retry.isPending && retry.variables === j.id}
                        onClick={() => retry.mutate(j.id, { onSuccess: () => toast("good", "다시 돌리도록 예약했어요") })}
                      >
                        <RotateCcw className="size-3.5" aria-hidden /> 재실행
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
