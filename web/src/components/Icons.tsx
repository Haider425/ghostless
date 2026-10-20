import type { SVGProps } from "react";

/* A small set of stroke icons, drawn on a 20px grid. Decorative: always aria-hidden. */

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, className = "size-4", ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...props}
    >
      {children}
    </svg>
  );
}

export const SearchIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="8.5" cy="8.5" r="5.5" />
    <path d="m13 13 4 4" />
  </Icon>
);

export const BookmarkIcon = ({ filled, ...p }: IconProps & { filled?: boolean }) => (
  <Icon {...p}>
    <path d="M5.5 3.5h9v13l-4.5-3-4.5 3z" fill={filled ? "currentColor" : "none"} />
  </Icon>
);

export const ExternalIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M11 4h5v5M16 4l-7 7M14 11.5V16H4V6h4.5" />
  </Icon>
);

export const ChevronDownIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m5.5 8 4.5 4.5L14.5 8" />
  </Icon>
);

export const ChevronRightIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m8 5.5 4.5 4.5L8 14.5" />
  </Icon>
);

export const MenuIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
  </Icon>
);

export const CloseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m5 5 10 10M15 5 5 15" />
  </Icon>
);

export const PinIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M10 17.5s5.5-4.8 5.5-9.2a5.5 5.5 0 0 0-11 0c0 4.4 5.5 9.2 5.5 9.2Z" />
    <circle cx="10" cy="8.3" r="1.9" />
  </Icon>
);

export const ClockIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="10" cy="10" r="7" />
    <path d="M10 6.2V10l2.6 1.6" />
  </Icon>
);

export const PayIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="2.5" y="5" width="15" height="10" rx="2" />
    <circle cx="10" cy="10" r="2.2" />
  </Icon>
);

export const FilterIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.5 5.5h13M6 10h8M8.5 14.5h3" />
  </Icon>
);

export const QuoteIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 12.5c0-3 1.5-5 4-6M11 12.5c0-3 1.5-5 4-6" />
    <circle cx="6" cy="13" r="2" fill="currentColor" stroke="none" />
    <circle cx="13" cy="13" r="2" fill="currentColor" stroke="none" />
  </Icon>
);

export const ChartIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.5 16.5h13M6 13.5V10M10 13.5V6M14 13.5V8.5" />
  </Icon>
);

export const CalendarIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="4.5" width="13" height="12" rx="2" />
    <path d="M3.5 8.5h13M7 3v3M13 3v3" />
  </Icon>
);

export const InfoIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="10" cy="10" r="6.5" />
    <path d="M10 9v4.5M10 6.5v.01" />
  </Icon>
);

export const LevelIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.5 15.5h3v-4h3v-4h3v-4h4" />
  </Icon>
);

export const RoleIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3" y="6" width="14" height="10.5" rx="1.5" />
    <path d="M7.5 6V4.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V6" />
  </Icon>
);

export const ShareIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M10 3v9M6.5 6.5 10 3l3.5 3.5M4.5 11v4.5h11V11" />
  </Icon>
);

export const NoteIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4.5 15.5h11M11.5 4.5l3 3-7 7h-3v-3Z" />
  </Icon>
);

export const CheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m4.5 10.5 3.5 3.5 7.5-8" />
  </Icon>
);

export const CrossIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m6 6 8 8M14 6l-8 8" />
  </Icon>
);

export const FlagIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 17V3.5M5 4h9l-2 3.5 2 3.5H5" />
  </Icon>
);

export const BulbIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7.5 14.5h5M8 17h4M10 3a5 5 0 0 0-3 9c.6.5 1 1.2 1 2h4c0-.8.4-1.5 1-2a5 5 0 0 0-3-9Z" />
  </Icon>
);

export const PlusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M10 4.5v11M4.5 10h11" />
  </Icon>
);

export const DocIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 3.5h6.5L15 7v9a.5.5 0 0 1-.5.5h-9A.5.5 0 0 1 5 16Z" />
    <path d="M11.5 3.5V7H15M7.5 10.5h5M7.5 13.5h3.5" />
  </Icon>
);
