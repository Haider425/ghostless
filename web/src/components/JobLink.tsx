"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type MouseEvent, type ReactNode, useEffect, useTransition } from "react";

const WIDE = "(min-width: 1024px)";

/**
 * A link to a job's page. On wide screens, when `previewHref` is given, a plain
 * click opens the job in the search page's preview pane instead, keeping the
 * results in place. Modified clicks, narrow screens and no-JavaScript all
 * follow the real link.
 */
export function JobLink({
  href,
  previewHref,
  current,
  className,
  children,
}: {
  href: string;
  previewHref?: string;
  current?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    const root = document.documentElement;
    if (pending) root.dataset.pending = "";
    else delete root.dataset.pending;
  }, [pending]);

  function onClick(event: MouseEvent<HTMLAnchorElement>) {
    if (!previewHref || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!window.matchMedia(WIDE).matches) return;
    event.preventDefault();
    startTransition(() => router.push(previewHref, { scroll: false }));
  }

  return (
    <Link href={href} onClick={onClick} aria-current={current ? "true" : undefined} className={className}>
      {children}
    </Link>
  );
}
