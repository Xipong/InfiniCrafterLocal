"""The campaign help path must not bootstrap the generator."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_runner_help_does_not_import_generator_before_admitted_run():
    script = """
import runpy, sys
class RejectProduction:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'infini_local' or fullname.startswith('infini_local.'):
            raise AssertionError('generator imported before admitted run')
sys.meta_path.insert(0, RejectProduction())
sys.argv = ['runner', '--help']
runpy.run_module('toolbox.live.runner', run_name='__main__')
"""
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert '--run' in result.stdout
