"use client";

import { type ReactNode, useEffect, useRef } from "react";

/**
 * Fades its content up the first time it scrolls into view. Purely visual:
 * the content is visible by default (readable without JavaScript, by
 * crawlers and in full-page captures); only once the script runs is a block
 * that starts below the screen hidden until it scrolls in. Nothing moves for
 * reduced motion (see .reveal in globals.css).
 */
export function Reveal({ children, className = "", delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    if (node.getBoundingClientRect().top < window.innerHeight) return; // already on screen: leave it be
    node.classList.add("reveal-pending");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            observer.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={ref} className={`reveal ${className}`.trim()} style={{ ["--d" as string]: `${delay}s` }}>
      {children}
    </div>
  );
}
