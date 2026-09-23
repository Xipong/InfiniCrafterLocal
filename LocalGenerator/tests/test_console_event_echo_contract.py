"""Contract: craft failures must be visible in the server console, not only in the log file.

The server window used to print a startup banner and then stay silent forever:
``log_event`` only appended to ``cache/events.ndjson``.  A failing craft therefore
looked like the generator doing nothing at all, and the actual reason was only
discoverable by opening the log afterwards.

``events.ndjson`` remains the complete record.  The console echo is a strict
subset of it, selected by ``INFINI_CONSOLE_EVENT_LEVEL``, and must never become a
second source of truth or swallow a level the user asked to see.
"""

import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACE_TOOLS = ROOT / "infini_local" / "storage" / "trace_tools.py"
TRACE_RUNTIME = ROOT / "infini_local" / "storage" / "trace_runtime.py"
SERVER = ROOT / "infini_local" / "web" / "server.py"


def _check_file_record_is_written_regardless_of_echo(tmp_path, capsys):
    from infini_local.storage import trace_tools

    # Echo disabled: the file must still receive the full event.
    trace_tools.log_event(tmp_path, "warn", "silent event", {"status": 400})
    captured = capsys.readouterr()
    assert captured.out == "", "no echo must be printed when echo_levels is empty"

    rows = [
        json.loads(line)
        for line in io.open(tmp_path / "events.ndjson", encoding="utf-8")
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["level"] == "warn"
    assert rows[0]["message"] == "silent event"
    assert rows[0]["payload"] == {"status": 400}


def _check_echo_prints_only_requested_levels(tmp_path, capsys):
    from infini_local.storage import trace_tools

    for level in ("debug", "info", "warn", "error"):
        trace_tools.log_event(
            tmp_path, level, f"{level} line", {"status": 400}, echo_levels=("warn", "error")
        )
    printed = capsys.readouterr().out

    assert "warn line" in printed
    assert "error line" in printed
    # Informational noise stays out of the window.
    assert "info line" not in printed
    assert "debug line" not in printed

    # Every level still reached the file: the echo filters the console, not the record.
    rows = [
        json.loads(line)
        for line in io.open(tmp_path / "events.ndjson", encoding="utf-8")
        if line.strip()
    ]
    assert [row["level"] for row in rows] == ["debug", "info", "warn", "error"]


def _check_echo_line_is_readable_and_bounded(tmp_path, capsys):
    from infini_local.storage import trace_tools

    long_hint = "п" * 5000
    trace_tools.log_event(
        tmp_path,
        "warn",
        "LLM strict json_schema rejected",
        {
            "hint": long_hint,
            "status": 400,
            "was": "json_schema",
            "now": "json_object",
            "ignored": "x" * 9000,
        },
        echo_levels=("warn", "error"),
    )
    printed = capsys.readouterr().out.strip()

    assert printed.count("\n") == 0, "one event must stay one console line"
    assert "WARN: LLM strict json_schema rejected" in printed
    # The operator needs the actionable fields.
    assert "was=json_schema" in printed
    assert "now=json_object" in printed
    assert "status=400" in printed
    # Unlisted payload keys must not be dumped into the window.
    assert "ignored=" not in printed
    # A runaway hint is clipped rather than flooding the terminal.
    assert len(printed) < 700
    assert "…" in printed


def _check_level_threshold_resolution(monkeypatch):
    import importlib

    from infini_local.storage import trace_runtime

    cases = {
        "warn": ("warn", "error"),
        "WARN": ("warn", "error"),
        "error": ("error",),
        "info": ("info", "warn", "error"),
        "debug": ("debug", "info", "warn", "error"),
        # Silence has to be asked for explicitly.
        "off": (),
        "none": (),
        "silent": (),
        # An empty or unrecognized value means "not configured", so the
        # recommended default applies instead of silently losing diagnostics.
        "": ("warn", "error"),
        "nonsense": ("warn", "error"),
    }
    for value, expected in cases.items():
        monkeypatch.setenv("INFINI_CONSOLE_EVENT_LEVEL", value)
        reloaded = importlib.reload(trace_runtime)
        assert reloaded._configured_echo_levels() == expected, value

    # Default with the variable absent must be the recommended warn+error.
    monkeypatch.delenv("INFINI_CONSOLE_EVENT_LEVEL", raising=False)
    reloaded = importlib.reload(trace_runtime)
    assert reloaded._configured_echo_levels() == ("warn", "error")


def _check_runtime_and_server_are_wired_to_the_echo():
    runtime_text = TRACE_RUNTIME.read_text(encoding="utf-8")
    server_text = SERVER.read_text(encoding="utf-8")
    tools_text = TRACE_TOOLS.read_text(encoding="utf-8")

    # The runtime log_event must pass the configured levels through.
    assert "echo_levels=CONSOLE_EVENT_LEVELS" in runtime_text
    assert "INFINI_CONSOLE_EVENT_LEVEL" in runtime_text
    # The file write must stay unconditional, before any echo decision.
    assert tools_text.index("append_ndjson(cache_dir") < tools_text.index("if echo_levels")
    # The banner must tell the user which mode is active and how to change it.
    assert "CONSOLE_EVENT_LEVELS" in server_text
    assert "INFINI_CONSOLE_EVENT_LEVEL" in server_text


def _check_setting_is_exposed_in_the_gui():
    from infini_local.desktop import settings_schema

    assert "INFINI_CONSOLE_EVENT_LEVEL" in settings_schema.FIELD_ORDER
    assert settings_schema.DEFAULTS["INFINI_CONSOLE_EVENT_LEVEL"] == "warn"
    help_text = settings_schema.FIELD_HELP["INFINI_CONSOLE_EVENT_LEVEL"]
    assert "events.ndjson" in help_text
    choices = settings_schema.OPTION_HELP["INFINI_CONSOLE_EVENT_LEVEL"]
    assert set(choices) == {"warn", "error", "info", "debug", "off"}


# One collected item per contract module: the checks above keep source order and
# their own tracebacks. The shared runner discovers them by prefix, so a new check
# cannot be silently left out of a hand-maintained dispatch list.
def test_console_event_echo_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")
