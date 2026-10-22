"""No-install entry point: python -m toolbox (offline unless --run)."""
from toolbox.cli import main

raise SystemExit(main())
