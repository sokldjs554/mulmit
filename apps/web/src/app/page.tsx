import { ArrowRight, FileCheck2, GitMerge, Timer } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/layout/shell";
import { buttonVariants } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/controls";
import { cn } from "@/lib/utils";

const JOURNEY = [
  {
    date: "2025.11",
    stage: "의회 발언",
    source: "강남구의회 행정재무위원회 회의록",
    quote: "내년도 본예산에 스마트쉘터 7개소 추가 설치 사업비 3억 5천만원을 반영하겠습니다.",
    us: true,
  },
  { date: "2025.12", stage: "예산 편성", source: "2026년도 세출예산 사업명세서", quote: "세부사업: 스마트쉘터 설치  352,000 (천원)" },
  { date: "2026.03", stage: "발주계획", source: "나라장터 발주계획", quote: "2026년 스마트쉘터 제작·설치 — 발주시기 2026년 6월" },
  { date: "2026.05", stage: "사전규격", source: "나라장터 사전규격 공개", quote: "스마트 버스정류장 조성사업 — 의견등록 마감 5/20" },
  { date: "2026.06", stage: "입찰공고", source: "나라장터 입찰공고", quote: "[긴급] 스마트쉘터 구축사업 (협상에 의한 계약)", them: true },
];

const FEATURES = [
  {
    icon: FileCheck2,
    title: "원문에서 확인된 신호만",
    body: "LLM이 뽑은 모든 금액·연도·근거 문장을 파서가 원문과 대조합니다. 원문에 없는 문장은 버리고, 금액이 다르면 사람이 검토합니다.",
  },
  {
    icon: GitMerge,
    title: "흩어진 문서를 한 사업으로",
    body: "의회에서는 '스쿨존 카메라', 예산서에서는 '어린이보호구역 지능형 CCTV', 공고에서는 '스쿨존 AI 안전카메라'. 공고 번호와 조달 용어 사전으로 한 기회로 묶습니다.",
  },
  {
    icon: Timer,
    title: "지금 움직일 수 있는 순서로",
    body: "적합도만이 아니라 '공고 전환 가능성'과 '영업 가능한 선행 기간'까지 점수에 넣습니다. 전환율은 과거 데이터 백테스트로 보정합니다.",
  },
];

export default function Home() {
  return (
    <div className="min-h-dvh">
      <header className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <Logo />
        <nav className="flex items-center gap-1">
          <a href="#how" className="hidden px-3 text-sm text-ink-2 hover:text-ink sm:inline">
            작동 방식
          </a>
          <ThemeToggle />
          <Link href="/login" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>
            로그인
          </Link>
          <Link href="/signup" className={cn(buttonVariants({ size: "sm" }))}>
            무료로 시작
          </Link>
        </nav>
      </header>

      <section className="mx-auto max-w-6xl px-4 pt-12 pb-16 md:pt-20">
        <p className="text-sm font-semibold text-accent-text">공공조달 발주 예측 서비스</p>
        <h1 className="mt-3 max-w-3xl text-[34px] leading-[1.15] font-bold tracking-tight text-ink md:text-[52px]">
          입찰공고 전에
          <br />
          공공사업을 미리 확인하세요.
        </h1>
        <p className="mt-5 max-w-2xl text-[17px] leading-relaxed text-ink-2">
          공공사업은 공고 6~18개월 전에 지방의회 회의록과 예산서에서 먼저 모습을 드러냅니다. 발주 예측은 그 문서들을 매일 읽고, 우리 회사가 영업을
          시작해야 할 사업을 근거 문장과 함께 알려드립니다.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/login" className={cn(buttonVariants({ size: "lg" }))}>
            데모로 둘러보기 <ArrowRight className="size-4" aria-hidden />
          </Link>
          <Link href="/signup" className={cn(buttonVariants({ variant: "secondary", size: "lg" }))}>
            무료로 시작하기
          </Link>
        </div>
      </section>

      <section id="how" className="border-y border-line bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-14">
          <h2 className="text-xl font-bold text-ink">한 사업이 공고가 되기까지</h2>
          <p className="mt-1 text-sm text-muted">예시는 데모용 합성 데이터입니다.</p>
          <ol className="mt-8 grid gap-4 md:grid-cols-5">
            {JOURNEY.map((step, i) => (
              <li
                key={step.stage}
                className={cn(
                  "relative rounded-xl border bg-bg p-4",
                  step.us ? "border-accent" : step.them ? "border-line-strong" : "border-line",
                )}
              >
                <div className="h-1.5 w-full rounded-full" style={{ background: `var(--stage-${i + 1})` }} aria-hidden />
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-[13px] font-semibold text-ink">{step.stage}</span>
                  <span className="tabular text-[12px] text-muted">{step.date}</span>
                </div>
                <p className="mt-1 text-[12px] text-muted">{step.source}</p>
                <p className="mt-3 text-[13px] leading-relaxed text-ink-2">「{step.quote}」</p>
                {step.us ? (
                  <p className="mt-3 text-[12px] font-semibold text-accent-text">▲ 발주 예측이 알려주는 시점</p>
                ) : null}
                {step.them ? <p className="mt-3 text-[12px] font-semibold text-muted">▲ 일반 입찰 알림이 알려주는 시점</p> : null}
              </li>
            ))}
          </ol>
          <p className="mt-6 text-sm text-ink-2">
            그 사이 7개월 동안 담당 부서를 만나고, 사업 계획에 우리 제품의 사양이 반영되도록 제안할 수 있습니다.
          </p>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-6 px-4 py-14 md:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <div key={title}>
            <Icon className="size-5 text-accent-text" aria-hidden />
            <h3 className="mt-3 text-[16px] font-semibold text-ink">{title}</h3>
            <p className="mt-2 text-[14px] leading-relaxed text-ink-2">{body}</p>
          </div>
        ))}
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-6 text-[12px] text-muted">
          <span>발주 예측 · 포트폴리오 프로젝트 — 데모 데이터는 모두 합성된 것입니다.</span>
          <span>국회도서관 지방의정포털 · 조달청 나라장터 · 행정안전부 지방재정365 Open API 기반 설계</span>
        </div>
      </footer>
    </div>
  );
}
