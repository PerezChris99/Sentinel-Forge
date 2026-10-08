"""Pure dashboard rendering and callback tests."""

import dashboard.app as dashboard


def test_kpi_cards_and_heatmap_handle_missing_data():
    cards = dashboard._build_kpi_cards({})
    assert len(cards) == 4
    fig = dashboard._build_heatmap({})
    assert len(fig.data) == 1


def test_person_summary_handles_missing_and_present_person():
    assert "Select a person" in str(dashboard._build_person_summary(None))
    summary = dashboard._build_person_summary({"name": "Alice", "role": "Security", "consent_given": True})
    assert "Alice" in str(summary)


def test_alerts_render_only_high_risk_events():
    assert "No high-risk" in str(dashboard.update_alerts([{"flag_level": 1}]))
    rendered = dashboard.update_alerts([
        {"flag_level": 2, "timestamp": "now", "person_id": "p1", "camera_id": "c1"},
        {"flag_level": 3, "timestamp": "later", "person_id": "p2", "camera_id": "c2"},
    ])
    assert len(rendered) == 2


def test_person_dropdown_selects_valid_or_first_person():
    options, selected, summary = dashboard.update_person_dropdown(
        [{"id": "p1", "name": "Alice", "role": "Security"}],
        "missing",
    )
    assert options[0]["value"] == "p1"
    assert selected == "p1"
    assert "Alice" in str(summary)


def test_person_timeline_returns_empty_figure_without_data(monkeypatch):
    monkeypatch.setattr(dashboard.API_CLIENT, "fetch_person_timeline", lambda _: [])
    fig = dashboard.update_person_timeline("p1", 0)
    assert len(fig.data) == 0


def test_unknown_gallery_handles_empty_and_populated_payloads():
    assert "No unknown" in str(dashboard.update_unknown_gallery({"items": []}))
    cards = dashboard.update_unknown_gallery({"items": [{"cluster_id": "u1", "flag_level": 2, "last_seen": "now", "thumbnail_b64": "data:image/jpeg;base64,x"}]})
    assert len(cards) == 1
