"use client";

import { Radar, Search } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";

import { OpportunityCard } from "@/components/opportunity/opportunity-card";
import { Button } from "@/components/ui/button";
import { ChipGroup, Segmented } from "@/components/ui/controls";
import { EmptyState, ErrorNote, Input, PageHeader, Select, Skeleton } from "@/components/ui/primitives";
import { useCategories, useFeed, type FeedFilters } from "@/lib/api/hooks";
import { STAGES } from "@/lib/utils";

type StatusKey = "open" | "bid_open" | "all";

export default function FeedPage() {
  const [query, setQuery] = useState("");
  const [stages, setStages] = useState<string[]>([]);
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState<StatusKey>("all");
  const deferredQuery = useDeferredValue(query);
  const categories = useCategories();

  const filters: FeedFilters = useMemo(
    () => ({
      q: deferredQuery.trim() || undefined,
      stage: stages,
      category: category ? [category] : [],
      status: status === "all" ? ["open", "bid_open"] : [status],
    }),
    [deferredQuery, stages, category, status],
  );
  const feed = useFeed(filters);
  const items = feed.data?.pages.flatMap((p) => p.items) ?? [];
  const total = feed.data?.pages[0]?.total ?? 0;
  const early = items.filter((i) => i.stage === "council_mention" || i.stage === "budget_line").length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="기회 피드"
        description={
          feed.data
            ? `우리 회사에 맞는 공공 수요 ${total.toLocaleString("ko-KR")}건 · 이 중 ${early}건은 아직 발주계획도 나오지 않은 단계입니다`
            : "우리 회사에 맞는 공공 수요를 불러오는 중입니다"
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input
            aria-label="사업명 검색"
            placeholder="사업명 검색 (예: 스마트쉘터)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          aria-label="분야"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="w-full sm:w-44"
        >
          <option value="">모든 분야</option>
          {categories.data?.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </Select>
        <Segmented<StatusKey>
          ariaLabel="상태"
          value={status}
          onChange={setStatus}
          options={[
            { key: "all", label: "전체" },
            { key: "open", label: "공고 전" },
            { key: "bid_open", label: "입찰 진행" },
          ]}
        />
      </div>
      <ChipGroup
        ariaLabel="단계"
        options={STAGES.slice(0, 5).map((s) => ({ key: s.key, label: s.label }))}
        value={stages}
        onChange={setStages}
      />

      {feed.error ? <ErrorNote error={feed.error} /> : null}

      <div className={feed.isPlaceholderData ? "space-y-3 opacity-60 transition-opacity" : "space-y-3"}>
        {feed.isLoading
          ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-44 w-full rounded-xl" />)
          : items.map((item) => <OpportunityCard key={item.id} item={item} />)}
      </div>

      {!feed.isLoading && items.length === 0 ? (
        <EmptyState
          icon={<Radar className="size-8" aria-hidden />}
          title="조건에 맞는 기회가 아직 없습니다"
          description="관심 키워드와 분야를 넓히면 더 많은 신호를 받아볼 수 있습니다. 새 회의록과 예산서는 매일 수집됩니다."
          action={
            <Link href="/app/profile">
              <Button variant="secondary">회사 프로필 수정</Button>
            </Link>
          }
        />
      ) : null}

      {feed.hasNextPage ? (
        <div className="flex justify-center">
          <Button variant="secondary" onClick={() => feed.fetchNextPage()} loading={feed.isFetchingNextPage}>
            더 보기
          </Button>
        </div>
      ) : null}
    </div>
  );
}
