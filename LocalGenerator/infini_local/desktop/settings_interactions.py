"""Instance-scoped presentation boundary shared by native and browser Studio.

Workers never call these helpers. Their results are delivered on the Tk thread;
Studio supplies a non-blocking notification sink while native UI keeps dialogs.
"""
from infini_local.desktop.tk_compat import messagebox


def notify(app, level: str, title: str, message: str) -> None:
    sink = app.__dict__.get('_ui_notification_sink')
    if sink is not None:
        sink(level, title, message)
    else:
        getattr(messagebox, {'error': 'showerror', 'warning': 'showwarning'}.get(level, 'showinfo'))(title, message)


def finish_action(app, identifier, ok: bool, message: str, *, cancelled=False) -> None:
    app.__dict__.get('_studio_async_ids', set()).discard(identifier)
    sink = app.__dict__.get('_ui_action_sink')
    if sink is not None and identifier:
        sink(identifier, ok, message, cancelled=cancelled)


def begin_action(app):
    identifier = app.__dict__.get('_studio_command_id')
    if identifier:
        app.__dict__.setdefault('_studio_async_ids', set()).add(identifier)
    return identifier


def saved_config_revision(config_path):
    """Fingerprint the exact saved source, including fresh-install provenance."""
    import hashlib
    from infini_local.desktop.settings_gui_theme import EXAMPLE_PATH
    existing = config_path.exists()
    path = config_path if existing else EXAMPLE_PATH
    return hashlib.sha256((b'config:' if existing else b'example:') + path.read_bytes()).hexdigest()
