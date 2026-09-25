/**
 * Small presentational primitives: Card, Badge, Field, Input, Textarea, Select, Skeleton,
 * EmptyState, SectionHeader. They own spacing, borders and theming so pages only compose.
 */
import { cva, type VariantProps } from "class-variance-authority";
import type {
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-xl border border-line bg-surface shadow-card", className)}
      {...rest}
    />
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-4 px-5 pt-5", className)}>
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        {description ? <p className="mt-1 text-[13px] text-muted">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12px] font-medium leading-5 whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "bg-surface-2 text-ink-2",
        accent: "bg-accent-soft text-accent-text",
        good: "bg-good/10 text-good-text",
        warning: "bg-warning/15 text-ink",
        critical: "bg-critical/10 text-critical",
        outline: "border border-line-strong text-ink-2",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...rest} />;
}

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-[13px] font-medium text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-[12px] text-critical" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-[12px] text-muted">{hint}</p>
      ) : null}
    </div>
  );
}

const control =
  "w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(control, "h-10", className)} {...rest} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(control, "min-h-24 py-2 leading-6", className)} {...rest} />;
}

export function Select({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(control, "h-10 pr-8", className)} {...rest} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-surface-2", className)} aria-hidden />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      {icon ? <div className="text-muted">{icon}</div> : null}
      <p className="text-[15px] font-semibold text-ink">{title}</p>
      {description ? <p className="max-w-md text-[13px] text-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[22px] font-bold tracking-tight text-ink">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "문제가 생겼어요. 잠시 후 다시 시도해 주세요.";
  return (
    <div
      role="alert"
      className="rounded-lg border border-critical/30 bg-critical/5 px-4 py-3 text-sm text-critical"
    >
      {message}
    </div>
  );
}
