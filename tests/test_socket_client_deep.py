"""Dashboard Socket.IO buffer and mock-event tests."""

from dashboard.services.socket_client import LiveEventBuffer, MockEventEmitter, seed_mock_data


def test_live_event_buffer_respects_max_size_and_clear():
    buffer = LiveEventBuffer(max_events=2)
    buffer.append({"id": "1"})
    buffer.append({"id": "2"})
    buffer.append({"id": "3"})
    assert [x["id"] for x in buffer.snapshot()] == ["2", "3"]
    buffer.clear()
    assert buffer.snapshot() == []


def test_seed_mock_data_populates_five_events():
    buffer = LiveEventBuffer()
    seed_mock_data(buffer)
    assert len(buffer.snapshot()) == 5
    assert all(item["event"] == "sighting" for item in buffer.snapshot())
