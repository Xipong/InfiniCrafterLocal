"""Generator diagnostic, asset and lifecycle HTTP routes."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse

from infini_local.core.config_bootstrap import APP_VERSION, ROOT, CACHE_DIR, SPRITE_DIR, WORLD_RECIPES_DIR
from infini_local.core.image_dependencies import Image
from infini_local.services.sdcpp_service import SDCPP_SERVER_STATE, cleanup_server_process
from infini_local.pipelines import generation_debug
from infini_local.pipelines.images.backends import ensure_sdcpp_server, sdcpp_debug_snapshot
from infini_local.pipelines.images.prompts import asset_negative_prompt, normalize_asset_prompt
from infini_local.pipelines.images.stage import generate_visual_asset, maybe_generate_sprite
from infini_local.pipelines.images.validation import alpha_stats
from infini_local.services import asset_sync_service
from infini_local.services.combine_endpoint import request_shutdown
from infini_local.storage import trace_runtime
from infini_local.storage.trace_runtime import clear_trace_files, trace_event
from infini_local.storage.world_storage import read_json_file
from infini_local.web import trace_dashboard
from infini_local.web.server_status import health_payload, multiplayer_connect_info
from infini_local.web.server_trace_snapshot import trace_snapshot, trace_snapshot_html


ASSET_STREAM_CHUNK_BYTES = 64 * 1024


def handle_get(handler: Any, path: str) -> bool:
    request_path = urlparse(path).path

    if request_path == "/health":
        handler.json(health_payload())
        return True
    if request_path == "/mp_connect.json":
        handler.json({"ok": True, "version": APP_VERSION, "multiplayer": multiplayer_connect_info()})
        return True
    if request_path == "/mp_connect":
        mp_connect_html(handler)
        return True
    if request_path == "/trace.json":
        handler.json(trace_snapshot(full=parse_qs(urlparse(path).query).get("full") == ["1"]))
        return True
    if request_path == "/trace":
        write_html(handler, trace_snapshot_html(full=parse_qs(urlparse(path).query).get("full") == ["1"]))
        return True
    if request_path.startswith("/sdcpp"):
        if request_path == "/sdcpp_start":
            sdcpp_start_endpoint(handler)
            return True
        if request_path == "/sdcpp_debug":
            handler.json(sdcpp_debug_snapshot(include_log_tail=True))
            return True
        return False
    if request_path == "/visual_doctor.json":
        handler.json(visual_doctor_payload(path))
        return True
    if request_path == "/visual_doctor":
        visual_doctor_html(handler, path)
        return True
    if request_path == "/debug/last_combine_failure":
        handler.json(generation_debug.last_combine_failure_payload())
        return True
    if request_path == "/debug/recipe_health":
        handler.json({"recipeStorage": "authoritative_world_recipe_files", "health": debug_recipe_health()})
        return True
    if request_path == "/debug/contracts":
        handler.json(debug_contracts())
        return True
    if request_path == "/debug/latest_recipe":
        handler.json(debug_latest_recipe_dump(path))
        return True
    if request_path == "/debug/recipes":
        handler.json({"recipeStorage": "authoritative_world_recipe_files", "recipes": debug_recipes()})
        return True
    if request_path == "/debug/worlds":
        handler.json({"worldRecipesDir": str(WORLD_RECIPES_DIR), "worlds": debug_worlds()})
        return True
    if request_path == "/get_asset":
        get_asset(handler, path)
        return True
    if request_path.startswith("/sprite/"):
        sprite_file(handler, path)
        return True
    return False


def handle_post(handler: Any, path: str, payload: dict[str, Any]) -> bool:
    request_path = urlparse(path).path
    if request_path == "/shutdown":
        shutdown(handler, path)
        return True
    if request_path == "/trace_clear":
        trace_clear(handler)
        return True
    return False


def shutdown(handler: Any, path: str = "") -> None:
    force = parse_qs(urlparse(path).query).get("force", ["0"])[0] == "1"
    accepted, activity = request_shutdown(force=force)
    if not accepted:
        handler.json_status(409, {
            "ok": False, "status": "generator_busy", "version": APP_VERSION,
            "generationActivity": activity, "message": "Active or queued generation prevents safe shutdown.",
        })
        return
    handler.json({
        "ok": True,
        "version": APP_VERSION,
        "serverRoot": str(ROOT),
        "pid": os.getpid(),
        "message": "shutdown scheduled",
        "generationActivity": activity,
        "forced": force,
    })

    def _shutdown_later() -> None:
        time.sleep(0.15)
        try:
            cleanup_server_process(SDCPP_SERVER_STATE, trace_runtime.log_event, "http_shutdown")
        finally:
            try:
                handler.server.shutdown()
            except Exception:
                pass

    threading.Thread(target=_shutdown_later, daemon=True).start()


def mp_connect_html(handler: Any) -> None:
    body = trace_dashboard.render_mp_connect_html(multiplayer_connect_info())
    write_html(handler, body)


def write_html(handler: Any, html: str) -> None:
    body = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def trace_clear(handler: Any) -> None:
    cleared = clear_trace_files((trace_runtime.TRACE_FILE, trace_runtime.PROMPT_TRACE_FILE, CACHE_DIR / "events.ndjson"))
    handler.json({"ok": True, "version": APP_VERSION, "cleared": cleared})


def sdcpp_start_endpoint(handler: Any) -> None:
    trace_event("step", "SDCPP:startup", "manual /sdcpp_start requested", {})
    ok = ensure_sdcpp_server()
    snap = sdcpp_debug_snapshot(include_log_tail=not ok)
    snap["ok"] = bool(ok)
    handler.json(snap)


def _file_check(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {"path": "", "configured": False, "exists": False, "kind": "missing"}
    try:
        p = Path(text)
        if os.name != "nt" and len(text) >= 3 and text[1] == ":" and text[2] in {"/", "\\"}:
            relative = text[3:].replace("\\", "/")
            p = Path("/mnt") / text[0].lower() / relative
        exists = p.exists()
        return {
            "path": text,
            "resolvedPath": str(p),
            "configured": True,
            "exists": exists,
            "isFile": p.is_file(),
            "isDir": p.is_dir(),
            "bytes": p.stat().st_size if exists and p.is_file() else None,
        }
    except Exception as e:
        return {"path": text, "configured": True, "exists": False, "error": repr(e)}


def _dir_writable_check(path: Path) -> dict[str, Any]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".infini_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"path": str(path), "exists": True, "writable": True}
    except Exception as e:
        return {"path": str(path), "exists": path.exists(), "writable": False, "error": repr(e)}


def _visual_probe_payload(role: str = "item", prompt: str = "") -> dict[str, Any]:
    role = (role or "item").lower()
    role = role if role in {"item", "projectile", "impact", "child", "field"} else "item"
    test_id = f"doctor_{role}_{int(time.time())}"
    # Explicit diagnostic art, not an old authored-item packet whose prose
    # or name is expected to synthesize a missing prompt or gameplay.
    prompt = prompt or "One cyan crystal blade with a violet slime edge and white star-shaped circuit inlay."
    dummy = {"id": test_id, "visual": {"preferredCanvasSize": 32}, "debug": {}}
    canvas = 32 if role == "item" else 48 if role == "projectile" else 32
    if role == "item":
        dummy["visual"]["imagePrompt"] = prompt
        before = time.time()
        dummy = maybe_generate_sprite(dummy)
        visual = dummy.get("visual") if isinstance(dummy.get("visual"), dict) else {}
        path = str(visual.get("spritePath") or "")
        alpha = {}
        if path and Image is not None and Path(path).exists():
            alpha = alpha_stats(Image.open(path).convert("RGBA"))
        return {"ok": bool(path and Path(path).exists()), "role": role, "ms": int((time.time() - before) * 1000), "visual": visual, "alpha": alpha, "debug": dummy.get("debug")}
    prompt = normalize_asset_prompt(dummy, role, prompt, canvas)
    before = time.time()
    sprite_path, url, score, status = generate_visual_asset(dummy, role, prompt, asset_negative_prompt(role), test_id, canvas)
    alpha = {}
    if sprite_path and Image is not None and Path(sprite_path).exists():
        alpha = alpha_stats(Image.open(sprite_path).convert("RGBA"))
    return {"ok": bool(sprite_path and Path(sprite_path).exists()), "role": role, "ms": int((time.time() - before) * 1000), "status": status, "path": sprite_path, "url": url, "score": score, "alpha": alpha, "debug": dummy.get("debug")}


def visual_doctor_payload(path: str) -> dict[str, Any]:
    q = parse_qs(urlparse(path).query)
    probe = str(q.get("probe", ["0"])[0]).strip().lower() in {"1", "true", "yes", "on"}
    role = q.get("role", ["item"])[0]
    health = health_payload()
    backend = str(health.get("imageBackend") or "").lower()
    sdcpp = sdcpp_debug_snapshot(include_log_tail=not probe) if backend == "sdcpp" else {}
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, level: str, message: str, **extra: Any) -> None:
        checks.append({"name": name, "ok": bool(ok), "level": level, "message": message, **extra})

    backend_error = str(health.get("imageBackendConfigError") or "").strip()
    backend_ok = bool(backend and not backend_error and backend != "off")
    add(
        "image_backend",
        backend_ok,
        "error" if not backend_ok else "ok",
        backend_error or "A supported image backend must be active for required item sprites.",
        value=backend,
        rawValue=health.get("imageBackendRaw"),
    )
    if health.get("visualRequireZImageBackend"):
        add(
            "zimage_backend_required",
            backend == "sdcpp",
            "error" if backend != "sdcpp" else "ok",
            "INFINI_VISUAL_REQUIRE_ZIMAGE_BACKEND=1 requires the sd.cpp backend.",
            value=backend,
        )
    add("visual_item_required", bool(health.get("visualRequireItemSprite")), "error" if not health.get("visualRequireItemSprite") else "ok", "Broken/missing item sprites should block craft delivery.")
    add("positive_only_prompt", bool(health.get("zImagePositiveOnly", True)), "warn" if not health.get("zImagePositiveOnly", True) else "ok", "Z-Image should use positive-only prompt contract.")
    add("pillow", bool(health.get("pillowAvailable")), "error" if not health.get("pillowAvailable") else "ok", "Pillow is required for sprite postprocess/keying.")
    add("sprite_dir_writable", _dir_writable_check(SPRITE_DIR).get("writable", False), "error", "Sprite cache must be writable.", check=_dir_writable_check(SPRITE_DIR))
    add("cache_dir_writable", _dir_writable_check(CACHE_DIR).get("writable", False), "error", "Cache dir must be writable.", check=_dir_writable_check(CACHE_DIR))
    if backend == "sdcpp":
        managed = sdcpp.get("autostart") is not False
        if managed:
            add("sdcpp_configured", bool(sdcpp.get("serverConfigured")), "error", "Managed sd.cpp requires local server exe/model configuration.")
            for key in ("serverExe", "model", "vae", "llm"):
                fc = _file_check(sdcpp.get(key))
                required = key in {"serverExe", "model"}
                add(f"sdcpp_{key}", bool(fc.get("isFile") or (not required and not fc.get("configured"))),
                    "error" if required else "warn", f"Managed sd.cpp {key} path check.", check=fc)
            if sdcpp.get("loraFile"):
                fc = _file_check(sdcpp.get("loraFile"))
                add("sdcpp_lora_file", bool(fc.get("isFile")), "warn", "Optional LoRA file path check.", check=fc)
        else:
            endpoint = urlparse(str(sdcpp.get("serverUrl") or ""))
            add("sdcpp_endpoint", endpoint.scheme in {"http", "https"} and bool(endpoint.hostname),
                "error", "Externally managed sd.cpp requires a configured HTTP endpoint, not local model files.")
        add("sdcpp_alive", bool(sdcpp.get("serverAlive")), "warn" if managed else "error",
            "Managed sd.cpp can start on demand." if managed else "Externally managed sd.cpp must already be reachable.")

    probe_payload = None
    if probe:
        try:
            probe_payload = _visual_probe_payload(role=role, prompt=q.get("prompt", [""])[0])
            add("live_sprite_probe", bool(probe_payload.get("ok")), "error" if not probe_payload.get("ok") else "ok", "Live Z-Image -> postprocess -> PNG probe.", probe=probe_payload)
        except Exception as e:
            probe_payload = {"ok": False, "error": repr(e)}
            add("live_sprite_probe", False, "error", "Live sprite probe crashed.", probe=probe_payload)

    errors = [c for c in checks if not c.get("ok") and c.get("level") == "error"]
    warnings = [c for c in checks if not c.get("ok") and c.get("level") == "warn"]
    return {
        "ok": not errors,
        "version": APP_VERSION,
        "summary": "ready" if not errors and not warnings else "ready_with_warnings" if not errors else "not_ready",
        "checks": checks,
        "probe": probe_payload,
        "health": {k: health.get(k) for k in ["imageBackend", "visualRequireItemSprite", "visualRequireZImageBackend", "zImagePromptContract", "zImagePositiveOnly", "bgRemoveMode", "bgColor", "spriteRetries", "visualAssetMode"]},
        "sdcpp": sdcpp,
        "links": {"health": "/health", "sdcppStart": "/sdcpp_start", "sdcppDebug": "/sdcpp_debug", "trace": "/trace", "probeItem": "/visual_doctor.json?probe=1&role=item"},
    }


def visual_doctor_html(handler: Any, path: str) -> None:
    payload = visual_doctor_payload(path)
    rows = []
    for c in payload.get("checks", []):
        mark = "✅" if c.get("ok") else "⚠️" if c.get("level") == "warn" else "❌"
        rows.append(f"<tr><td>{mark}</td><td><b>{c.get('name')}</b></td><td>{c.get('message')}</td><td><code>{json.dumps({k:v for k,v in c.items() if k not in {'name','ok','level','message'}}, ensure_ascii=False)[:800]}</code></td></tr>")
    html = f"""
    <!doctype html><meta charset='utf-8'><title>Infini Visual Doctor</title>
    <style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;max-width:1200px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px;vertical-align:top}}code,pre{{white-space:pre-wrap;background:#f6f6f6;padding:2px 4px}}.bar a{{margin-right:12px}}</style>
    <h1>Infini Visual Doctor</h1>
    <p>Status: <b>{payload.get('summary')}</b>. This checks the mandatory Z-Image/sprite delivery path before you burn ingredients.</p>
    <p class='bar'><a href='/visual_doctor.json'>json</a><a href='/visual_doctor.json?probe=1&role=item'>live item probe</a><a href='/visual_doctor.json?probe=1&role=projectile'>live projectile probe</a><a href='/sdcpp_start'>start sd.cpp</a><a href='/trace'>trace</a></p>
    <table><tr><th></th><th>check</th><th>meaning</th><th>details</th></tr>{''.join(rows)}</table>
    <h2>Raw payload</h2><pre>{json.dumps(payload, ensure_ascii=False, indent=2)}</pre>
    """
    write_html(handler, html)


def _iter_recipe_records(world_dir: Path | None = None) -> Iterator[dict[str, Any]]:
    """Order file metadata first, then read only bodies the consumer needs.

    Metadata discovery still scans O(N) paths. Unreadable/legacy records may
    require more reads before a view fills; world aggregates remain full scans.
    No persistent or shadow index is maintained.
    """
    candidates: list[tuple[float, Path]] = []
    directories = [world_dir] if world_dir is not None else (
        sorted(WORLD_RECIPES_DIR.iterdir()) if WORLD_RECIPES_DIR.exists() else []
    )
    for directory in directories:
        if not directory.is_dir():
            continue
        for recipe_path in (directory / "recipes").glob("*.json"):
            try:
                candidates.append((recipe_path.stat().st_mtime, recipe_path))
            except OSError:
                continue
    candidates.sort(key=lambda row: (-row[0], str(row[1])))
    manifests: dict[Path, dict[str, Any]] = {}
    for updated_at, recipe_path in candidates:
        recipe = read_json_file(recipe_path)
        if not isinstance(recipe, dict):
            continue
        directory = recipe_path.parent.parent
        if directory not in manifests:
            manifests[directory] = read_json_file(directory / "manifest.json") or {}
        manifest = manifests[directory]
        recipe_meta = recipe.get("recipeMeta") if isinstance(recipe.get("recipeMeta"), dict) else {}
        health = recipe.get("recipeHealth") if isinstance(recipe.get("recipeHealth"), dict) else {}
        health_parents = health.get("parents") if isinstance(health.get("parents"), dict) else {}
        yield {
            "path": recipe_path, "recipe": recipe, "health": health,
            "key": str(recipe_meta.get("recipeKey") or recipe.get("recipeKey") or recipe_path.stem),
            "parentA": str(recipe_meta.get("parentA") or health_parents.get("a") or recipe.get("parentA") or ""),
            "parentB": str(recipe_meta.get("parentB") or health_parents.get("b") or recipe.get("parentB") or ""),
            "worldId": str(manifest.get("worldId") or recipe_meta.get("worldId") or ""),
            "worldName": str(manifest.get("worldName") or recipe_meta.get("worldName") or ""),
            "updatedAt": float(updated_at),
        }


def debug_recipes() -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    for record in _iter_recipe_records():
        recipe = record["recipe"]
        recipes.append({
            "worldId": record["worldId"], "worldName": record["worldName"],
            "createdAt": record["updatedAt"], "a": record["parentA"], "b": record["parentB"],
            "result": recipe.get("name", ""), "key": record["key"], "file": str(record["path"]),
        })
        if len(recipes) == 50:
            break
    return recipes


def debug_recipe_health() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in _iter_recipe_records():
        health = record["health"]
        if not health:
            continue
        rows.append({
            "worldId": record["worldId"], "worldName": record["worldName"], "key": record["key"],
            "ok": bool(health.get("ok")), "status": health.get("status", "unknown"),
            "result": health.get("resultName") or record["recipe"].get("name", ""),
            "runtime": health.get("runtime", {}), "visual": health.get("visual", {}),
            "warnings": health.get("warnings", []), "problems": health.get("problems", []),
            "updatedAt": record["updatedAt"],
        })
        if len(rows) == 100:
            break
    return rows


def debug_latest_recipe_dump(path: str = "") -> dict[str, Any]:
    del path
    record = next(_iter_recipe_records(), None)
    if record is None:
        return {"ok": False, "error": "no_recipe", "message": "No world recipe has been committed yet."}
    recipe_path, recipe = record["path"], record["recipe"]
    runtime = recipe.get("runtimeProgram") if isinstance(recipe.get("runtimeProgram"), dict) else {}
    entities = [row for row in runtime.get("entities") or [] if isinstance(row, dict)]
    visual = recipe.get("visual") if isinstance(recipe.get("visual"), dict) else {}
    debug = recipe.get("debug") if isinstance(recipe.get("debug"), dict) else {}
    health = recipe.get("recipeHealth") if isinstance(recipe.get("recipeHealth"), dict) else {}
    return {
        "ok": True,
        "version": APP_VERSION,
        "file": str(recipe_path),
        "recipeKey": recipe.get("recipeKey", ""),
        "name": recipe.get("name", ""),
        "parents": [recipe.get("parentA", ""), recipe.get("parentB", "")],
        "category": recipe.get("category", ""),
        "runtime": {
            "apiVersion": runtime.get("apiVersion", ""),
            "schema": runtime.get("schema", ""),
            "itemEntityId": runtime.get("itemEntityId", ""),
            "entityCount": len(entities),
            "bindingCount": len(runtime.get("bindings") or []),
            "entities": [{"id": row.get("id"), "kind": row.get("kind"), "visualRole": row.get("visualRole")} for row in entities],
        },
        "visual": {"itemStatus": visual.get("spriteStatus", ""), "item": visual.get("spriteUrl", ""), "entities": [row.get("visual", {}) for row in entities if row.get("kind") != "item_body"]},
        "health": health,
        "contractVersions": recipe.get("contractVersions", {}),
        "quickWarnings": health.get("warnings", []) if isinstance(health, dict) else [],
        "pipelineLog": debug.get("pipelineLog", ""),
    }


def debug_contracts() -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for record in _iter_recipe_records():
        recipe = record["recipe"]
        contract_versions = recipe.get("contractVersions") if isinstance(recipe.get("contractVersions"), dict) else {}
        if contract_versions:
            latest = contract_versions
            break
    return {
        "ok": True,
        "version": APP_VERSION,
        "latestRecipeContractVersions": latest,
        "worldRecipesDir": str(WORLD_RECIPES_DIR),
        "note": "Contract stamps identify generation contracts; this read-only endpoint never migrates recipes.",
    }


def debug_worlds() -> list[dict[str, Any]]:
    worlds: list[dict[str, Any]] = []
    if WORLD_RECIPES_DIR.exists():
        for world_dir in sorted(WORLD_RECIPES_DIR.iterdir()):
            if not world_dir.is_dir():
                continue
            manifest = read_json_file(world_dir / "manifest.json") or {}
            records = list(_iter_recipe_records(world_dir))
            health_counts: dict[str, int] = {}
            for record in records:
                health = record["health"]
                status = str(health.get("status") or "unknown") if isinstance(health, dict) else "unknown"
                health_counts[status] = health_counts.get(status, 0) + 1
            latest_recipe_time = max((record["updatedAt"] for record in records), default=0.0)
            worlds.append({
                "dir": world_dir.name,
                "path": str(world_dir),
                "worldId": manifest.get("worldId", ""),
                "worldName": manifest.get("worldName", ""),
                "recipeCount": len(records),
                "healthCounts": health_counts,
                "updatedAt": latest_recipe_time or manifest.get("updatedAt", None),
            })
    return worlds


def send_bounded_asset_file(handler: Any, path: Path, content_type: str, *, immutable: bool) -> None:
    try:
        stream = path.open("rb")
    except OSError:
        handler.send_error(404)
        return
    # Derive framing from the handle we actually serve, not a prior path stat.
    # Concurrent atomic replacement/unlink cannot switch the selected inode.
    with stream:
        try:
            size = os.fstat(stream.fileno()).st_size
        except OSError:
            handler.send_error(404)
            return
        if size <= 0:
            handler.send_error(404)
            return
        if size > asset_sync_service.MAX_ASSET_RESPONSE_BYTES:
            handler.send_error(413)
            return
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", content_type)
            handler.send_header("Content-Length", str(size))
            if immutable:
                handler.send_header("Cache-Control", "public, max-age=31536000, immutable")
            handler.end_headers()
            remaining = size
            while remaining:
                chunk = stream.read(min(ASSET_STREAM_CHUNK_BYTES, remaining))
                if not chunk:
                    # A concurrently truncated file cannot complete this body.
                    # Never let the next HTTP response fill its missing bytes.
                    handler.close_connection = True
                    return
                handler.wfile.write(chunk)
                remaining -= len(chunk)
        except OSError:
            handler.close_connection = True


def get_asset(handler: Any, path: str) -> None:
    q = parse_qs(urlparse(path).query)
    name = asset_sync_service.safe_asset_file_from_query(
        q,
        sprite_dir=SPRITE_DIR,
        world_recipes_dir=WORLD_RECIPES_DIR,
    )
    p = asset_sync_service.find_asset_file(
        name,
        sprite_dir=SPRITE_DIR,
        world_recipes_dir=WORLD_RECIPES_DIR,
    )
    if p is None:
        handler.send_error(404)
        return
    send_bounded_asset_file(
        handler,
        p,
        asset_sync_service.asset_content_type(p),
        immutable=True,
    )


def sprite_file(handler: Any, path: str) -> None:
    name = unquote(urlparse(path).path.rsplit("/", 1)[-1])
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        handler.send_error(404)
        return
    root = SPRITE_DIR.resolve()
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        handler.send_error(404)
        return
    if candidate.is_file() and candidate.suffix.lower() == ".png":
        send_bounded_asset_file(handler, candidate, "image/png", immutable=False)
        return
    handler.send_error(404)
