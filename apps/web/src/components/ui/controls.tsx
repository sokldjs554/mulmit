"use client";

import { Moon, Sun, X } from "lucide-react";
import { useState, useSyncExternalStore, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";

/** Free-text tag input: Enter or comma adds, Backspace on empty removes the last tag. */
export function TagInput({
  id,
  value,
  onChange,
  placeholder,
  max = 30,
}: {
  id?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  max?: number;
}) {
  const [draft, setDraft] = useState("");
  const add = (raw: string) => {
    const tag = raw.trim();
    if (!tag || value.includes(tag) || value.length >= max) return;
    onChange([...value, tag]);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === "Enter" || e.key === ",") && !e.nativeEvent.isComposing) {
      e.preventDefault();
      add(draft);
      setDraft("");
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };
  return (
    <div className="flex min-h-10 flex-wrap items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-2 py-1.5 focus-within:border-accent">
      {value.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-md bg-accent-soft py-0.5 pr-1 pl-2 text-[13px] text-accent-text"
        >
          {tag}
          <button
            type="button"
            className="rounded p-0.5 hover:bg-accent/15"
            aria-label={`${tag} 삭제`}
            onClick={() => onChange(value.filter((t) => t !== tag))}
          >
            <X className="size-3" aria-hidden />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => {
          add(draft);
          setDraft("");
        }}
        placeholder={value.length ? "" : placeholder}
        className="min-w-24 flex-1 bg-transparent px-1 text-sm text-ink placeholder:text-muted focus:outline-none"
      />
    </div>
  );
}

/** Multi-select as toggle chips (categories, stages). */
export function ChipGroup({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { key: string; label: string; count?: number }[];
  value: string[];
  onChange: (next: string[]) => void;
  ariaLabel: string;
}) {
  return (
    <div role="group" aria-label={ariaLabel} className="flex flex-wrap gap-1.5">
      {options.map((opt) => {
        const on = value.includes(opt.key);
        return (
          <button
            key={opt.key}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((v) => v !== opt.key) : [...value, opt.key])}
            className={cn(
              "h-8 rounded-full border px-3 text-[13px] transition-colors",
              on
                ? "border-accent bg-accent-soft font-medium text-accent-text"
                : "border-line-strong text-ink-2 hover:bg-surface-2",
            )}
          >
            {opt.label}
            {opt.count !== undefined ? (
              <span className={cn("tabular ml-1.5", on ? "text-accent-text" : "text-muted")}>{opt.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { key: T; label: string; disabled?: boolean }[];
  value: T;
  onChange: (next: T) => void;
  ariaLabel: string;
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="inline-flex rounded-lg bg-surface-2 p-1">
      {options.map((opt) => (
        <button
          key={opt.key}
          type="button"
          role="radio"
          aria-checked={value === opt.key}
          disabled={opt.disabled}
          onClick={() => onChange(opt.key)}
          className={cn(
            "h-8 rounded-md px-3 text-[13px] transition-colors disabled:opacity-40",
            value === opt.key ? "bg-surface font-semibold text-ink shadow-card" : "text-ink-2 hover:text-ink",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

type Theme = "light" | "dark";

function readTheme(): Theme {
  const current = document.documentElement.dataset.theme;
  if (current === "light" || current === "dark") return current;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Re-render when <html data-theme> or the OS preference changes (another tab's toggle included). */
function subscribeTheme(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", onChange);
  return () => {
    observer.disconnect();
    media.removeEventListener("change", onChange);
  };
}

export function ThemeToggle() {
  const theme = useSyncExternalStore<Theme | null>(subscribeTheme, readTheme, () => null);
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* private mode: the toggle still works for this page view */
    }
  };
  return (
    <button
      type="button"
      onClick={toggle}
      className="inline-flex size-9 items-center justify-center rounded-lg text-ink-2 hover:bg-surface-2 hover:text-ink"
      aria-label={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
    >
      {theme === "dark" ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
    </button>
  );
}
