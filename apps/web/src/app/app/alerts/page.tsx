"use client";

import { Hash, Mail, MessageCircle, Send, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { ChipGroup, Segmented } from "@/components/ui/controls";
import { Badge, Card, CardHeader, EmptyState, ErrorNote, Field, Input, PageHeader, Select, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import type { Schemas } from "@/lib/api/client";
import {
  useAddChannel,
  useAlertRule,
  useChannels,
  useDeleteChannel,
  useMe,
  useNotifications,
  useSaveAlertRule,
  useTestChannel,
} from "@/lib/api/hooks";
import { formatDateTime } from "@/lib/format";
import { STAGES } from "@/lib/utils";

type Mode = Schemas["AlertRuleIO"]["mode"];
type Kind = Schemas["AlertChannelIn"]["kind"];

const KIND = {
  email: { label: "이메일", icon: Mail, placeholder: "sales@company.kr" },
  slack: { label: "Slack", icon: Hash, placeholder: "https://hooks.slack.com/services/…" },
  kakao: { label: "카카오 알림톡", icon: MessageCircle, placeholder: "010-1234-5678" },
} as const;

const PLAN_CHANNELS: Record<string, Kind[]> = {
  free: ["email"],
  pro: ["email", "slack"],
  team: ["email", "slack", "kakao"],
};

function RuleCard({ rule, plan }: { rule: Schemas["AlertRuleIO"]; plan: string }) {
  const save = useSaveAlertRule();
  const toast = useToast();
  const [form, setForm] = useState(rule);
  const hours = Array.from({ length: 24 }, (_, h) => h);
  return (
    <Card>
      <CardHeader title="언제 알려드릴까요?" description="새 기회가 생기거나, 기존 기회가 다음 단계(예: 의회 발언 → 예산 편성)로 넘어가면 알려드립니다." />
      <div className="space-y-5 p-5">
        <Field label="방식" htmlFor="mode" hint={plan === "free" ? "즉시 알림은 Pro 플랜부터 사용할 수 있습니다." : undefined}>
          <Segmented<Mode>
            ariaLabel="알림 방식"
            value={form.mode ?? "daily"}
            onChange={(mode) => setForm({ ...form, mode })}
            options={[
              { key: "instant", label: "즉시", disabled: plan === "free" },
              { key: "daily", label: "매일 아침 8시" },
              { key: "weekly", label: "매주 월요일" },
            ]}
          />
        </Field>
        <Field label={`최소 적합도: ${Math.round((form.min_score ?? 0.55) * 100)}점`} htmlFor="score">
          <input
            id="score"
            type="range"
            min={0.3}
            max={0.9}
            step={0.05}
            value={form.min_score ?? 0.55}
            onChange={(e) => setForm({ ...form, min_score: Number(e.target.value) })}
            className="w-full accent-[var(--accent)]"
          />
        </Field>
        <Field label="알릴 단계" htmlFor="stages" hint="선택하지 않으면 모든 단계를 알립니다.">
          <ChipGroup
            ariaLabel="알릴 단계"
            options={STAGES.slice(0, 5).map((s) => ({ key: s.key, label: s.label }))}
            value={form.stages ?? []}
            onChange={(stages) => setForm({ ...form, stages })}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="방해 금지 시작 (KST)" htmlFor="qs">
            <Select id="qs" value={form.quiet_start ?? 22} onChange={(e) => setForm({ ...form, quiet_start: Number(e.target.value) })}>
              {hours.map((h) => (
                <option key={h} value={h}>{`${h}시`}</option>
              ))}
            </Select>
          </Field>
          <Field label="방해 금지 끝 (KST)" htmlFor="qe">
            <Select id="qe" value={form.quiet_end ?? 8} onChange={(e) => setForm({ ...form, quiet_end: Number(e.target.value) })}>
              {hours.map((h) => (
                <option key={h} value={h}>{`${h}시`}</option>
              ))}
            </Select>
          </Field>
        </div>
        {save.error ? <ErrorNote error={save.error} /> : null}
        <div className="flex justify-end">
          <Button loading={save.isPending} onClick={() => save.mutate(form, { onSuccess: () => toast("good", "알림 설정을 저장했습니다") })}>
            저장
          </Button>
        </div>
      </div>
    </Card>
  );
}

function ChannelsCard({ plan }: { plan: string }) {
  const channels = useChannels();
  const add = useAddChannel();
  const remove = useDeleteChannel();
  const test = useTestChannel();
  const toast = useToast();
  const allowed = PLAN_CHANNELS[plan] ?? ["email"];
  const [kind, setKind] = useState<Kind>("email");
  const [target, setTarget] = useState("");

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate({ kind, target, label: "" }, { onSuccess: () => setTarget("") });
  };

  return (
    <Card>
      <CardHeader title="어디로 보낼까요?" description="채널별로 실패하면 자동 재시도하고, 웹훅이 폐기되면 채널을 끄고 알려드립니다." />
      <div className="p-5">
        {channels.isLoading ? (
          <Skeleton className="h-20" />
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line">
            {channels.data?.map((ch) => {
              const meta = KIND[ch.kind as Kind] ?? KIND.email;
              const Icon = meta.icon;
              return (
                <li key={ch.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <Icon className="size-4 text-muted" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-ink">{ch.target}</div>
                    <div className="text-[12px] text-muted">
                      {meta.label}
                      {ch.last_error ? <span className="text-critical"> · {ch.last_error}</span> : null}
                    </div>
                  </div>
                  <Badge tone={ch.enabled ? "good" : "critical"}>{ch.enabled ? "사용 중" : "꺼짐"}</Badge>
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={test.isPending && test.variables === ch.id}
                    onClick={() => test.mutate(ch.id, { onSuccess: () => toast("good", "테스트 알림을 보냈습니다") })}
                  >
                    <Send className="size-3.5" aria-hidden /> 테스트
                  </Button>
                  <Button size="icon" variant="ghost" aria-label="채널 삭제" onClick={() => remove.mutate(ch.id)}>
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
        <form onSubmit={onSubmit} className="mt-4 flex flex-wrap gap-2">
          <Select aria-label="채널 종류" value={kind} onChange={(e) => setKind(e.target.value as Kind)} className="w-40">
            {(Object.keys(KIND) as Kind[]).map((k) => (
              <option key={k} value={k} disabled={!allowed.includes(k)}>
                {KIND[k].label}
                {allowed.includes(k) ? "" : " (상위 플랜)"}
              </option>
            ))}
          </Select>
          <Input
            aria-label="받는 곳"
            className="min-w-56 flex-1"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder={KIND[kind].placeholder}
            required
          />
          <Button type="submit" variant="secondary" loading={add.isPending}>
            추가
          </Button>
        </form>
        {add.error ? <div className="mt-3"><ErrorNote error={add.error} /></div> : null}
      </div>
    </Card>
  );
}

function LogCard() {
  const notes = useNotifications();
  return (
    <Card>
      <CardHeader title="발송 기록" description="최근 50건" />
      <div className="overflow-x-auto p-5">
        {notes.data && notes.data.length === 0 ? (
          <EmptyState title="아직 보낸 알림이 없습니다" />
        ) : (
          <table className="w-full min-w-[560px] text-[13px]">
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th className="py-2 font-medium">시각</th>
                <th className="py-2 font-medium">내용</th>
                <th className="py-2 font-medium">방식</th>
                <th className="py-2 font-medium">상태</th>
              </tr>
            </thead>
            <tbody>
              {notes.data?.map((n) => (
                <tr key={n.id} className="border-b border-line last:border-0">
                  <td className="tabular py-2 text-ink-2">{formatDateTime(n.sent_at ?? n.created_at)}</td>
                  <td className="py-2 text-ink">{n.headline}</td>
                  <td className="py-2 text-ink-2">{n.kind}</td>
                  <td className="py-2">
                    <Badge tone={n.status === "sent" ? "good" : n.status === "failed" ? "critical" : "neutral"}>
                      {n.status === "sent" ? "발송" : n.status === "failed" ? "실패" : n.status === "pending" ? "대기" : n.status}
                    </Badge>
                    {n.attempts > 1 ? <span className="ml-1 text-muted">({n.attempts}회 시도)</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  );
}

export default function AlertsPage() {
  const rule = useAlertRule();
  const me = useMe();
  const plan = me.data?.org.plan ?? "free";
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="알림" description="입찰공고를 기다리지 말고, 수요가 움직이는 순간 받아보세요." />
      {rule.data ? <RuleCard key={rule.dataUpdatedAt} rule={rule.data} plan={plan} /> : <Skeleton className="h-72" />}
      <ChannelsCard plan={plan} />
      <LogCard />
    </div>
  );
}
