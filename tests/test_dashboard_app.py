import importlib
import sys


def test_dashboard_layout_contains_expected_components(monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_USE_MOCKS", "1")
    module_name = "dashboard.app"
    if module_name in sys.modules:
        importlib.reload(sys.modules[module_name])
    else:
        importlib.import_module(module_name)

    from dashboard import app as dash_app  # type: ignore

    layout = dash_app.APP.layout
    assert layout is not None

    # Dash may wrap the layout in a component tree; inspect the declared stores
    # from the layout's top-level children without relying on an implementation
    # detail from the previous dashboard.
    children = getattr(layout, "children", []) or []
    stores = [child for child in children if getattr(child, "id", None) in {
        "overview-stats-store", "persons-store", "unknowns-store", "live-events-store"
    }]
    assert len(stores) >= 3
