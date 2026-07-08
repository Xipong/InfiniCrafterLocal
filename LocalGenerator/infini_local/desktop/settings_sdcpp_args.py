from __future__ import annotations

import shlex


# AGENT MAP: pure sd.cpp extra-args token helpers for settings_gui.py.
# These functions preserve GUI conflict-replacement behavior without depending on Tk.

VALUE_FLAGS = {"--rng", "--flow-shift", "--lora-apply-mode", "--params-backend", "--cache-mode", "--cache-option", "--backend"}


def split_extra_for_gui(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    try:
        return shlex.split(raw, posix=True)
    except ValueError:
        return raw.split()


def join_extra_for_gui(tokens: list[str]) -> str:
    if not tokens:
        return ""
    try:
        return shlex.join(tokens)
    except AttributeError:
        return " ".join(tokens)


def extra_option_names(tokens: list[str]) -> set[str]:
    names: set[str] = set()
    i = 0
    while i < len(tokens):
        token = str(tokens[i])
        name = token.split("=", 1)[0]
        if name in VALUE_FLAGS:
            names.add(name)
            i += 2 if "=" not in token and i + 1 < len(tokens) else 1
        else:
            i += 1
    return names


def remove_extra_options(tokens: list[str], names: set[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        token = str(tokens[i])
        name = token.split("=", 1)[0]
        if name in names:
            i += 2 if name in VALUE_FLAGS and "=" not in token and i + 1 < len(tokens) else 1
            continue
        out.append(token)
        i += 1
    return out


__all__ = [
    "VALUE_FLAGS",
    "split_extra_for_gui",
    "join_extra_for_gui",
    "extra_option_names",
    "remove_extra_options",
]
