# Browser Studio

Studio stays a loopback browser UI. Desktop packaging would not repair the original
presentation leak: browser commands were invoking modal Tk dialogs behind a hidden
window. All user-facing launchers now open the browser. Tk remains an internal
state/scheduling adapter, so Tcl/Tk is still required.

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

Regression entry points:

    PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio_interactions.py LocalGenerator/tests/test_web_studio_state.py

For native-controller/browser integration, provide a display, Playwright and
Chromium. `INFINI_TEST_BROWSER_EXECUTABLE` can select an installed Chromium:

    PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio.py LocalGenerator/tests/test_web_studio_browser.py

These tests do not establish real provider authentication, paid generation,
Terraria gameplay, or Windows-specific filesystem behavior.
