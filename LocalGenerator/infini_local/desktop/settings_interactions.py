"""Owner-thread notifications and action receipts for browser Studio."""


def notify(app, level: str, title: str, message: str) -> None:
    sink = app.__dict__.get('_ui_notification_sink')
    if sink is not None:
        sink(level, title, message)
    else:
        app.status = message


def finish_action(app, identifier, ok: bool, message: str, *, cancelled=False, saved=False) -> None:
    app.__dict__.get('_studio_async_ids', set()).discard(identifier)
    sink = app.__dict__.get('_ui_action_sink')
    if sink is not None and identifier:
        sink(identifier, ok, message, cancelled=cancelled, saved=saved)


def begin_action(app):
    identifier = app.__dict__.get('_studio_command_id')
    if identifier:
        app.__dict__.setdefault('_studio_async_ids', set()).add(identifier)
    return identifier


def saved_config_revision(config_path, *, example_path=None):
    """Fingerprint the exact saved source, including fresh-install provenance."""
    import hashlib
    from infini_local.desktop.settings_paths import EXAMPLE_PATH
    existing = config_path.exists()
    path = config_path if existing else (EXAMPLE_PATH if example_path is None else example_path)
    return hashlib.sha256((b'config:' if existing else b'example:') + path.read_bytes()).hexdigest()
