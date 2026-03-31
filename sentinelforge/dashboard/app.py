"""Dash application entry-point for the SentinelForge dashboard."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html

from .services.api_client import BaseSentinelForgeAPI, build_api_client
from .services.config import DashboardConfig
from .services.socket_client import (
    LiveEventBuffer,
    LiveEventStream,
    MockEventEmitter,
    seed_mock_data,
)

CONFIG = DashboardConfig()
API_CLIENT: BaseSentinelForgeAPI = build_api_client(CONFIG)
EVENT_BUFFER = LiveEventBuffer(max_events=CONFIG.max_events_cached)

if CONFIG.use_mocks:
    seed_mock_data(EVENT_BUFFER)
    MockEventEmitter(buffer=EVENT_BUFFER).start()
elif CONFIG.enable_socket_stream and CONFIG.socket_url:
    LiveEventStream(CONFIG, EVENT_BUFFER).start()

external_stylesheets = [dbc.themes.DARKLY, "/assets/custom.css"]
APP: Dash = Dash(
    __name__,
    external_stylesheets=external_stylesheets,
    suppress_callback_exceptions=True,
    title="SentinelForge",
)
SERVER = APP.server


def _build_overview_tab() -> dbc.Container:
    return dbc.Container(
        [
            dbc.Row(id="kpi-cards", className="g-3"),
            dbc.Row(
                [
                    dbc.Col(dcc.Graph(id="heatmap"), md=7),
                    dbc.Col(
                        [
                            html.H5("Live Alerts"),
                            html.Div(id="alerts-ticker", className="alert-ticker"),
                        ],
                        md=5,
                    ),
                ],
                className="g-3 mt-1",
            ),
        ],
        fluid=True,
    )


def _build_persons_tab() -> dbc.Container:
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Dropdown(
                            id="person-dropdown",
                            placeholder="Select a person",
                            clearable=True,
                        ),
                        md=4,
                    ),
                    dbc.Col(html.Div(id="person-summary"), md=8),
                ],
                className="g-3",
            ),
            dbc.Row(
                [
                    dbc.Col(dcc.Graph(id="person-timeline"), width=12),
                ]
            ),
        ],
        fluid=True,
    )


def _build_unknowns_tab() -> dbc.Container:
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(dcc.Slider(id="unknown-flag-filter", min=0, max=3, value=0, marks={i: f"L{i}" for i in range(4)}), md=8),
                    dbc.Col(dbc.Button("Refresh", id="unknown-refresh", color="secondary"), md=4),
                ],
                className="g-2",
            ),
            html.Div(id="unknown-gallery", className="mt-3"),
        ],
        fluid=True,
    )


def _build_reports_tab() -> dbc.Container:
    csv_url = f"{CONFIG.api_url.rstrip('/')}/api/reports/daily.csv"
    pdf_url = f"{CONFIG.api_url.rstrip('/')}/api/reports/daily.pdf"
    return dbc.Container(
        [
            html.P("Generate artefacts for briefings or exports."),
            dbc.ButtonGroup(
                [
                    dbc.Button("Download CSV", href=csv_url, target="_blank", color="success"),
                    dbc.Button("Download PDF", href=pdf_url, target="_blank", color="info"),
                ]
            ),
            html.Hr(),
            html.H4("ALFIE Insights"),
            html.Div(id="alfie-placeholder", children="Awaiting ALFIE summaries."),
        ],
        fluid=True,
    )


@APP.callback(Output("overview-stats-store", "data"), Input("interval-overview", "n_intervals"))
def refresh_overview(_: int) -> Dict[str, Any]:
    return API_CLIENT.fetch_overview_stats()


@APP.callback(Output("persons-store", "data"), Input("interval-persons", "n_intervals"))
def refresh_persons(_: int) -> List[Dict[str, Any]]:
    return API_CLIENT.fetch_persons()


@APP.callback(
    Output("unknowns-store", "data"),
    Input("interval-unknowns", "n_intervals"),
    Input("unknown-flag-filter", "value"),
    Input("unknown-refresh", "n_clicks"),
)
def refresh_unknowns(_: int, flag_level: int, __: Optional[int]) -> Dict[str, Any]:
    return API_CLIENT.fetch_unknown_clusters(flag_level=flag_level)


@APP.callback(Output("live-events-store", "data"), Input("interval-events", "n_intervals"))
def refresh_events(_: int) -> List[Dict[str, Any]]:
    return EVENT_BUFFER.snapshot()


@APP.callback(
    Output("kpi-cards", "children"),
    Output("heatmap", "figure"),
    Input("overview-stats-store", "data"),
)
def update_overview(stats: Optional[Dict[str, Any]]) -> Tuple[List[dbc.Col], go.Figure]:
    stats = stats or {}
    cards = _build_kpi_cards(stats)
    figure = _build_heatmap(stats)
    return cards, figure


@APP.callback(Output("alerts-ticker", "children"), Input("live-events-store", "data"))
def update_alerts(events: Optional[List[Dict[str, Any]]]) -> List[html.Div]:
    events = events or []
    flagged = [e for e in events if int(e.get("flag_level", 0)) >= 2]
    if not flagged:
        return [html.Div("No high-risk alerts in queue.")]
    items = []
    for event in reversed(flagged[-5:]):
        timestamp = event.get("timestamp", "")
        person = event.get("person_id", "unknown")
        camera = event.get("camera_id", "cam-??")
        items.append(
            html.Div(
                [
                    html.Strong(f"{timestamp} | {person}"),
                    html.Span(f" @ {camera}", className="ms-2"),
                ],
                className="alert alert-danger py-1 my-1",
            )
        )
    return items


@APP.callback(
    Output("person-dropdown", "options"),
    Output("person-dropdown", "value"),
    Output("person-summary", "children"),
    Input("persons-store", "data"),
    State("person-dropdown", "value"),
)
def update_person_dropdown(persons: Optional[List[Dict[str, Any]]], current_value: Optional[str]):
    persons = persons or []
    options = [
        {"label": f"{p.get('name')} ({p.get('role')})", "value": p.get("id")}
        for p in persons
    ]
    selected = current_value if any(opt["value"] == current_value for opt in options) else None
    if selected is None and options:
        selected = options[0]["value"]
    summary = _build_person_summary(next((p for p in persons if p.get("id") == selected), None))
    return options, selected, summary


@APP.callback(
    Output("person-timeline", "figure"),
    Input("person-dropdown", "value"),
    Input("interval-person-timeline", "n_intervals"),
)
def update_person_timeline(person_id: Optional[str], _: int) -> go.Figure:
    data = API_CLIENT.fetch_person_timeline(person_id)
    if not data:
        return go.Figure()
    timestamps = [entry.get("timestamp") for entry in data]
    camera_ids = [entry.get("camera_id") for entry in data]
    confidence = [entry.get("confidence", 0.0) for entry in data]
    figure = go.Figure(
        data=go.Scatter(x=timestamps, y=camera_ids, mode="markers+lines", marker={"size": 12, "color": confidence}),
    )
    figure.update_layout(
        title=f"Timeline for {person_id}",
        xaxis_title="Timestamp",
        yaxis_title="Camera",
        template="plotly_dark",
    )
    return figure


@APP.callback(
    Output("unknown-gallery", "children"),
    Input("unknowns-store", "data"),
)
def update_unknown_gallery(payload: Optional[Dict[str, Any]]) -> List[dbc.Col]:
    payload = payload or {"items": []}
    items = payload.get("items", [])
    if not items:
        return [html.Div("No unknown clusters detected.")]
    cards = []
    for item in items:
        cards.append(
            dbc.Col(
                dbc.Card(
                    [
                        html.Img(src=item.get("thumbnail_b64", ""), className="card-img-top"),
                        dbc.CardBody(
                            [
                                html.H6(item.get("cluster_id"), className="card-title"),
                                html.P(f"Flag {item.get('flag_level', 0)}", className="card-text"),
                                html.Small(item.get("last_seen")),
                            ]
                        ),
                    ]
                ),
                md=3,
            )
        )
    return cards


def _build_kpi_cards(stats: Dict[str, Any]) -> List[dbc.Col]:
    definitions = [
        ("Active Cameras", stats.get("active_cameras", 0), "primary"),
        ("Last Hour Sightings", stats.get("sightings_last_hour", 0), "info"),
        ("Unknowns Pending", stats.get("unknowns_pending", 0), "warning"),
        ("Flagged Events", stats.get("flagged_events", 0), "danger"),
    ]
    cards = []
    for label, value, color in definitions:
        cards.append(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(label),
                        dbc.CardBody(html.H2(value, className="card-title")),
                    ],
                    color=color,
                    inverse=True,
                )
            )
        )
    return cards


def _build_heatmap(stats: Dict[str, Any]) -> go.Figure:
    matrix = stats.get("heatmap") or [[0] * 7 for _ in range(4)]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cameras = [f"Cam {idx+1}" for idx in range(len(matrix))]
    figure = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=days,
            y=cameras,
            colorscale="Viridis",
        )
    )
    figure.update_layout(title="Activity Heatmap", template="plotly_dark", height=380)
    return figure


def _build_person_summary(person: Optional[Dict[str, Any]]) -> html.Div:
    if not person:
        return html.Div("Select a person to view stats")
    return html.Div(
        [
            html.H4(person.get("name")),
            html.P(f"Role: {person.get('role', 'Unknown')}", className="mb-1"),
            html.P(f"Consent: {'Yes' if person.get('consent_given') else 'No'}"),
            html.Small(f"Last seen: {person.get('last_seen', 'n/a')}")
        ]
    )


APP.layout = dbc.Container(
    [
        dcc.Store(id="overview-stats-store"),
        dcc.Store(id="persons-store"),
        dcc.Store(id="unknowns-store"),
        dcc.Store(id="live-events-store"),
        dcc.Interval(id="interval-overview", interval=15_000, n_intervals=0),
        dcc.Interval(id="interval-persons", interval=60_000, n_intervals=0),
        dcc.Interval(id="interval-unknowns", interval=60_000, n_intervals=0),
        dcc.Interval(id="interval-events", interval=5_000, n_intervals=0),
        dcc.Interval(id="interval-person-timeline", interval=30_000, n_intervals=0),
        html.H1("SentinelForge Command Console", className="mb-4"),
        dbc.Tabs(
            [
                dbc.Tab(label="Overview", tab_id="overview", children=_build_overview_tab()),
                dbc.Tab(label="Persons", tab_id="persons", children=_build_persons_tab()),
                dbc.Tab(label="Unknowns", tab_id="unknowns", children=_build_unknowns_tab()),
                dbc.Tab(label="Reports", tab_id="reports", children=_build_reports_tab()),
            ],
            id="tabs",
            active_tab="overview",
        ),
    ],
    fluid=True,
)


if __name__ == "__main__":  # pragma: no cover - manual run helper
    APP.run_server(debug=True)
