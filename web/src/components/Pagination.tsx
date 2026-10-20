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
  const linkClass = "btn btn-secondary";
  return (
    <nav aria-label="Pages" className="flex items-center justify-between gap-4 pt-8">
      {page > 1 ? (
        <Link href={href(page - 1)} className={linkClass} rel="prev">
          Previous
        </Link>
      ) : (
        <span />
      )}
      <p className="text-ui text-ink-soft">
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
