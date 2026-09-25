"use client";

import { ArrowLeft, Building2, EyeOff, FileSearch, ThumbsDown, ThumbsUp, Trophy } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import ReactMarkdown from "react-markdown";

import { BarList } from "@/components/charts/bar-list";
import { BudgetLine, StatTile } from "@/components/charts/budget-line";
import { SignalTimeline } from "@/components/opportunity/signal-timeline";
import { StageRail } from "@/components/opportunity/stage-rail";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardHeader, ErrorNote, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError, type Schemas } from "@/lib/api/client";
import { useCreateBrief, useFeedback, useMe, useOpportunity } from "@/lib/api/hooks";
import { formatDateTime, formatKRW, formatPercent, formatWindow, leadLabel } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/utils";

const FEATURE_LABEL: Record<string, string> = {
  semantic: "회사 소개와의 의미 유사도",
  keyword: "관심 키워드 일치",
  category: "관심 분야",
  region: "관심 지역",
  budget: "선호 예산 범위",
  conversion: "공고 전환 가능성",
  lead_time: "영업 가능한 선행 기간",
};

function Why({ breakdown }: { breakdown: Record<string, unknown> | null | undefined }) {
  const features = (breakdown?.features ?? {}) as Record<string, number>;
  const weights = (breakdown?.weights ?? {}) as Record<string, number>;
  const data = Object.keys(FEATURE_LABEL)
    .filter((k) => k in features)
    .map((k) => ({
      key: k,
      label: FEATURE_LABEL[k] ?? k,
      value: (features[k] ?? 0) * (weights[k] ?? 0) * 100,
      note: `신호 ${Math.round((features[k] ?? 0) * 100)}점 × 가중치 ${Math.round((weights[k] ?? 0) * 100)}%`,
    }))
    .sort((a, b) => b.value - a.value);
  if (!data.length) return <p className="text-sm text-muted">이 기회는 아직 우리 회사 기준으로 채점되지 않았습니다.</p>;
  return (
    <BarList
      data={data}
      format={(v) => `${v.toFixed(1)}점`}
      caption="적합도 점수에 대한 기여 (점)"
      max={Math.max(...Object.values(weights).map((w) => w * 100))}
    />
  );
}

function Briefs({ detail }: { detail: Schemas["OpportunityDetail"] }) {
  const me = useMe();
  const toast = useToast();
  const create = useCreateBrief(detail.id);
  const balance = me.data?.org.credit_balance ?? 0;
  const latest = detail.briefs[0];
  return (
    <Card>
      <CardHeader
        title="Deep Brief"
        description="신호·원문 인용·기관 발주 이력으로 쓴 1쪽 영업 브리핑 (3 크레딧)"
        action={
          <Button
            size="sm"
            loading={create.isPending}
            disabled={balance < 3}
            onClick={() =>
              create.mutate(undefined, {
                onSuccess: () => toast("good", "브리프를 생성했습니다 (3 크레딧 사용)"),
                onError: (e) =>
                  toast("critical", e instanceof ApiError && e.status === 402 ? e.message : "브리프 생성에 실패했습니다"),
              })
            }
          >
            <FileSearch className="size-4" aria-hidden />
            {latest ? "다시 생성" : "생성하기"}
          </Button>
        }
      />
      <div className="px-5 pt-3 pb-5">
        {balance < 3 ? (
          <p className="mb-3 text-[13px] text-muted">
            크레딧이 부족합니다.{" "}
            <Link href="/app/billing" className="text-accent-text hover:underline">
              충전하기
            </Link>
          </p>
        ) : null}
        {latest ? (
          <article className="prose-brief">
            <ReactMarkdown>{latest.content_md}</ReactMarkdown>
            <p className="mt-4 text-[11px] text-muted">
              {formatDateTime(latest.created_at)} · {latest.model}
            </p>
          </article>
        ) : (
          <p className="text-[13px] text-muted">아직 생성된 브리프가 없습니다.</p>
        )}
      </div>
    </Card>
  );
}

function FeedbackBar({ id, current }: { id: number; current: string | null }) {
  const feedback = useFeedback(id);
  const options = [
    { key: "relevant", label: "관련 있음", icon: ThumbsUp },
    { key: "irrelevant", label: "관련 없음", icon: ThumbsDown },
    { key: "won", label: "수주함", icon: Trophy },
    { key: "dismissed", label: "숨기기", icon: EyeOff },
  ] as const;
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="추천 피드백">
      {options.map(({ key, label, icon: Icon }) => (
        <Button
          key={key}
          size="sm"
          variant={current === key ? "primary" : "secondary"}
          aria-pressed={current === key}
          onClick={() => feedback.mutate(current === key ? null : key)}
        >
          <Icon className="size-3.5" aria-hidden />
          {label}
        </Button>
      ))}
    </div>
  );
}

export default function OpportunityPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { data, error, isLoading } = useOpportunity(id);

  if (isLoading) return <Skeleton className="h-96 w-full" />;
  if (error || !data) return <ErrorNote error={error ?? new Error("기회를 찾을 수 없습니다")} />;

  const lead = leadLabel(data.lead_days);
  const reached = data.signals.map((s) => s.stage);
  return (
    <div className="space-y-6">
      <Link href="/app" className="inline-flex items-center gap-1 text-[13px] text-ink-2 hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> 기회 피드
      </Link>

      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="accent">{data.stage_label}</Badge>
          <Badge>{data.category_label}</Badge>
          <Badge tone={data.status === "bid_open" ? "warning" : "outline"}>{STATUS_LABEL[data.status] ?? data.status}</Badge>
          {lead ? <Badge tone="outline">입찰 {lead}</Badge> : null}
        </div>
        <h1 className="text-[24px] leading-tight font-bold tracking-tight text-ink">{data.title}</h1>
        <p className="inline-flex items-center gap-1.5 text-sm text-ink-2">
          <Building2 className="size-4 text-muted" aria-hidden />
          {data.institution.name}
          {data.department ? <span className="text-muted">· {data.department}</span> : null}
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="추정 예산" value={formatKRW(data.est_budget_krw)} sub="가장 최근 단계 기준" />
        <StatTile label="입찰 예상 시기" value={formatWindow(data.bid_window_start, data.bid_window_end)} sub={lead ? `입찰 ${lead}` : undefined} />
        <StatTile label="공고 전환 확률" value={formatPercent(data.conversion_prob)} sub="백테스트로 보정" />
        <StatTile label="우리 회사 적합도" value={data.score !== null ? `${Math.round(data.score * 100)}점` : "–"} sub={`신호 ${data.signal_count}건`} />
      </div>

      <Card className="px-5 py-4">
        <StageRail stage={data.stage} reached={reached} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader
            title="신호 타임라인"
            description="문서마다 근거 문장을 원문 위치 그대로 강조했습니다. 근거를 찾지 못한 추출은 보여주지 않습니다."
          />
          <div className="px-5 pt-5 pb-6">
            <SignalTimeline signals={data.signals} />
          </div>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader title="왜 추천되었나" />
            <div className="px-5 pt-3 pb-5">
              <Why breakdown={data.breakdown} />
            </div>
          </Card>
          {data.budget_trajectory.length >= 2 ? (
            <Card>
              <CardHeader title="금액 추이" />
              <div className="px-5 pt-3 pb-5">
                <BudgetLine points={data.budget_trajectory} />
              </div>
            </Card>
          ) : null}
          <Briefs detail={data} />
          <Card className="p-5">
            <p className="mb-3 text-[13px] font-medium text-ink">이 추천이 도움이 되었나요?</p>
            <FeedbackBar id={data.id} current={data.feedback} />
            <p className="mt-2 text-[12px] text-muted">피드백은 랭킹 모델 학습 데이터로 쓰입니다.</p>
          </Card>
        </div>
      </div>
    </div>
  );
}
