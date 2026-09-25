"use client";

import Link from "next/link";

import { BarList } from "@/components/charts/bar-list";
import { StatTile } from "@/components/charts/budget-line";
import { Card, CardHeader, ErrorNote, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useAdminOverview } from "@/lib/api/hooks";
import { formatUSD } from "@/lib/format";

const sum = (o: Record<string, number>) => Object.values(o).reduce((a, b) => a + b, 0);

const JOB_STATUS: Record<string, string> = {
  succeeded: "성공",
  failed: "실패",
  running: "실행 중",
  retrying: "재시도 대기",
};

export default function AdminOverview() {
  const { data, error, isLoading } = useAdminOverview();
  if (isLoading) return <Skeleton className="h-96" />;
  if (!data) return <ErrorNote error={error} />;
  const f = data.funnel;
  const docs = sum(f.documents);
  const signals = sum(f.signals);
  const opps = sum(f.opportunities);
  const budgetUse = data.llm_daily_budget_usd ? data.llm_spent_today_usd / data.llm_daily_budget_usd : 0;
  const funnel = [
    { key: "docs", label: "수집 문서", value: docs, note: "회의록·예산서·조달 공고" },
    { key: "chunks", label: "청크 (발언 교환·예산 항목)", value: f.chunks },
    { key: "triaged", label: "추출 대상 청크 (트리아지 통과)", value: f.chunks_triaged, note: `${Math.round((1 - f.chunks_triaged / Math.max(f.chunks, 1)) * 100)}%는 LLM 호출 없이 건너뜀` },
    { key: "signals", label: "검증된 신호", value: signals },
    { key: "opps", label: "기회 (단계 연결 후)", value: opps },
  ];
  return (
    <div className="space-y-6">
      <PageHeader title="운영 개요" description="파이프라인이 잘 돌고 있는지, 막혔다면 어디서 막혔는지 여기서 한눈에 봐요." />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="검토 대기" value={`${f.review_open}건`} sub="근거·금액·기관을 확인 못 한 신호" />
        <StatTile label="실패한 작업 (24시간)" value={`${data.failed_jobs}건`} sub={`대기열 ${data.queue_depth ?? "–"}건`} />
        <StatTile
          label="오늘 LLM 비용"
          value={formatUSD(data.llm_spent_today_usd)}
          sub={`일 한도 ${formatUSD(data.llm_daily_budget_usd)}의 ${Math.round(budgetUse * 100)}%`}
        />
        <StatTile label="문제 있는 수집원" value={`${data.sources_unhealthy}곳`} sub="최근 실행이 실패한 곳" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="파이프라인 퍼널" description="전체 누적" />
          <div className="p-5">
            <BarList data={funnel} format={(v) => v.toLocaleString("ko-KR")} caption="단계별 건수" />
          </div>
        </Card>
        <Card>
          <CardHeader title="신호 판정" description="검증기(verifier) 결과" />
          <div className="p-5">
            <BarList
              data={[
                { key: "accepted", label: "채택 (근거 확인)", value: f.signals.accepted ?? 0 },
                { key: "needs_review", label: "검토 필요", value: f.signals.needs_review ?? 0 },
                { key: "rejected", label: "기각 (근거 없음)", value: f.signals.rejected ?? 0 },
              ]}
              format={(v) => v.toLocaleString("ko-KR")}
              caption="신호 수"
            />
            <p className="mt-4 text-[13px] text-muted">
              검토 대기열은{" "}
              <Link href="/admin/review" className="text-accent-text hover:underline">
                여기
              </Link>
              서 처리해요. 승인하면 사업 연결을 다시 돌려요.
            </p>
          </div>
        </Card>
        <Card>
          <CardHeader title="기회 상태" />
          <div className="p-5">
            <BarList
              data={[
                { key: "open", label: "공고 전 (진행 중)", value: f.opportunities.open ?? 0 },
                { key: "bid_open", label: "입찰 진행", value: f.opportunities.bid_open ?? 0 },
                { key: "closed", label: "종료", value: f.opportunities.closed ?? 0 },
                { key: "dormant", label: "휴면 (18개월째 소식 없음)", value: f.opportunities.dormant ?? 0 },
              ]}
              format={(v) => v.toLocaleString("ko-KR")}
              caption="기회 수"
            />
          </div>
        </Card>
        <Card>
          <CardHeader title="작업 (24시간)" />
          <div className="p-5">
            {Object.keys(data.jobs_last_24h).length ? (
              <BarList
                data={Object.entries(data.jobs_last_24h).map(([k, v]) => ({ key: k, label: JOB_STATUS[k] ?? k, value: v }))}
                format={(v) => v.toLocaleString("ko-KR")}
                caption="상태별 작업 수"
              />
            ) : (
              <p className="text-sm text-muted">최근 24시간 동안 워커가 돌린 작업이 없어요.</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
