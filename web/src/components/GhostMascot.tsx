/**
 * Ghostless's mascot: a friendly ghost with a magnifying glass, the one who
 * checks every posting. Decorative (aria-hidden). It keeps its own colours in
 * both themes, like a sticker: a white body with an ink outline.
 */
export function GhostMascot({ className = "", withLens = true }: { className?: string; withLens?: boolean }) {
  return (
    <svg viewBox="0 0 140 160" fill="none" aria-hidden="true" className={className}>
      <path
        d="M70 12C38 12 20 38 20 70V138L34 128L48 140L62 128L76 140L90 128L104 140L118 128V70C118 38 102 12 70 12Z"
        fill="#FFFFFF"
        stroke="#17140F"
        strokeWidth="4"
        strokeLinejoin="round"
      />
      <ellipse cx="54" cy="66" rx="6" ry="8" fill="#17140F" />
      <ellipse cx="86" cy="66" rx="6" ry="8" fill="#17140F" />
      <circle cx="56" cy="63" r="2" fill="#FFFFFF" />
      <circle cx="88" cy="63" r="2" fill="#FFFFFF" />
      <ellipse cx="44" cy="82" rx="7" ry="4" fill="#FFB8A6" />
      <ellipse cx="96" cy="82" rx="7" ry="4" fill="#FFB8A6" />
      <path d="M62 84C66 89 74 89 78 84" stroke="#17140F" strokeWidth="3.5" strokeLinecap="round" />
      {withLens && (
        <g className="ghost-lens">
          <circle cx="122" cy="96" r="16" fill="#FFF7D6" stroke="#17140F" strokeWidth="4" />
          <path d="M110 108L98 122" stroke="#17140F" strokeWidth="6" strokeLinecap="round" />
          <path d="M116 90C118 87 122 86 125 87" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round" />
        </g>
      )}
    </svg>
  );
}

/** The small ghost used as a bullet in the ticker and badges. */
export function MiniGhost({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={className}>
      <path
        d="M5 20V10.5a7 7 0 0 1 14 0V20l-2.33-1.6L14.33 20 12 18.4 9.67 20l-2.34-1.6L5 20Z"
        fill="#FFFFFF"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <circle cx="9.5" cy="10.5" r="1.2" fill="currentColor" />
      <circle cx="14.5" cy="10.5" r="1.2" fill="currentColor" />
    </svg>
  );
}
