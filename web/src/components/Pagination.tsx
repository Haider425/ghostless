import Link from "next/link";

export function Pagination({
  page,
  total,
  pageSize,
  href,
}: {
  page: number;
  total: number;
  pageSize: number;
  href: (page: number) => string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  const linkClass =
    "inline-flex h-9 items-center rounded-md border border-line-strong bg-surface px-3 text-sm font-medium text-ink hover:border-accent hover:text-accent";
  return (
    <nav aria-label="Pages" className="flex items-center justify-between gap-4 pt-6">
      {page > 1 ? (
        <Link href={href(page - 1)} className={linkClass} rel="prev">
          Previous
        </Link>
      ) : (
        <span />
      )}
      <p className="text-sm text-ink-soft">
        Page {page.toLocaleString("en-CA")} of {Math.min(pages, 400).toLocaleString("en-CA")}
      </p>
      {page < Math.min(pages, 400) ? (
        <Link href={href(page + 1)} className={linkClass} rel="next">
          Next
        </Link>
      ) : (
        <span />
      )}
    </nav>
  );
}
