# Accessibility and RTL audit (M7)

The panel is used by Persian-speaking administrators, often with a keyboard and often on
a shared screen. This document records what is guaranteed by tests, and where the
guarantees live, so a regression is caught by CI rather than by a user.

---

## 1. Direction and language

| Guarantee | Where it is enforced |
| --- | --- |
| `<html lang="fa" dir="rtl">` by default, synchronised on language switch | `src/i18n/index.ts` (`applyDocumentLocale`), asserted in `rtl.test.tsx` |
| Logical CSS properties only — no `ml-`, `pr-`, `left-`, `text-left` anywhere | `rtl.test.tsx` walks every source file and fails on a physical utility |
| The layout is *designed* for Persian, not mirrored: sidebar and forms use `text-start`, tables put the first column on the right edge | `components/ui/*`, `components/layout/*` |

## 2. Technical values inside Persian text

An API key (`xrx_live_8f2a…`), an endpoint path, a JSON payload or an IP address must
survive the bidi algorithm unchanged:

* `<Ltr>` renders `dir="ltr" lang="en"` with `unicode-bidi: isolate` for inline runs;
* `<CodeBlock>` uses `isolate-override` for JSON, curl samples and log payloads;
* request ids, provider/model names, status codes, error codes and endpoint paths are all
  rendered through `<Ltr>`; the request-log detail also offers the full payload as a
  strict LTR JSON block with copy-to-clipboard;
* digits: presentation values follow the administrator's numeral style (Persian by
  default), technical values always stay Latin.

Covered by `rtl.test.tsx` (isolation islands, no physical utilities) and by the module
tests, which assert `dir="ltr"` on the rendered nodes.

## 3. Keyboard and focus

The modal contract is tested in `a11y.test.tsx`:

| Behaviour | Test |
| --- | --- |
| Focus moves into the dialog on open and starts on its first control | `moves focus into the dialog…` |
| `Tab` and `Shift+Tab` cycle inside the dialog and never reach the page behind it | same test |
| `Escape` closes the dialog | same test |
| Focus returns to the button that opened it | same test |
| Body scrolling is locked while open and restored on close | `locks body scrolling…` |
| Confirmation dialogs expose their title and a labelled «لغو» action | `gives the confirmation dialog…` |

Destructive actions always open a Persian confirmation dialog (`ConfirmDialog`), so a
destructive click is never a single keystroke away.

## 4. Semantics

* A skip link («پرش به محتوای اصلی») is the first focusable element in the shell and
  targets `#main-content`.
* Every dialog is `role="dialog" aria-modal="true"` with `aria-labelledby` and an optional
  `aria-describedby`.
* Icon-only buttons carry `aria-label` (close, copy, run check, row actions).
* Toasts and loading states use `aria-live="polite"`; error states render the stable
  English `error.code` inside an LTR badge, so a report can quote it.
* Form controls are labelled: `<label htmlFor>` where the id is explicit, `aria-label` on
  composite widgets (icon buttons, switches, search fields).
* Tables use real `<table>/<th>/<td>` markup with a sticky header, asserted in
  `a11y.test.tsx`.

## 5. Layout at 1280px and 1920px

Long Persian sentences («مدت نگهداری آمار مصرف پیش از تجمیع و پاک‌سازی») sit next to long
technical values (a 512-character payload, an endpoint path, a model id). The rules that
keep both readable:

* the shell's content column is `min-w-0`, so a wide child cannot push the sidebar off
  screen;
* every table lives inside `<TableWrapper>` (`overflow-x-auto`), so a wide row scrolls
  horizontally instead of breaking the page — asserted in `rtl.test.tsx`;
* long technical cells use `<Ltr>` with `truncate`/`whitespace-nowrap` where appropriate,
  and the full value remains available in the row's `title` (relative times, ids) or in
  the detail drawer;
* the sidebar collapses to icons and becomes a drawer on narrow screens.

Manual audit procedure (before a release):

1. Open every module at 1280×800 and 1920×1080 with the demo dataset loaded
   (`python -m app.seeds`).
2. Check for horizontal page scroll (there must be none), clipped Persian text and any
   technical value that reorders visually.
3. Navigate one full flow with the keyboard only: sign in → providers → models →
   api-keys → routing → usage → logs → settings.
4. Switch the language to English and back, confirming that the direction flips and no
   layout jumps.

## 6. What is deliberately out of scope

* No third-party accessibility overlay: the guarantees above are in the components, not
  bolted on.
* Automated WCAG conformance scoring is not part of CI; the tests assert the interaction
  contract the DoD names (semantics, focus, labelling, direction) instead of a score whose
  meaning depends on the rule set version.
