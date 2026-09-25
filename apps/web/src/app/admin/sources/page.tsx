"use client";

import { Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge, Card, ErrorNote, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { useAdminSources, useRunSource, useToggleSource } from "@/lib/api/hooks";
import { formatDateTime } from "@/lib/format";

export default function SourcesPage() {
  const sources = useAdminSources();
  const run = useRunSource();
  const toggle = useToggleSource();
  const toast = useToast();
  return (
    <div className="space-y-6">
      <PageHeader
        title="수집원"
        description="공공 API는 하루 호출 한도(CLIK·data.go.kr 1,000회)가 있고, 오류를 HTTP 200으로 돌려주는 일도 잦아요. 한도를 넘기면 자정(한국 시간) 뒤로 다시 예약하고, 계속 실패하면 서킷을 열어 잠시 쉬어요."
      />
      {sources.error ? <ErrorNote error={sources.error} /> : null}
      <Card className="overflow-x-auto">
        {sources.isLoading ? (
          <Skeleton className="m-5 h-48" />
        ) : (
          <table className="w-full min-w-[860px] text-[13px]">
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th className="px-5 py-3 font-medium">수집원</th>
                <th className="py-3 font-medium">문서</th>
                <th className="py-3 font-medium">최근 실행</th>
                <th className="py-3 font-medium">서킷</th>
                <th className="py-3 font-medium">사용</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {sources.data?.map((s) => (
                <tr key={s.key} className="border-b border-line last:border-0">
                  <td className="px-5 py-3">
                    <div className="font-medium text-ink">{s.name}</div>
                    <div className="text-[12px] text-muted">
                      {s.key} · {s.adapter}
                    </div>
                  </td>
                  <td className="tabular py-3 text-ink">{s.documents.toLocaleString("ko-KR")}</td>
                  <td className="py-3">
                    {s.last_run ? (
                      <div>
                        <Badge tone={s.last_run.status === "succeeded" ? "good" : s.last_run.status === "failed" ? "critical" : "warning"}>
                          {String(s.last_run.status)}
                        </Badge>
                        <div className="mt-0.5 text-[12px] text-muted">
                          {formatDateTime(String(s.last_run.started_at))} · 신규 {String(s.last_run.created)} · 갱신 {String(s.last_run.updated)}
                        </div>
                        {s.last_run.error ? <div className="mt-0.5 max-w-xs truncate text-[12px] text-critical">{String(s.last_run.error)}</div> : null}
                      </div>
                    ) : (
                      <span className="text-muted">실행 기록 없음</span>
                    )}
                  </td>
                  <td className="py-3">
                    <Badge tone={s.circuit.state === "open" ? "critical" : s.circuit.state === "closed" ? "good" : "neutral"}>
                      {s.circuit.state === "open" ? "열림" : s.circuit.state === "closed" ? "정상" : "–"}
                    </Badge>
                    {s.consecutive_failures ? <span className="ml-1 text-[12px] text-critical">연속 실패 {s.consecutive_failures}</span> : null}
                  </td>
                  <td className="py-3">
                    <label className="inline-flex cursor-pointer items-center gap-2">
                      <input
                        type="checkbox"
                        className="size-4 accent-[var(--accent)]"
                        checked={s.enabled}
                        onChange={(e) => toggle.mutate({ key: s.key, enabled: e.target.checked })}
                      />
                      <span className="text-ink-2">{s.enabled ? "켜짐" : "꺼짐"}</span>
                    </label>
                  </td>
                  <td className="px-5 py-3 text-right">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={!s.enabled}
                      loading={run.isPending && run.variables === s.key}
                      onClick={() => run.mutate(s.key, { onSuccess: () => toast("good", `${s.key} 수집을 예약했어요`) })}
                    >
                      <Play className="size-3.5" aria-hidden /> 지금 수집
                    </Button>
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
