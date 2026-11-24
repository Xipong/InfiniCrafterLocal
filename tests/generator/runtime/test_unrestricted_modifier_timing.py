"""Shared timing vocabulary must not silently acquire a call-specific default."""
import infini_local.core.runtime_authoring.registry_views as registry_views


def test_shared_window_type_never_inherits_a_use_specific_default(monkeypatch):
    import infini_local.core.runtime_authoring.capability_registry as registry
    cap = registry.CAPABILITY_REGISTRY["homing"]
    reordered = {key: value for key, value in registry.CAPABILITY_REGISTRY.items() if key != cap.name}
    reordered[cap.name] = cap
    monkeypatch.setattr(registry, "CAPABILITY_REGISTRY", reordered)
    shared = registry_views.shared_parameter_schemas()["motionWindow"]
    assert "default" not in shared and "x-infini-neutral" not in shared
