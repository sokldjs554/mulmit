"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Logo } from "@/components/layout/shell";
import { Button } from "@/components/ui/button";
import { Card, ErrorNote, Field, Input } from "@/components/ui/primitives";
import { useLogin } from "@/lib/api/hooks";

const DEMO = { email: "demo@example.com", password: "demo-pass-1234" };
const ADMIN = { email: "admin@example.com", password: "admin-pass-1234" };

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const submit = (creds: { email: string; password: string }) =>
    login.mutate(creds, {
      onSuccess: (me) => {
        const next = params.get("next");
        const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : null;
        router.replace(safeNext ?? (me.user.is_staff ? "/admin" : "/app"));
      },
    });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit({ email, password });
  };

  return (
    <Card className="w-full max-w-sm p-6">
      <Logo />
      <h1 className="mt-6 text-xl font-bold text-ink">로그인</h1>
      <p className="mt-1 text-sm text-muted">공고가 나오기 전에 잡힌 사업들이 기다리고 있어요.</p>
      <form className="mt-6 space-y-4" onSubmit={onSubmit}>
        <Field label="이메일" htmlFor="email">
          <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </Field>
        <Field label="비밀번호" htmlFor="password">
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        {login.error ? <ErrorNote error={login.error} /> : null}
        <Button type="submit" className="w-full" loading={login.isPending}>
          로그인
        </Button>
      </form>
      <div className="mt-5 space-y-2 border-t border-line pt-5">
        <p className="text-[12px] text-muted">가입 없이 바로 둘러볼 수 있어요 · 가상 데이터</p>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" size="sm" onClick={() => submit(DEMO)} disabled={login.isPending}>
            고객사로 둘러보기
          </Button>
          <Button variant="secondary" size="sm" onClick={() => submit(ADMIN)} disabled={login.isPending}>
            운영자로 둘러보기
          </Button>
        </div>
      </div>
      <p className="mt-5 text-center text-[13px] text-muted">
        아직 계정이 없으세요?{" "}
        <Link href="/signup" className="font-medium text-accent-text hover:underline">
          무료로 시작하기
        </Link>
      </p>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
