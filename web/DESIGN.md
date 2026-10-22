# Ghostless design

The brand is direction B, "Friendly ghost", from the Figma file "Ghostless polish v3" (page "Brand directions"). It's warm, made for students and new grads, and built around one character: a friendly ghost with a magnifying glass who checks every posting. This file summarises the rules so the code stays consistent with it.

## Principles

- **The ghost does the explaining.** The mascot (`GhostMascot`) appears where a person needs reassurance or a nudge: the home hero, empty states, the 404 page. Never as decoration in dense views like the job list.
- **Evidence, not a verdict.** Every number, note and quote on the home page comes from live data. The stamp says "High ghost risk", never "Fake".
- **Warm paper, white cards.** The page is warm paper; content sits on white cards with a hairline and a soft shadow (`.card`, `.panel`). Recessed areas use the warm `sunken` tone (`.well`).
- **Colour for meaning.** Blue is for actions, links and selection. Ochre and brick are only for ghost risk. The yellow highlighter and the pastel reason cards are brand accents on the home page. In the app, pastels mean status only, through the status chips (`.chip`): mint for good (no flags, first seen in the last 3 days, a real vacancy), butter for caution (some flags, overdue, AI screening), blush for a problem (high ghost risk, not a real vacancy), warm grey for neutral facts.
- **Motion that explains, once.** The home hero tells its story in about five seconds and then stops; the ghost keeps a gentle float. Everything is static for reduced motion (system setting or Settings page).

## Type

- **Bricolage Grotesque** for every heading and the wordmark (`font-display`, `font-brand`).
- **Figtree** for all interface and body text (`font-sans`, `font-friendly`).
- **Caveat** only for the handwritten notes on the home page (`font-hand`).
- Inter stays loaded as the fallback. All three brand faces are self-hosted by `next/font/google` at build time.

## Tokens

All tokens are in `src/app/globals.css`, with light and dark values (dark is warm too). Tailwind names in brackets.

| Role | Light | Dark |
|---|---|---|
| Page (`paper`) | #fbf7f0 | #191713 |
| Cards, popovers (`surface`) | #ffffff | #23201b |
| Wells, hover fills (`sunken`) | #f3ede2 | #201d19 |
| Track, pressed (`hover`) | #ece5d7 | #2b2722 |
| Hairline / strong border (`line`, `line-strong`) | #e8e1d4 / #d6ccba | #34302a / #463f36 |
| Text (`ink`, `ink-soft`, `ink-faint`) | #17140f / #5c564c / #6a6358 | #f3efe7 / #bdb6a9 / #9f978a |
| Accent text / fill (`accent`, `accent-solid`) | #0a62c2 / #0a62c2 | #6aaef5 / #1c6fcc |
| Some flags (`ochre`, `ochre-tint`) | #8a5000 / #fbefd6 | #e8ab4f / #3a2d17 |
| High risk, errors (`brick`, `danger`) | #b42a24 | #ff8a7e |

Brand accents for the home page (`b-*`): yellow highlighter #ffd84a (text on it is always ink), pastels blush #ffe1d8, mint #ddf3e4, lilac #e8e2ff, sky #e3f0ff, butter #fff1c2, each with a dark counterpart.

Every text colour passes WCAG AA (4.5:1) on every surface it's used on, in both themes. The lowest pair is 4.73:1. Faint text is never placed on the pastel cards.

## Shapes and parts

- **Buttons (`.btn`):** 40px tall, 12px radius; large 48px. Primary is blue, secondary outlined white.
- **Cards (`.card`) and panels (`.panel`):** white, 1px hairline, 20px radius, soft shadow.
- **Filter pills (`.pill`):** rounded, outlined; tinted when on.
- **Quick links on home:** pastel pills with a coloured dot.
- **Status chips (`.chip` with `.chip-good`, `.chip-warn`, `.chip-bad`, `.chip-neutral`):** fully rounded, 24px tall (`.chip-md` is larger). Every pair passes AA (5.16:1 or more) in both themes. No icons in age chips.
- **Empty states (`EmptyState`):** the mascot, a title that says what's missing, one sentence, one action.
- **Loading:** the floating mascot with one line of what's happening ("Checking today's postings…"), above skeleton rows. The float stops for reduced motion.

## Layout

- Top bar: the mascot wordmark, Jobs, Companies, Resume, Insights; Saved (or Applications), Log in, Sign up. On the home page the bar takes the warm paper so the page reads as one sheet.
- **Home:** the badge with today's flagged count, the highlighted headline, the search, pastel quick links, the animated exhibit (a real high-risk posting checked by the ghost, with handwritten notes on desktop), the yellow live ticker, three pastel reason cards, and one call to action.
- **Jobs and job page:** list rows stay plain (logo, title, company, facts, status chips); nothing decorative per row. The selected row lifts onto a white card. The ghost appears only in loading, no results, a closed posting and a posting with no description. Flags on the posting record are pastel cards (blush for high risk, butter otherwise); disclosure answers are status chips.
- **Companies, resume tools:** unchanged structure, on the brand's tokens and type.
