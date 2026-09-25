"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Logo } from "@/components/layout/shell";
import { Button } from "@/components/ui/button";
import { Card, ErrorNote, Field, Input } from "@/components/ui/primitives";
import { useSignup } from "@/lib/api/hooks";

export default function SignupPage() {
  const router = useRouter();
  const signup = useSignup();
  const [form, setForm] = useState({ email: "", password: "", name: "", company_name: "" });
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    signup.mutate(form, { onSuccess: () => router.replace("/app/profile?welcome=1") });
  };

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <Card className="w-full max-w-sm p-6">
        <Logo />
        <h1 className="mt-6 text-xl font-bold text-ink">무료로 시작하기</h1>
        <p className="mt-1 text-sm text-muted">가입하면 크레딧 3개를 드려요. 영업 브리핑 한 건을 바로 받아 볼 수 있어요.</p>
        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <Field label="회사명" htmlFor="company">
            <Input id="company" value={form.company_name} onChange={set("company_name")} required maxLength={200} />
          </Field>
          <Field label="이름" htmlFor="name">
            <Input id="name" value={form.name} onChange={set("name")} required maxLength={100} />
          </Field>
          <Field label="업무용 이메일" htmlFor="email">
            <Input id="email" type="email" autoComplete="email" value={form.email} onChange={set("email")} required />
          </Field>
          <Field label="비밀번호" htmlFor="password" hint="8자 이상">
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={form.password}
              onChange={set("password")}
              required
            />
          </Field>
          {signup.error ? <ErrorNote error={signup.error} /> : null}
          <Button type="submit" className="w-full" loading={signup.isPending}>
            가입하고 관심 분야 설정하기
          </Button>
        </form>
        <p className="mt-5 text-center text-[13px] text-muted">
          이미 계정이 있으세요?{" "}
          <Link href="/login" className="font-medium text-accent-text hover:underline">
            로그인
          </Link>
        </p>
      </Card>
    </main>
  );
}
