from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse


class ServerUtilityRoutes:
    """Coarse HTTP route block for local status/debug/static-asset endpoints.

    This intentionally groups one scenario family instead of scattering every helper into
    separate files: server health, multiplayer connect hints, trace UI, sd.cpp debug,
    generated asset serving, and visual test-sprite probes.
    """

    def __init__(
        self,
        *,
        app_version: str,
        root: Path,
        cache_dir: Path,
        sprite_dir: Path,
        world_recipes_dir: Path,
        trace_files: tuple[Path, ...],
        trace_dashboard: Any,
        asset_sync_service: Any,
        health_payload: Callable[[], dict[str, Any]],
        multiplayer_connect_info: Callable[[], dict[str, Any]],
        trace_snapshot: Callable[[], dict[str, Any]],
        trace_snapshot_html: Callable[[], str],
        trace_event: Callable[..., None],
        sdcpp_start: Callable[[], bool],
        sdcpp_debug_snapshot: Callable[..., dict[str, Any]],
        read_json_file: Callable[[Path], dict[str, Any] | None],
        last_combine_failure_payload: Callable[[], dict[str, Any]],
        cleanup_for_shutdown: Callable[[str], None],
        build_image_prompt: Callable[[dict[str, Any], dict[str, Any]], str],
        maybe_generate_sprite: Callable[[dict[str, Any]], dict[str, Any]],
        normalize_asset_prompt: Callable[[dict[str, Any], str, str, int], str],
        generate_visual_asset: Callable[[dict[str, Any], str, str, str, str, int], tuple[str, str, float, dict[str, Any]]],
        asset_negative_prompt: Callable[[str], str],
        alpha_stats: Callable[[Any], dict[str, Any]],
        image_module: Any,
    ) -> None:
        self.app_version = app_version
        self.root = root
        self.cache_dir = cache_dir
        self.sprite_dir = sprite_dir
        self.world_recipes_dir = world_recipes_dir
        self.trace_files = trace_files
        self.trace_dashboard = trace_dashboard
        self.asset_sync_service = asset_sync_service
        self.health_payload = health_payload
        self.multiplayer_connect_info = multiplayer_connect_info
        self.trace_snapshot = trace_snapshot
        self.trace_snapshot_html = trace_snapshot_html
        self.trace_event = trace_event
        self.sdcpp_start = sdcpp_start
        self.sdcpp_debug_snapshot = sdcpp_debug_snapshot
        self.read_json_file = read_json_file
        self.last_combine_failure_payload = last_combine_failure_payload
        self.cleanup_for_shutdown = cleanup_for_shutdown
        self.build_image_prompt = build_image_prompt
        self.maybe_generate_sprite = maybe_generate_sprite
        self.normalize_asset_prompt = normalize_asset_prompt
        self.generate_visual_asset = generate_visual_asset
        self.asset_negative_prompt = asset_negative_prompt
        self.alpha_stats = alpha_stats
        self.Image = image_module

    def handle_get(self, handler: Any, path: str) -> bool:
        request_path = urlparse(path).path

        # path.startswith("/shutdown") intentionally avoided for exact route matching + query support.
        if request_path == "/shutdown":
            self.shutdown(handler)
            return True
        if request_path == "/health":
            handler.json(self.health_payload())
            return True
        if request_path == "/mp_connect.json":
            handler.json({"ok": True, "version": self.app_version, "multiplayer": self.multiplayer_connect_info()})
            return True
        if request_path == "/mp_connect":
            self.mp_connect_html(handler)
            return True
        if request_path == "/trace.json" or request_path == "/debug/trace":
            handler.json(self.trace_snapshot())
            return True
        if request_path == "/trace_clear":
            self.trace_clear(handler)
            return True
        if request_path == "/trace":
            self.write_html(handler, self.trace_snapshot_html())
            return True
        if request_path.startswith("/sdcpp"):
            if request_path == "/sdcpp_start":
                self.sdcpp_start_endpoint(handler)
                return True
            if request_path == "/sdcpp_debug":
                handler.json(self.sdcpp_debug_snapshot(include_log_tail=True))
                return True
            return False
        if request_path in {"/visual_doctor.json", "/zimage_doctor.json"}:
            handler.json(self.visual_doctor_payload(path))
            return True
        if request_path in {"/visual_doctor", "/zimage_doctor"}:
            self.visual_doctor_html(handler, path)
            return True
        if request_path == "/debug/generate_test_sprite":
            self.generate_test_sprite(handler, path)
            return True
        if request_path == "/debug/last_combine_failure":
            handler.json(self.last_combine_failure_payload())
            return True
        if request_path == "/debug/recipe_health":
            handler.json({"recipeStorage": "authoritative_world_recipe_files", "health": self.debug_recipe_health()[:100]})
            return True
        if request_path == "/debug/contracts":
            handler.json(self.debug_contracts())
            return True
        if request_path in {"/debug/latest_recipe", "/debug/recipe_dump"}:
            handler.json(self.debug_latest_recipe_dump(path))
            return True
        if request_path == "/debug/recipes":
            handler.json({"recipeStorage": "authoritative_world_recipe_files", "recipes": self.debug_recipes()[:50]})
            return True
        if request_path == "/debug/worlds":
            handler.json({"worldRecipesDir": str(self.world_recipes_dir), "worlds": self.debug_worlds()})
            return True
        if request_path == "/get_asset":
            self.get_asset(handler, path)
            return True
        if request_path.startswith("/sprite/"):
            self.sprite_file(handler, path)
            return True
        return False

    def shutdown(self, handler: Any) -> None:
        # Local GUI uses this to cleanly replace stale helper instances left behind
        # when a console/window was closed incorrectly. Keep it before /health.
        handler.json({
            "ok": True,
            "version": self.app_version,
            "serverRoot": str(self.root),
            "pid": os.getpid(),
            "message": "shutdown scheduled",
        })

        def _shutdown_later() -> None:
            time.sleep(0.15)
            try:
                self.cleanup_for_shutdown("http_shutdown")
            finally:
                try:
                    handler.server.shutdown()
                except Exception:
                    pass

        threading.Thread(target=_shutdown_later, daemon=True).start()

    def mp_connect_html(self, handler: Any) -> None:
        body = self.trace_dashboard.render_mp_connect_html(self.multiplayer_connect_info())
        self.write_html(handler, body)

    def write_html(self, handler: Any, html: str) -> None:
        body = html.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def trace_clear(self, handler: Any) -> None:
        cleared: list[str] = []
        for p in self.trace_files:
            try:
                Path(p).write_text("", encoding="utf-8")
                cleared.append(str(p))
            except Exception:
                pass
        handler.json({"ok": True, "version": self.app_version, "cleared": cleared})

    def sdcpp_start_endpoint(self, handler: Any) -> None:
        self.trace_event("step", "SDCPP:startup", "manual /sdcpp_start requested", {})
        ok = self.sdcpp_start()
        snap = self.sdcpp_debug_snapshot(include_log_tail=not ok)
        snap["ok"] = bool(ok)
        handler.json(snap)

    def _file_check(self, value: Any) -> dict[str, Any]:
        text = str(value or "").strip()
        if not text:
            return {"path": "", "configured": False, "exists": False, "kind": "missing"}
        try:
            p = Path(text)
            return {
                "path": text,
                "configured": True,
                "exists": p.exists(),
                "isFile": p.is_file(),
                "isDir": p.is_dir(),
                "bytes": p.stat().st_size if p.exists() and p.is_file() else None,
            }
        except Exception as e:
            return {"path": text, "configured": True, "exists": False, "error": repr(e)}

    def _dir_writable_check(self, path: Path) -> dict[str, Any]:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".infini_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return {"path": str(path), "exists": True, "writable": True}
        except Exception as e:
            return {"path": str(path), "exists": path.exists(), "writable": False, "error": repr(e)}

    def _visual_probe_payload(self, role: str = "item", prompt: str = "") -> dict[str, Any]:
        role = (role or "item").lower()
        role = role if role in {"item", "projectile", "impact", "child", "field"} else "item"
        test_id = f"doctor_{role}_{int(time.time())}"
        dummy = {
            "id": test_id,
            "name": "Z-Image Doctor Blade",
            "tooltip": "Doctor probe sprite asset",
            "concept": {"fantasy": "a crystal slime blade with starlight circuitry"},
            "visual": {"palette": ["cyan", "white", "violet"], "preferredCanvasSize": 32, "requiredAnchors": ["crystal blade", "slime edge", "star circuit"]},
            "attack": {"enabled": True, "projectileShape": "tiny crescent crystal blade", "projectileTrail": "violet starlight dots", "projectileImpact": "small cyan star crack"},
            "tags": ["doctor", "zimage", "sprite", "magic"],
            "debug": {},
        }
        canvas = 32 if role == "item" else 48 if role == "projectile" else 32
        if role == "item":
            dummy["visual"]["imagePrompt"] = prompt or self.build_image_prompt(dummy, dummy["visual"])
            before = time.time()
            dummy = self.maybe_generate_sprite(dummy)
            visual = dummy.get("visual") if isinstance(dummy.get("visual"), dict) else {}
            path = str(visual.get("spritePath") or "")
            alpha = {}
            if path and self.Image is not None and Path(path).exists():
                alpha = self.alpha_stats(self.Image.open(path).convert("RGBA"))
            return {"ok": bool(path and Path(path).exists()), "role": role, "ms": int((time.time() - before) * 1000), "visual": visual, "alpha": alpha, "debug": dummy.get("debug")}
        prompt = prompt or self.normalize_asset_prompt(dummy, role, "", canvas)
        before = time.time()
        sprite_path, url, score, status = self.generate_visual_asset(dummy, role, prompt, self.asset_negative_prompt(role), test_id, canvas)
        alpha = {}
        if sprite_path and self.Image is not None and Path(sprite_path).exists():
            alpha = self.alpha_stats(self.Image.open(sprite_path).convert("RGBA"))
        return {"ok": bool(sprite_path and Path(sprite_path).exists()), "role": role, "ms": int((time.time() - before) * 1000), "status": status, "path": sprite_path, "url": url, "score": score, "alpha": alpha, "debug": dummy.get("debug")}

    def visual_doctor_payload(self, path: str) -> dict[str, Any]:
        q = parse_qs(urlparse(path).query)
        probe = str(q.get("probe", ["0"])[0]).strip().lower() in {"1", "true", "yes", "on"}
        role = q.get("role", ["item"])[0]
        health = self.health_payload()
        sdcpp = self.sdcpp_debug_snapshot(include_log_tail=not probe)
        backend = str(health.get("imageBackend") or "").lower()
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
        add("sprite_dir_writable", self._dir_writable_check(self.sprite_dir).get("writable", False), "error", "Sprite cache must be writable.", check=self._dir_writable_check(self.sprite_dir))
        add("cache_dir_writable", self._dir_writable_check(self.cache_dir).get("writable", False), "error", "Cache dir must be writable.", check=self._dir_writable_check(self.cache_dir))
        add("sdcpp_configured", bool(sdcpp.get("serverConfigured")), "error" if not sdcpp.get("serverConfigured") else "ok", "sd.cpp server exe/model must be configured.")
        add("sdcpp_alive", bool(sdcpp.get("serverAlive")), "warn" if not sdcpp.get("serverAlive") else "ok", "sd.cpp server should be alive before crafting; /sdcpp_start can start it.")
        for key in ["serverExe", "model", "vae", "llm"]:
            fc = self._file_check(sdcpp.get(key))
            add(f"sdcpp_{key}", bool(fc.get("exists") if fc.get("configured") else key not in {"vae", "llm"}), "error" if key in {"serverExe", "model"} else "warn", f"sd.cpp {key} path check.", check=fc)
        if sdcpp.get("loraFile"):
            add("sdcpp_lora_file", bool(self._file_check(sdcpp.get("loraFile")).get("exists")), "warn", "Optional LoRA file path check.", check=self._file_check(sdcpp.get("loraFile")))

        probe_payload = None
        if probe:
            try:
                probe_payload = self._visual_probe_payload(role=role, prompt=q.get("prompt", [""])[0])
                add("live_sprite_probe", bool(probe_payload.get("ok")), "error" if not probe_payload.get("ok") else "ok", "Live Z-Image -> postprocess -> PNG probe.", probe=probe_payload)
            except Exception as e:
                probe_payload = {"ok": False, "error": repr(e)}
                add("live_sprite_probe", False, "error", "Live sprite probe crashed.", probe=probe_payload)

        errors = [c for c in checks if not c.get("ok") and c.get("level") == "error"]
        warnings = [c for c in checks if not c.get("ok") and c.get("level") == "warn"]
        return {
            "ok": not errors,
            "version": self.app_version,
            "summary": "ready" if not errors and not warnings else "ready_with_warnings" if not errors else "not_ready",
            "checks": checks,
            "probe": probe_payload,
            "health": {k: health.get(k) for k in ["imageBackend", "visualRequireItemSprite", "visualRequireZImageBackend", "zImagePromptContract", "zImagePositiveOnly", "bgRemoveMode", "bgColor", "spriteRetries", "visualAssetMode"]},
            "sdcpp": sdcpp,
            "links": {"health": "/health", "sdcppStart": "/sdcpp_start", "sdcppDebug": "/sdcpp_debug", "trace": "/trace", "probeItem": "/visual_doctor.json?probe=1&role=item"},
        }

    def visual_doctor_html(self, handler: Any, path: str) -> None:
        payload = self.visual_doctor_payload(path)
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
        self.write_html(handler, html)

    def generate_test_sprite(self, handler: Any, path: str) -> None:
        q = parse_qs(urlparse(path).query)
        role = (q.get("role", ["projectile"])[0] or "projectile").lower()
        role = role if role in {"item", "projectile", "impact", "child", "field"} else "projectile"
        test_id = f"debug_{role}_{int(time.time())}"
        dummy = {
            "id": test_id,
            "name": q.get("name", ["Debug Pixel Sprite"])[0],
            "tooltip": "Debug generated sprite asset",
            "concept": {"fantasy": q.get("fantasy", ["a tiny magic sword made of slime and starlight"])[0]},
            "visual": {"palette": ["cyan", "white", "violet"], "preferredCanvasSize": 32, "requiredAnchors": ["magic sword", "slime", "starlight"]},
            "attack": {"enabled": True, "projectileShape": "tiny crescent sword comet", "projectileTrail": "blue slime sparkles", "projectileImpact": "small star pop"},
            "tags": ["debug", "sprite", "magic"],
            "debug": {},
        }
        canvas = int(q.get("canvas", ["32"])[0] or "32")
        prompt = q.get("prompt", [""])[0]
        if role == "item":
            dummy["visual"]["imagePrompt"] = prompt or self.build_image_prompt(dummy, dummy["visual"])
            dummy = self.maybe_generate_sprite(dummy)
            handler.json({"ok": True, "role": role, "version": self.app_version, "visual": dummy.get("visual"), "debug": dummy.get("debug")})
            return
        prompt = prompt or self.normalize_asset_prompt(dummy, role, "", canvas)
        sprite_path, url, score, status = self.generate_visual_asset(dummy, role, prompt, self.asset_negative_prompt(role), test_id, canvas)
        stats = {}
        if sprite_path and self.Image is not None and Path(sprite_path).exists():
            stats = self.alpha_stats(self.Image.open(sprite_path).convert("RGBA"))
        handler.json({
            "ok": True,
            "role": role,
            "version": self.app_version,
            "status": status,
            "path": sprite_path,
            "url": url,
            "score": score,
            "alpha": stats,
            "debug": dummy.get("debug"),
        })

    def _world_recipe_records(self, world_dir: Path) -> list[dict[str, Any]]:
        """Build debug-only derived rows from authoritative ``recipes/*.json`` files."""
        manifest = self.read_json_file(world_dir / "manifest.json") or {}
        recipes_dir = world_dir / "recipes"
        if not recipes_dir.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for recipe_path in recipes_dir.glob("*.json"):
            recipe = self.read_json_file(recipe_path)
            if not isinstance(recipe, dict):
                continue
            recipe_meta = recipe.get("recipeMeta") if isinstance(recipe.get("recipeMeta"), dict) else {}
            health = recipe.get("recipeHealth") if isinstance(recipe.get("recipeHealth"), dict) else {}
            health_parents = health.get("parents") if isinstance(health.get("parents"), dict) else {}
            try:
                updated_at = recipe_path.stat().st_mtime
            except OSError:
                updated_at = 0.0
            records.append({
                "path": recipe_path,
                "recipe": recipe,
                "health": health,
                "key": str(recipe_meta.get("recipeKey") or recipe.get("recipeKey") or recipe_path.stem),
                "parentA": str(recipe_meta.get("parentA") or health_parents.get("a") or recipe.get("parentA") or ""),
                "parentB": str(recipe_meta.get("parentB") or health_parents.get("b") or recipe.get("parentB") or ""),
                "worldId": str(manifest.get("worldId") or recipe_meta.get("worldId") or ""),
                "worldName": str(manifest.get("worldName") or recipe_meta.get("worldName") or ""),
                "updatedAt": float(updated_at),
            })
        records.sort(key=lambda row: (row["updatedAt"], row["key"]))
        return records

    def debug_recipes(self) -> list[dict[str, Any]]:
        recipes: list[dict[str, Any]] = []
        if self.world_recipes_dir.exists():
            for world_dir in sorted(self.world_recipes_dir.iterdir()):
                if not world_dir.is_dir():
                    continue
                for record in self._world_recipe_records(world_dir)[-50:]:
                    recipe = record["recipe"]
                    recipes.append({
                        "worldId": record["worldId"],
                        "worldName": record["worldName"],
                        "createdAt": record["updatedAt"],
                        "a": record["parentA"],
                        "b": record["parentB"],
                        "result": recipe.get("name", ""),
                        "key": record["key"],
                        "file": str(record["path"]),
                    })
        recipes.sort(key=lambda row: row.get("createdAt") or 0, reverse=True)
        return recipes

    def debug_recipe_health(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self.world_recipes_dir.exists():
            for world_dir in sorted(self.world_recipes_dir.iterdir()):
                if not world_dir.is_dir():
                    continue
                for record in self._world_recipe_records(world_dir):
                    health = record["health"]
                    if not isinstance(health, dict) or not health:
                        continue
                    rows.append({
                        "worldId": record["worldId"],
                        "worldName": record["worldName"],
                        "key": record["key"],
                        "ok": bool(health.get("ok")),
                        "status": health.get("status", "unknown"),
                        "result": health.get("resultName") or record["recipe"].get("name", ""),
                        "runtime": health.get("runtime", {}),
                        "visual": health.get("visual", {}),
                        "warnings": health.get("warnings", []),
                        "problems": health.get("problems", []),
                        "updatedAt": record["updatedAt"],
                    })
        rows.sort(key=lambda row: row.get("updatedAt") or 0, reverse=True)
        return rows

    def _latest_recipe_file(self) -> Path | None:
        best_path: Path | None = None
        best_time = -1.0
        if self.world_recipes_dir.exists():
            for world_dir in sorted(self.world_recipes_dir.iterdir()):
                if not world_dir.is_dir():
                    continue
                for record in self._world_recipe_records(world_dir):
                    if record["updatedAt"] > best_time:
                        best_time = record["updatedAt"]
                        best_path = record["path"]
        return best_path

    def debug_latest_recipe_dump(self, path: str = "") -> dict[str, Any]:
        recipe_path = self._latest_recipe_file()
        if recipe_path is None:
            return {"ok": False, "error": "no_recipe", "message": "No world recipe has been committed yet."}
        recipe = self.read_json_file(recipe_path) or {}
        attack = recipe.get("attack") if isinstance(recipe.get("attack"), dict) else {}
        gameplay = recipe.get("gameplay") if isinstance(recipe.get("gameplay"), dict) else {}
        visual = recipe.get("visual") if isinstance(recipe.get("visual"), dict) else {}
        debug = recipe.get("debug") if isinstance(recipe.get("debug"), dict) else {}
        health = recipe.get("recipeHealth") if isinstance(recipe.get("recipeHealth"), dict) else {}
        recipe_meta = recipe.get("recipeMeta") if isinstance(recipe.get("recipeMeta"), dict) else {}
        health_parents = health.get("parents") if isinstance(health.get("parents"), dict) else {}
        return {
            "ok": True,
            "version": self.app_version,
            "file": str(recipe_path),
            "recipeKey": recipe_meta.get("recipeKey") or recipe.get("recipeKey", ""),
            "name": recipe.get("name", ""),
            "parents": [
                recipe_meta.get("parentA") or health_parents.get("a") or recipe.get("parentA", ""),
                recipe_meta.get("parentB") or health_parents.get("b") or recipe.get("parentB", ""),
            ],
            "category": recipe.get("category", ""),
            "runtime": {
                "resultKind": (recipe.get("runtimePlan") or {}).get("resultKind") if isinstance(recipe.get("runtimePlan"), dict) else gameplay.get("runtimeOutputKind", ""),
                "delivery": attack.get("delivery", ""),
                "runtimeFamily": attack.get("runtimeFamily", ""),
                "movement": attack.get("movement", ""),
                "damagePath": attack.get("damagePath", ""),
                "hasRealChildren": (health.get("runtime") or {}).get("hasRealChildren") if isinstance(health.get("runtime"), dict) else False,
                "pureVfx": (health.get("runtime") or {}).get("pureVfx") if isinstance(health.get("runtime"), dict) else False,
            },
            "affordance": recipe.get("runtimeAffordance", {}),
            "visual": {
                "itemStatus": visual.get("spriteStatus", ""),
                "item": visual.get("spriteUrl", ""),
                "projectileStatus": attack.get("projectileSpriteStatus", ""),
                "projectile": attack.get("projectileSpriteUrl", ""),
                "impactStatus": attack.get("impactSpriteStatus", ""),
                "impact": attack.get("impactSpriteUrl", ""),
                "assetFiles": recipe_meta.get("assetFiles", []),
            },
            "health": health,
            "contractVersions": recipe.get("contractVersions", {}),
            "quickWarnings": (health.get("warnings") or []) if isinstance(health, dict) else [],
            "pipelineLog": debug.get("pipelineLog", ""),
        }

    def debug_contracts(self) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        candidates: list[dict[str, Any]] = []
        if self.world_recipes_dir.exists():
            for world_dir in sorted(self.world_recipes_dir.iterdir()):
                if world_dir.is_dir():
                    candidates.extend(self._world_recipe_records(world_dir))
        for record in sorted(candidates, key=lambda row: row["updatedAt"], reverse=True):
            recipe = record["recipe"]
            contract_versions = recipe.get("contractVersions") if isinstance(recipe.get("contractVersions"), dict) else {}
            if contract_versions:
                latest = contract_versions
                break
        return {
            "ok": True,
            "version": self.app_version,
            "latestRecipeContractVersions": latest,
            "worldRecipesDir": str(self.world_recipes_dir),
            "note": "Contract stamps are diagnostic only; they do not migrate or block recipes.",
        }

    def debug_worlds(self) -> list[dict[str, Any]]:
        worlds: list[dict[str, Any]] = []
        if self.world_recipes_dir.exists():
            for world_dir in sorted(self.world_recipes_dir.iterdir()):
                if not world_dir.is_dir():
                    continue
                manifest = self.read_json_file(world_dir / "manifest.json") or {}
                records = self._world_recipe_records(world_dir)
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

    def get_asset(self, handler: Any, path: str) -> None:
        q = parse_qs(urlparse(path).query)
        name = self.asset_sync_service.safe_asset_file_from_query(
            q,
            sprite_dir=self.sprite_dir,
            world_recipes_dir=self.world_recipes_dir,
        )
        p = self.asset_sync_service.find_asset_file(
            name,
            sprite_dir=self.sprite_dir,
            world_recipes_dir=self.world_recipes_dir,
        )
        if p is None:
            handler.send_error(404)
            return
        handler.send_response(200)
        handler.send_header("Content-Type", self.asset_sync_service.asset_content_type(p))
        handler.send_header("Content-Length", str(p.stat().st_size))
        handler.send_header("Cache-Control", "public, max-age=31536000, immutable")
        handler.end_headers()
        handler.wfile.write(p.read_bytes())

    def sprite_file(self, handler: Any, path: str) -> None:
        name = unquote(urlparse(path).path.rsplit("/", 1)[-1])
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            handler.send_error(404)
            return
        root = self.sprite_dir.resolve()
        candidate = (root / name).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            handler.send_error(404)
            return
        if candidate.is_file() and candidate.suffix.lower() == ".png":
            handler.send_response(200)
            handler.send_header("Content-Type", "image/png")
            handler.send_header("Content-Length", str(candidate.stat().st_size))
            handler.end_headers()
            handler.wfile.write(candidate.read_bytes())
            return
        handler.send_error(404)
