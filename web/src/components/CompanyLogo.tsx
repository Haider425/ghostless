"use client";

import Image from "next/image";
import { useState } from "react";

import { initials } from "@/lib/format";

/*
  A company's logo, from its website's icon via Google's favicon service.
  Images go through Next's image optimizer, so visitors' browsers never
  contact Google directly. Without a known domain, or if the icon fails to
  load, a lettered tile in one neutral colour stands in.
*/

const SIZES = { sm: 36, md: 44, lg: 56 } as const;

export function CompanyLogo({
  name,
  domain,
  size = "md",
}: {
  name: string;
  domain?: string | null;
  size?: keyof typeof SIZES;
}) {
  const [failed, setFailed] = useState(false);
  const px = SIZES[size];
  const box = { sm: "size-9 rounded-lg text-meta", md: "size-11 rounded-[10px] text-ui", lg: "size-14 rounded-xl text-lg" }[size];

  if (domain && !failed) {
    return (
      <span className={`${box} grid shrink-0 place-items-center overflow-hidden border border-line bg-logo`}>
        <Image
          src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128`}
          alt=""
          width={px}
          height={px}
          className="size-[70%] object-contain"
          onError={() => setFailed(true)}
        />
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`${box} logo-tile grid shrink-0 place-items-center font-semibold`}
    >
      {initials(name)}
    </span>
  );
}
