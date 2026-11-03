"""No-install router: Live panels require --run; workbench owns its explicit commands."""
from toolbox.cli import main

raise SystemExit(main())
