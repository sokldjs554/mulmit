"use client";

import { useCallback, useState } from "react";

/**
 * Track an element's content width so SVG charts draw in real pixels: axis text stays at its
 * specified size instead of scaling with a viewBox, and narrow cards get their own layout.
 */
export function useWidth<T extends HTMLElement>(fallback: number) {
  const [width, setWidth] = useState(fallback);
  const ref = useCallback((node: T | null) => {
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry && entry.contentRect.width > 0) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}
