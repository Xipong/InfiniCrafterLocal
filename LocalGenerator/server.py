from __future__ import annotations

# Launcher. Real implementation lives in:
#   LocalGenerator/infini_local/web/server.py
# Keep APP_VERSION literal here for static release/version hygiene checks.
APP_VERSION = "0.4.239"

from infini_local.web import api as _impl
from infini_local.web.server import main

if __name__ == "__main__":
    main()
else:
    import sys as _sys
    _sys.modules[__name__] = _impl
