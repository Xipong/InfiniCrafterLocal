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

The light paper, olive, and lime interface has eight content-focused routes:

| Route | Contents |
| --- | --- |
| `operate` | Generator state and controls; selected text model, image backend, and sprite processing |
| `configure` | Profiles, current configuration summaries, recommendations, and the complete field list |
| `providers` | Text provider, model, account, and request settings |
| `images` | Selected image backend and its generation settings |
| `sprites` | Transparency, resizing, and palette settings |
| `models` | sd.cpp program, local weights, and LoRA |
| `multiplayer` | Generator address, Terraria connection, and sprite delivery |
| `diagnostics` | Last health snapshot, trace source, logs, and saved failure details |

Settings pages combine live summaries of the current per-tab draft with relevant
field groups. Disabled and externally managed settings retain their meaning.
Controller snapshots and command receipts remain authoritative; selecting a model
does not establish provider readiness. Existing field keys, IDs, `data-action`,
`data-ui`, diagnostic tabs, and keyboard/focus contracts are retained.

`studio.css` owns type, spacing, color, layout, and motion tokens. `studio-motion.js`
owns presentation interactions; `studio.js` owns routes, drafts, commands, and
receipts. Manrope, Cormorant, and the SVG symbols are served locally. There is no
frontend build step, CDN, animation dependency, or additional persisted UI state.

`[data-flow-card]` links use a local fine-pointer highlight driven by normalized
`--pointer-x` / `--pointer-y` and `data-pointer-active`. Interpolation stops when
settled; leaving, keyboard input, offscreen cards, and hidden tabs clear it. There
are no idle animation loops. The navigation marker travels on pointer activation;
keyboard selection is immediate. Route reveals run only on pointer navigation,
not typing, draft-summary updates, or polling. `prefers-reduced-motion` applies
immediately, including live preference changes.

Diagnostics use guarded JSON inspectors only for sd.cpp and saved failures. HTTP
reachability requires an explicit probe; managed-process state and `autostart`
are separate readouts. Known empty failure snapshots show no saved error.
Full JSON remains in a disclosure, whose open state survives unchanged polling;
unsupported content falls back to raw text. Trace source/status stays visible
outside the inspector. No progress percentage is inferred from logs.

Keep the mobile drawer's 720px breakpoint aligned with `setMenu()` and the resize
handler, including focus trapping and inert content. Existing font licenses remain
in `assets/`.

## Verification

The current visual iteration is **under review, not approved**. Mass regression
suites have not been run for this iteration. Palette and appearance assertions
must follow the reviewed design while retaining behavioral and DOM-contract
coverage; update those assertions after visual approval.

Regression entry points, to run after browser review:

    PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio_interactions.py LocalGenerator/tests/test_web_studio_state.py

For controller/browser integration, provide Playwright and Chromium. `INFINI_TEST_BROWSER_EXECUTABLE` can select an installed Chromium:

    PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio.py LocalGenerator/tests/test_web_studio_browser.py LocalGenerator/tests/test_web_studio_workflows_browser.py

Behavioral coverage includes keyboard search and focus, route motion, dirty-state
navigation, and diagnostic tabs. Fixtures do not establish visual quality, real
provider authentication, paid generation, Terraria gameplay, or Windows-specific
filesystem behavior.
