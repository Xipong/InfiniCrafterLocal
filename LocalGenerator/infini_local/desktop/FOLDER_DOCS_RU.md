# infini_local/desktop

Desktop/settings GUI code.

- `settings_gui.py` is the small public `SettingsGui` shell/entrypoint: Tk init, preset detection, `main()`.
- `settings_gui_theme.py` owns GUI paths/title/theme constants shared by the shell and mixins.
- `settings_gui_ui.py` owns theme/chrome/card builders, tabs and editable row widgets.
- `settings_gui_image_args.py` owns LoRA, sd.cpp extra-args/debug buttons and visual tab assembly.
- `settings_gui_trace_state.py` owns trace tab refresh, save/collect/preset/radmin status helpers.
- `settings_gui_server_controls.py` owns path pickers, health identity checks and local helper server lifecycle.
- `settings_schema.py` owns static field order/defaults/presets/help text for the GUI.
- `settings_env.py` owns config.env parse/write helpers for the GUI.
- `settings_widgets.py` owns small reusable Tk widgets (`ToolTip`, `ScrollFrame`).
- `settings_sdcpp_args.py` owns pure sd.cpp extra-args token/conflict helpers.
- `tk_compat.py` owns Tkinter import/headless fallback shims for GUI tests and headless Python.

This is operational UI, not the runtime contract source. If config affects gameplay/asset generation, verify the actual pipeline/core consumer.
