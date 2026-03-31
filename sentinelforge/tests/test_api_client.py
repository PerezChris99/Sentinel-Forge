from dashboard.services.api_client import MockSentinelForgeAPI


def test_mock_api_provides_person_data():
    api = MockSentinelForgeAPI()
    persons = api.fetch_persons()
    assert persons, "mock should return sample persons"
    assert set(persons[0]).issuperset({"id", "name", "role"})
    overview = api.fetch_overview_stats()
    assert "active_cameras" in overview
