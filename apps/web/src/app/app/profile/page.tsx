"use client";

import { Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { ChipGroup, TagInput } from "@/components/ui/controls";
import { Card, CardHeader, ErrorNote, Field, Input, PageHeader, Skeleton, Textarea } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import type { Schemas } from "@/lib/api/client";
import { useCategories, useMe, useProfile, useSaveProfile } from "@/lib/api/hooks";

const SIDO = [
  { key: "11", label: "서울" }, { key: "26", label: "부산" }, { key: "27", label: "대구" },
  { key: "28", label: "인천" }, { key: "29", label: "광주" }, { key: "30", label: "대전" },
  { key: "31", label: "울산" }, { key: "36", label: "세종" }, { key: "41", label: "경기" },
  { key: "51", label: "강원" }, { key: "43", label: "충북" }, { key: "44", label: "충남" },
  { key: "52", label: "전북" }, { key: "46", label: "전남" }, { key: "47", label: "경북" },
  { key: "48", label: "경남" }, { key: "50", label: "제주" },
];
const PLAN_REGION_LIMIT: Record<string, number | null> = { free: 1, pro: 5, team: null };

const toEok = (won: number | null | undefined) => (won ? String(won / 100_000_000) : "");
const fromEok = (text: string) => {
  const n = Number(text);
  return text.trim() && Number.isFinite(n) && n > 0 ? Math.round(n * 100_000_000) : null;
};

function ProfileForm({ initial }: { initial: Schemas["ProfileIO"] }) {
  const toast = useToast();
  const save = useSaveProfile();
  const categories = useCategories();
  const me = useMe();
  const limit = PLAN_REGION_LIMIT[me.data?.org.plan ?? "free"] ?? 1;
  const [form, setForm] = useState(initial);
  const [budgetMin, setBudgetMin] = useState(toEok(initial.budget_min));
  const [budgetMax, setBudgetMax] = useState(toEok(initial.budget_max));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(
      { ...form, budget_min: fromEok(budgetMin), budget_max: fromEok(budgetMax) },
      { onSuccess: () => toast("good", "저장했습니다. 추천을 다시 계산하고 있습니다.") },
    );
  };

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <Card>
        <CardHeader title="무엇을 파나요?" description="의미 검색에 쓰입니다. 제품·서비스와 주요 레퍼런스를 적어 주세요." />
        <div className="space-y-5 p-5">
          <Field label="회사 소개" htmlFor="description">
            <Textarea
              id="description"
              value={form.description ?? ""}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="예: 냉난방·공기청정 기능의 스마트쉘터와 스마트폴을 제조·설치하며, 지자체 납품 실적 30건"
              maxLength={2000}
            />
          </Field>
          <Field label="관심 키워드" htmlFor="keywords" hint="Enter로 추가합니다. 공고명·예산서 세부사업명에 나올 단어가 좋습니다.">
            <TagInput
              id="keywords"
              value={form.keywords ?? []}
              onChange={(keywords) => setForm({ ...form, keywords })}
              placeholder="스마트쉘터, 선별관제, 디지털트윈…"
            />
          </Field>
          <Field label="제외 키워드" htmlFor="excludes" hint="이 단어가 들어간 기회는 순위를 크게 낮춥니다.">
            <TagInput
              id="excludes"
              value={form.exclude_keywords ?? []}
              onChange={(exclude_keywords) => setForm({ ...form, exclude_keywords })}
              placeholder="청소용역, 유지보수…"
            />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader title="어디에, 얼마 규모로?" />
        <div className="space-y-5 p-5">
          <Field label="관심 분야" htmlFor="categories">
            <ChipGroup
              ariaLabel="관심 분야"
              options={categories.data ?? []}
              value={form.categories ?? []}
              onChange={(next) => setForm({ ...form, categories: next })}
            />
          </Field>
          <Field
            label="관심 지역 (시·도)"
            htmlFor="regions"
            hint={
              limit === null
                ? "선택하지 않으면 전국을 봅니다."
                : `현재 플랜은 ${limit}개까지 선택할 수 있습니다. 선택하지 않으면 전국을 봅니다.`
            }
          >
            <ChipGroup
              ariaLabel="관심 지역"
              options={SIDO}
              value={form.region_codes ?? []}
              onChange={(next) => {
                if (limit !== null && next.length > limit) {
                  toast("critical", `현재 플랜은 관심 지역을 ${limit}개까지 설정할 수 있습니다`);
                  return;
                }
                setForm({ ...form, region_codes: next });
              }}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="최소 사업 규모 (억 원)" htmlFor="bmin">
              <Input id="bmin" inputMode="decimal" value={budgetMin} onChange={(e) => setBudgetMin(e.target.value)} placeholder="1" />
            </Field>
            <Field label="최대 사업 규모 (억 원)" htmlFor="bmax">
              <Input id="bmax" inputMode="decimal" value={budgetMax} onChange={(e) => setBudgetMax(e.target.value)} placeholder="20" />
            </Field>
          </div>
        </div>
      </Card>

      {save.error ? <ErrorNote error={save.error} /> : null}
      <div className="flex justify-end">
        <Button type="submit" loading={save.isPending}>
          저장하고 추천 다시 받기
        </Button>
      </div>
    </form>
  );
}

function ProfileContent() {
  const profile = useProfile();
  const params = useSearchParams();
  const welcome = params.get("welcome") === "1";
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="회사 프로필" description="이 정보로 어떤 공공 수요가 우리 회사 기회인지 판단합니다." />
      {welcome ? (
        <div className="flex items-start gap-3 rounded-xl border border-accent/30 bg-accent-soft px-4 py-3 text-sm text-ink">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-accent-text" aria-hidden />
          가입을 환영합니다. 키워드와 분야를 저장하면 지방의회 회의록·예산서·나라장터에서 찾은 신호로 맞춤 피드를 만들어 드립니다.
        </div>
      ) : null}
      {profile.isLoading ? <Skeleton className="h-96" /> : profile.data ? <ProfileForm initial={profile.data} /> : <ErrorNote error={profile.error} />}
    </div>
  );
}

export default function ProfilePage() {
  return (
    <Suspense>
      <ProfileContent />
    </Suspense>
  );
}
