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

Kinetic Atelier is a light paper, olive, and lime workspace. The operating screen
pairs a spatial craft diagram with a separate generator control panel. The diagram
explains the three configuration surfaces (mechanics, image, and sprite); it is
not a generated item or a progress display. Controller state remains authoritative.
Source summaries can reflect the current unsaved browser draft.

`studio.css` owns type, spacing, color, layout, and motion tokens. `studio-motion.js`
owns presentation interactions; `studio.js` owns routes, drafts, commands, and
receipts. Manrope, Cormorant, and the SVG symbols are served locally. There is no
frontend build step, CDN, animation dependency, or additional persisted UI state.

| Surface | Behavior |
| --- | --- |
| Craft diagram | Fine-pointer parallax, layered assembly/explosion, and source-specific hover/focus emphasis |
| Diagram links | The three layers and source summaries open the existing settings routes |
| Generator state | Explicit `data-state` derived from the existing home snapshot |
| Navigation | The selected rail marker travels on pointer navigation; keyboard changes are immediate |
| Pointer route change | A short horizontal reveal of the persistent workspace, triggered only by navigation |
| Settings | Existing labeled controls, advanced fields, drafts, and save receipts |
| Narrow viewport | Drawer at 720px, stacked sources, and a compact craft diagram |
| Pending action | Existing busy feedback and receipts remain authoritative |
| Input, keyboard navigation, search, polling | No page entrance animation |
| Motion pause | An in-memory control pauses decoration and makes state changes immediate |
| Reduced motion | System preference wins, including live changes; layered states remain operable without animation |

The craft stage is retained across home snapshot renders, and pointer interpolation
stops when settled, offscreen, hidden, or paused. Keyboard focus has priority over
an idle hovered source. The object is decorative and hidden from the accessibility
tree; its controls are ordinary buttons and route links.

Do not attach route entrance animations to the settings renderer: polling and
draft-dependent controls can rebuild it while a person is typing. Keep the mobile
drawer's CSS breakpoint aligned with `setMenu()` and the resize handler, including
focus trapping and inert content. Document scroll padding reserves space for the
fixed save tray before the first edit reveals it.

The palette is a presentation decision, not a compatibility contract. Visual
iterations should be reviewed in the browser before updating assertions that
encode the accepted appearance. Existing font licenses remain in `assets/`.

## Verification

Regression entry points:

    PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio_interactions.py LocalGenerator/tests/test_web_studio_state.py

For controller/browser integration, provide Playwright and Chromium. `INFINI_TEST_BROWSER_EXECUTABLE` can select an installed Chromium:

    PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio.py LocalGenerator/tests/test_web_studio_browser.py LocalGenerator/tests/test_web_studio_workflows_browser.py

The workflow tests still include the previous exact Atelier colors. Update those
presentation assertions after the new visual direction is approved. Their behavioral coverage includes keyboard search and focus,
route motion, dirty-state navigation and diagnostic tabs. Review the changed UI
in the browser, then run affected tests. Fixtures do not prove provider readiness
or visual quality.

These tests do not establish real provider authentication, paid generation,
Terraria gameplay, or Windows-specific filesystem behavior.
