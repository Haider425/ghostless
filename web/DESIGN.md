# Ghostless design

The approved design lives in Figma as "Ghostless redesign v2". It covers every page in light and dark, at desktop and phone widths. This file summarises the rules so the code stays consistent with it.

## Principles

- **Your record first.** On a job, the posting record (true age, the employer's usual time, flags with quoted evidence) comes before everything else.
- **Calm lists.** A job row is the title, company and "place · level · pay" as plain text, then the posting age. A risk tag appears only when a posting has flags, because "No flags" is the normal case. The match ring shows only when there's a resume.
- **Grey for structure, colour for meaning.** Neutrals do the layout. Blue is for actions, links and selection. Ochre and brick are only for ghost risk, and errors use a separate danger colour.
- **Confident type.** Inter throughout. Large, tightly set titles (40px pages, 76px home), 16px row titles, 15px UI text.

## Tokens

All tokens are in `src/app/globals.css`, with light and dark values. Tailwind names in brackets.

| Role | Light | Dark |
|---|---|---|
| Page (`paper`) | #ffffff | #191919 |
| Soft cards, wells, hover (`sunken`) | #f7f6f3 | #202020 |
| Raised panels, popovers (`surface`) | #ffffff | #252525 |
| Track, pressed (`hover`) | #efeeea | #2c2c2c |
| Hairline / strong border (`line`, `line-strong`) | #e9e9e7 / #d3d2ce | #2f2f2f / #3f3f3f |
| Text (`ink`, `ink-soft`, `ink-faint`) | #191919 / #5f5e5b / #686763 | #ededec / #b4b3af / #9c9b97 |
| Accent text / fill (`accent`, `accent-solid`) | #0a62c2 / #0a62c2 | #5ba4f0 / #1c6fcc |
| Accent tint (`accent-tint`) | #e8f1fc | #1c2b3c |
| Some flags (`ochre`, `ochre-tint`) | #8f5300 / #fbf0da | #e8ab4f / #3a2d17 |
| High risk (`brick`, `brick-tint`) | #c0302a / #fdebea | #ff8075 / #40211f |
| Errors, destructive (`danger`, `danger-tint`) | #c0302a / #fdebea | #ff8075 / #40211f |

Every text colour passes WCAG AA (4.5:1) against every surface in both themes. The lowest pair is 4.88:1.

## Shapes and parts

- **Buttons (`.btn`):** 40px tall with a 10px radius. Large ones (`.btn-lg`) are 48px with a 12px radius. Primary buttons are a blue fill; secondary buttons are outlined.
- **Filter pills (`.pill`):** rounded and outlined, with a blue tint when the filter is on.
- **Search fields (`.field-soft`):** a soft grey fill with no border until focused.
- **Containers:** cards (`.card`) are soft grey with a 16px radius, panels (`.panel`) are outlined with a 16px radius, and the posting record uses the soft card.
- **Tags (`.tag`):** quiet grey pills for skills.
- **Match:** a ring with the score inside (`Ring`), 40px in rows and 56px in panels.

## Layout

- A top navigation bar: Jobs, Companies, Resume, and Insights (Skills gap, Hiring calendar, How it works). On the right are Saved (or Applications when signed in), Log in and Sign up, or the avatar menu. On phones a full-width menu opens under the bar.
- **Jobs:** the toolbar, then role tabs, then the list next to a sticky preview panel. On phones, rows link to the job's own page.
- **Job page:** the header (logo, title, a row of facts with icons, Apply and Save), with the description on the left. The rail on the right holds the posting record, match, history and disclosures.
- **Home:** the headline and search, a real posting record as proof, three live figures, three reasons and one call to action.
- **Footer:** one line.
