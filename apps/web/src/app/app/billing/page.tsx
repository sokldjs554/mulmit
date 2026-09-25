"use client";

import { Check, CreditCard } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge, Card, CardHeader, ErrorNote, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError, newIdempotencyKey, type Schemas } from "@/lib/api/client";
import { useBilling, useBuyCredits, useChangePlan, useRegisterCard } from "@/lib/api/hooks";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Billing = Schemas["BillingOut"];

const REASON_LABEL: Record<string, string> = {
  plan_grant: "플랜 기본 제공",
  purchase: "크레딧 구매",
  brief: "Deep Brief 생성",
  refund: "환불",
  adjustment: "조정",
  expiry: "기간 만료 소멸",
};
const CHANNEL_LABEL: Record<string, string> = { email: "이메일", slack: "Slack", kakao: "카카오 알림톡" };
const STATUS_LABEL: Record<string, string> = {
  active: "이용 중",
  trialing: "체험 중",
  past_due: "결제 실패 — 재시도 예정",
  canceled: "해지됨",
};

declare global {
  interface Window {
    TossPayments?: (clientKey: string) => {
      payment: (opts: { customerKey: string }) => {
        requestBillingAuth: (opts: {
          method: "CARD";
          successUrl: string;
          failUrl: string;
          customerEmail?: string;
          customerName?: string;
        }) => Promise<void>;
      };
    };
  }
}

async function loadTossSdk(): Promise<NonNullable<Window["TossPayments"]>> {
  if (window.TossPayments) return window.TossPayments;
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://js.tosspayments.com/v2/standard";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("토스페이먼츠 SDK를 불러오지 못했습니다"));
    document.head.appendChild(script);
  });
  if (!window.TossPayments) throw new Error("토스페이먼츠 SDK를 불러오지 못했습니다");
  return window.TossPayments;
}

function CardSection({ billing }: { billing: Billing }) {
  const register = useRegisterCard();
  const toast = useToast();
  const sub = billing.subscription;

  const startRegistration = async () => {
    if (billing.payment_provider === "toss" && billing.toss_client_key) {
      // Real flow: Toss hosts the card form and redirects back with authKey.
      const TossPayments = await loadTossSdk();
      await TossPayments(billing.toss_client_key)
        .payment({ customerKey: billing.customer_key })
        .requestBillingAuth({
          method: "CARD",
          successUrl: `${window.location.origin}/app/billing/success`,
          failUrl: `${window.location.origin}/app/billing?fail=1`,
        });
      return;
    }
    // Local/demo: the fake provider issues a test billing key.
    register.mutate(
      { auth_key: newIdempotencyKey("demo"), customer_key: billing.customer_key },
      { onSuccess: () => toast("good", "테스트 카드를 등록했습니다") },
    );
  };

  return (
    <Card>
      <CardHeader
        title="결제 수단"
        description={
          billing.payment_provider === "toss"
            ? "토스페이먼츠 자동결제(빌링)로 매월 결제됩니다. 카드 정보는 저장하지 않고 암호화된 빌링키만 보관합니다."
            : "데모 환경입니다. 실제 결제 없이 테스트 결제사로 동작합니다."
        }
      />
      <div className="flex flex-wrap items-center justify-between gap-3 p-5">
        <div className="flex items-center gap-2 text-sm text-ink">
          <CreditCard className="size-4 text-muted" aria-hidden />
          {sub.card_summary ?? "등록된 카드가 없습니다"}
        </div>
        <Button variant="secondary" size="sm" loading={register.isPending} onClick={() => void startRegistration()}>
          {sub.card_summary ? "카드 변경" : "카드 등록"}
        </Button>
      </div>
      {register.error ? <div className="px-5 pb-5"><ErrorNote error={register.error} /></div> : null}
    </Card>
  );
}

function Plans({ billing }: { billing: Billing }) {
  const change = useChangePlan();
  const toast = useToast();
  const current = billing.subscription.plan;
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {billing.plans.map((plan) => {
        const isCurrent = plan.key === current;
        return (
          <Card key={plan.key} className={cn("flex flex-col p-5", isCurrent && "border-accent")}>
            <div className="flex items-center justify-between">
              <h3 className="text-[15px] font-semibold text-ink">{plan.name}</h3>
              {isCurrent ? <Badge tone="accent">현재 플랜</Badge> : null}
            </div>
            <p className="mt-2 text-[24px] font-bold tracking-tight text-ink">
              {plan.monthly_price_krw ? `₩${plan.monthly_price_krw.toLocaleString("ko-KR")}` : "무료"}
              {plan.monthly_price_krw ? <span className="text-sm font-normal text-muted"> / 월</span> : null}
            </p>
            <ul className="mt-4 flex-1 space-y-2 text-[13px] text-ink-2">
              <li className="flex gap-2"><Check className="mt-0.5 size-3.5 text-good" aria-hidden />매월 크레딧 {plan.monthly_credits}개</li>
              <li className="flex gap-2"><Check className="mt-0.5 size-3.5 text-good" aria-hidden />관심 지역 {plan.max_regions ?? "무제한"}{plan.max_regions ? "개" : ""}</li>
              <li className="flex gap-2"><Check className="mt-0.5 size-3.5 text-good" aria-hidden />{plan.channels.map((c) => CHANNEL_LABEL[c] ?? c).join(" · ")}</li>
              <li className="flex gap-2"><Check className="mt-0.5 size-3.5 text-good" aria-hidden />{plan.instant_alerts ? "즉시 알림" : "매일·매주 요약 알림"}</li>
            </ul>
            <Button
              className="mt-5"
              variant={isCurrent ? "secondary" : "primary"}
              disabled={isCurrent || change.isPending}
              loading={change.isPending && change.variables === plan.key}
              onClick={() =>
                change.mutate(plan.key as Schemas["PlanChangeIn"]["plan"], {
                  onSuccess: () =>
                    toast("good", plan.monthly_price_krw ? `${plan.name} 플랜으로 변경했습니다` : "현재 기간이 끝나면 Free로 전환됩니다"),
                  onError: (e) => toast("critical", e instanceof ApiError ? e.message : "플랜 변경에 실패했습니다"),
                })
              }
            >
              {isCurrent ? "이용 중" : plan.monthly_price_krw ? "이 플랜으로 변경" : "해지 예약"}
            </Button>
          </Card>
        );
      })}
    </div>
  );
}

function Credits({ billing }: { billing: Billing }) {
  const buy = useBuyCredits();
  const toast = useToast();
  return (
    <Card>
      <CardHeader
        title={`크레딧 ${billing.credit_balance}개`}
        description={`Deep Brief 1건에 ${billing.brief_cost}크레딧. 플랜 제공분은 매월 소멸하고, 구매한 크레딧은 소멸하지 않습니다.`}
        action={
          <div className="flex gap-2">
            {billing.credit_packs.map((p) => (
              <Button
                key={p.key}
                size="sm"
                variant="secondary"
                loading={buy.isPending && buy.variables === p.key}
                onClick={() =>
                  buy.mutate(p.key, {
                    onSuccess: () => toast("good", `크레딧 ${p.credits}개를 충전했습니다`),
                    onError: (e) => toast("critical", e instanceof ApiError ? e.message : "결제에 실패했습니다"),
                  })
                }
              >
                +{p.credits} · ₩{p.price_krw.toLocaleString("ko-KR")}
              </Button>
            ))}
          </div>
        }
      />
      <div className="overflow-x-auto p-5">
        <table className="w-full min-w-[480px] text-[13px]">
          <thead>
            <tr className="border-b border-line text-left text-muted">
              <th className="py-2 font-medium">일시</th>
              <th className="py-2 font-medium">내용</th>
              <th className="py-2 text-right font-medium">변동</th>
              <th className="py-2 text-right font-medium">잔액</th>
            </tr>
          </thead>
          <tbody>
            {billing.ledger.map((e) => (
              <tr key={e.id} className="border-b border-line last:border-0">
                <td className="tabular py-2 text-ink-2">{formatDateTime(e.created_at)}</td>
                <td className="py-2 text-ink">{REASON_LABEL[e.reason] ?? e.reason}</td>
                <td className={cn("tabular py-2 text-right font-medium", e.delta > 0 ? "text-good-text" : "text-ink")}>
                  {e.delta > 0 ? `+${e.delta}` : e.delta}
                </td>
                <td className="tabular py-2 text-right text-ink-2">{e.balance_after}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function BillingPage() {
  const billing = useBilling();
  if (billing.isLoading) return <Skeleton className="h-96" />;
  if (!billing.data) return <ErrorNote error={billing.error} />;
  const b = billing.data;
  const sub = b.subscription;
  return (
    <div className="space-y-6">
      <PageHeader
        title="요금·크레딧"
        description={
          <>
            {STATUS_LABEL[sub.status] ?? sub.status}
            {sub.next_charge_at ? ` · 다음 결제 ${formatDate(sub.next_charge_at)}` : ""}
            {sub.canceled_at && sub.current_period_end ? ` · ${formatDate(sub.current_period_end)}에 Free로 전환` : ""}
          </>
        }
      />
      {sub.status === "past_due" ? (
        <div role="alert" className="rounded-lg border border-serious/40 bg-serious/10 px-4 py-3 text-sm text-ink">
          최근 정기결제가 실패했습니다({sub.failed_attempts}회). 1·3·7일 뒤 다시 시도하며, 모두 실패하면 Free 플랜으로 전환됩니다.
        </div>
      ) : null}
      <CardSection billing={b} />
      <Plans billing={b} />
      <Credits billing={b} />
      <Card>
        <CardHeader title="결제 내역" />
        <div className="overflow-x-auto p-5">
          <table className="w-full min-w-[520px] text-[13px]">
            <tbody>
              {b.payments.map((p) => (
                <tr key={p.id} className="border-b border-line last:border-0">
                  <td className="tabular py-2 text-ink-2">{formatDateTime(p.paid_at ?? p.created_at)}</td>
                  <td className="py-2 text-ink">{p.order_name}</td>
                  <td className="tabular py-2 text-right text-ink">₩{p.amount.toLocaleString("ko-KR")}</td>
                  <td className="py-2 text-right">
                    <Badge tone={p.status === "paid" ? "good" : p.status === "failed" ? "critical" : "neutral"}>
                      {p.status === "paid" ? "결제 완료" : p.status === "failed" ? (p.failure_message ?? "실패") : p.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
