import importlib
import sys

from dash import dcc


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
    stores = [child for child in layout.children if isinstance(child, dcc.Store)]
    assert len(stores) >= 3
*** End Patch