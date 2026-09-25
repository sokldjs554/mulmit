"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";

import { ErrorNote, Skeleton } from "@/components/ui/primitives";
import { useRegisterCard } from "@/lib/api/hooks";

/** Toss redirects here after card authentication with ?authKey=…&customerKey=… */
function Exchange() {
  const params = useSearchParams();
  const router = useRouter();
  const register = useRegisterCard();
  const started = useRef(false);

  useEffect(() => {
    const authKey = params.get("authKey");
    const customerKey = params.get("customerKey");
    if (started.current || !authKey || !customerKey) return;
    started.current = true; // StrictMode double-invokes effects; exchange the authKey once.
    register.mutate(
      { auth_key: authKey, customer_key: customerKey },
      { onSuccess: () => router.replace("/app/billing") },
    );
  }, [params, register, router]);

  if (register.error) return <ErrorNote error={register.error} />;
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-2">카드를 등록하고 있습니다…</p>
      <Skeleton className="h-24" />
    </div>
  );
}

export default function BillingSuccessPage() {
  return (
    <Suspense>
      <Exchange />
    </Suspense>
  );
}
