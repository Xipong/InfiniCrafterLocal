# Browser Studio

Studio is a loopback browser UI backed by a plain-data Python controller and
owner-thread event loop. It needs no Tk widgets, hidden windows, Tcl/Tk, or display
server. All user-facing launchers open the same browser interface.

- Notifications, confirmations, config preview, and file selection stay in-page.
  The path picker returns local paths; it never uploads model files.
- Browser drafts are per-tab. Save/start use an optimistic saved-config revision.
  A conflict requires explicit review; rebasing preserves unrelated disk changes.
- Validation checks the draft. Health, trace, cache and server controls use saved
  settings or the recorded owned launch target, not another tab's prepared draft.
- Async commands have bounded per-ID receipts. Queue acceptance is not completion.
- Non-saving transformations return their own result before restoring the adapter.
- The guide opens the existing, self-contained offline handbook. Config preview
  masks credential assignments and does not create or save a config file.

## Presentation

The current Studio uses an Atelier palette: an ivory workspace, charcoal-olive
rail, and lime primary actions. This is a description of the present design,
**not a palette or layout compatibility contract**. A redesign may change
colors, navigation, copy, DOM and component geometry together with their
presentation assertions. Judge it in the browser at desktop and narrow widths;
do not protect a screenshot's incidental CSS values at the expense of the
new design. Generator status still comes from the controller snapshot, while
source choices may reflect the unsaved browser draft. The interface must not
infer model readiness or invent generated items, progress, metrics, or ETA.

`studio.css` owns the shared color, type, spacing, radius, and motion tokens.
If the palette changes, keep contrast and state meaning legible across the rail,
save tray, dialogs, toasts, links and controls; do not keep a color solely because
a test expects it.
Manrope and the SVG symbols are served locally. There is no frontend build step,
CDN, animation dependency, or additional persisted UI state.

| Surface | Behavior |
| --- | --- |
| Primary action / active navigation | Visually distinct, accessible hierarchy; exact colors belong to the current design, not the contract |
| Generator state | Explicit `data-state` derived from the existing home state |
| Settings | Shared labeled controls; advanced and inactive values remain accessible |
| Narrow viewport | Drawer at 720px; stacked fields; independently scrollable trace tabs |
| Pointer route change | One 160ms opacity / 4px transition on the persistent workspace |
| Dialog, save tray, toast | Short CSS entry transitions, with immediate dismissal |
| Pending action | Busy feedback retains its element across snapshot polling |
| Input, keyboard navigation, search, polling | No page entrance animation |
| Reduced motion | Immediate changes; static loading and search-location feedback |

Route motion is triggered by an actual pointer navigation and cleared on keyboard
input, completion, or the next navigation. Do not attach entrance animations to
the settings renderer: polling and draft-dependent controls can rebuild it while
a person is typing. Keep the mobile drawer's CSS breakpoint aligned with
`setMenu()` and the resize handler, including focus trapping and inert content.
Document scroll padding reserves room for the fixed save tray before the first
edit reveals it, keeping native focus scrolling above the tray.

Design guidance was reviewed from
[Anthropic frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md),
[Impeccable's product UI guidance](https://github.com/pbakaus/impeccable/blob/main/skill/reference/operate.md),
and [Emil Kowalski's animation guidance](https://github.com/emilkowalski/skills/blob/main/skills/animate/SKILL.md).
These are references, not vendored skills or runtime dependencies. Existing font
licenses remain in `assets/`.

## Verification

Regression entry points:

    PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio_interactions.py LocalGenerator/tests/test_web_studio_state.py

For controller/browser integration, provide Playwright and Chromium. `INFINI_TEST_BROWSER_EXECUTABLE` can select an installed Chromium:

    PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio.py LocalGenerator/tests/test_web_studio_browser.py LocalGenerator/tests/test_web_studio_workflows_browser.py

The workflow tests currently include Atelier palette checks at desktop/mobile widths;
update or replace those exact-color assertions when the design changes. They also cover
pointer-only route motion, keyboard search, field focus across snapshots, reduced motion,
narrow-screen diagnostic tabs with long trace content, and native Tab navigation above
the dirty save tray. For a visual task, first implement a complete pass, review real
desktop/mobile screenshots, fix obvious visual defects, then run affected
regressions. Test fixtures are not evidence of provider readiness or aesthetic
quality; avoid repeating unchanged backend checks as a visual gate.

These tests do not establish real provider authentication, paid generation,
Terraria gameplay, or Windows-specific filesystem behavior.
