import pytest
import sys
import os
import logging
import json
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch, call, ANY
import pytz
from contextlib import contextmanager # Added for the new fixture

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Imports from the module being tested and the data model
from src.google_calendar import GoogleCalendarExporter, service_account
from src.data_models import BinCollection, FetcherResult

# Sample test data with a fixed year for consistency
TEST_ADDRESS = "Test Address"
TEST_YEAR = 2024
EXPECTED_SCOPES = ['https://www.googleapis.com/auth/calendar']

TEST_COLLECTIONS = [
    BinCollection("10 Thursday", "April", "Household", "green", "/link1"),
    BinCollection("17 Thursday", "April", "Recycling", "dark blue", "/link2"),
    BinCollection("24 Thursday", "April", "Garden", "brown", "/link3")
]
TEST_FETCHER_RESULT = FetcherResult(address_text=TEST_ADDRESS, collections=TEST_COLLECTIONS)

APRIL_10_DATE = date(TEST_YEAR, 4, 10)
APRIL_17_DATE = date(TEST_YEAR, 4, 17)
APRIL_24_DATE = date(TEST_YEAR, 4, 24)


@pytest.fixture(autouse=True)
def isolated_google_env_vars(monkeypatch):
    """
    Ensures that Google Calendar related environment variables are cleared
    before each test, preventing interference from external .env files or
    the actual environment. Tests should explicitly set these if needed.
    """
    monkeypatch.delenv("BINS_GOOGLE_CALENDAR_ID", raising=False)
    monkeypatch.delenv("BINS_GOOGLE_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("BINS_GOOGLE_CREDENTIALS", raising=False)

@pytest.fixture
def mock_google_creds_object():
    """Returns a MagicMock for a credentials object."""
    return MagicMock(spec=service_account.Credentials)

@pytest.fixture
def mock_service(mocker):
    """Fixture to create a mock Google Calendar service."""
    mock_service_instance = MagicMock()
    mock_events_list = MagicMock()
    mock_events_list.execute.return_value = {'items': []}
    mock_events_insert = MagicMock()
    mock_events_insert.execute.return_value = {'id': 'new_event_id', 'htmlLink': 'http://example.com'}
    mock_service_instance.events.return_value.list.return_value = mock_events_list
    mock_service_instance.events.return_value.insert.return_value = mock_events_insert
    mocker.patch('src.google_calendar.build', return_value=mock_service_instance)
    return mock_service_instance

@pytest.fixture
def exporter(mock_service, monkeypatch, mock_google_creds_object):
    """Fixture to create a GoogleCalendarExporter instance with mocked service and controlled env."""
    fixture_calendar_id = 'fixture_calendar_id'
    monkeypatch.setenv('BINS_GOOGLE_CALENDAR_ID', fixture_calendar_id)
    monkeypatch.setenv('BINS_GOOGLE_CREDENTIALS_JSON', '{"type": "service_account", "private_key": "dummy_key", "client_email": "dummy@example.com"}')
    monkeypatch.setenv('BINS_GOOGLE_CREDENTIALS', 'dummy_credentials_file.json')

    with patch.object(GoogleCalendarExporter, '_get_credentials', return_value=mock_google_creds_object):
        gce = GoogleCalendarExporter()
        assert gce.calendar_id == fixture_calendar_id
        return gce

@pytest.fixture
def mock_datetime_controlled_year():
    """
    Fixture providing a context manager to mock the year returned by datetime.now().
    Ensures other datetime functions like strptime, combine, min, max are still available.
    """
    @contextmanager
    def _mock_year(year_to_mock):
        # Store original datetime attributes that we might need
        original_strptime = datetime.strptime
        original_combine = datetime.combine
        original_min_time = datetime.min
        original_max_time = datetime.max
        # We need to patch 'datetime.now' specifically where it's used in google_calendar.py
        # which is 'src.google_calendar.datetime.now'
        with patch('src.google_calendar.datetime') as mock_datetime_module:
            mock_dt_now_instance = MagicMock(spec=datetime)
            mock_dt_now_instance.year = year_to_mock
            
            # Configure the mock_datetime_module object
            mock_datetime_module.now.return_value = mock_dt_now_instance
            mock_datetime_module.strptime = original_strptime
            mock_datetime_module.combine = original_combine
            mock_datetime_module.min = original_min_time
            mock_datetime_module.max = original_max_time
            # If other datetime attributes are needed, add them here.
            yield mock_datetime_module
    return _mock_year


def test_initialization(exporter, mock_service):
    """Test that the exporter initializes correctly and builds the service."""
    assert exporter.calendar_id == 'fixture_calendar_id'
    assert exporter.timezone == 'Europe/London'
    assert isinstance(exporter.tz, pytz.tzinfo.BaseTzInfo)
    assert exporter.service is not None
    assert exporter.service is mock_service


@pytest.mark.parametrize("coll_date_str, coll_month, current_dt_tuple, expected_date_tuple", [
    ("10 Thursday", "April", (TEST_YEAR, 3, 1), (TEST_YEAR, 4, 10)),
    ("26 Friday", "December", (TEST_YEAR, 11, 1), (TEST_YEAR, 12, 26)),
    ("5 Monday", "January", (TEST_YEAR, 12, 20), (TEST_YEAR + 1, 1, 5)),
    ("31 Wednesday", "October", (TEST_YEAR, 11, 1), (TEST_YEAR + 1, 10, 31)),
])
def test_parse_collection_date_success(exporter, mock_datetime_controlled_year, coll_date_str, coll_month, current_dt_tuple, expected_date_tuple):
    current_dt = date(*current_dt_tuple)
    expected_date = date(*expected_date_tuple)
    collection = BinCollection(coll_date_str, coll_month, "Test", "col", "link")
    
    with mock_datetime_controlled_year(current_dt.year): # Use the new fixture
        parsed_date = exporter._parse_collection_date(collection, current_dt)
        assert parsed_date == expected_date


def test_parse_collection_date_invalid_format(exporter, caplog):
    collection = BinCollection("Invalid Date", "April", "Test", "col", "link")
    parsed_date = exporter._parse_collection_date(collection, date(TEST_YEAR, 3, 1))
    assert parsed_date is None
    assert "Error parsing date" in caplog.text


def test_parse_collection_date_missing_month(exporter, caplog):
    collection = BinCollection("10 Thursday", None, "Test", "col", "link")
    parsed_date = exporter._parse_collection_date(collection, date(TEST_YEAR, 3, 1))
    assert parsed_date is None
    assert "Skipping collection due to missing month" in caplog.text


def test_create_event_data(exporter):
    """Test event data creation from BinCollection."""
    collection = TEST_COLLECTIONS[0]
    event_date = APRIL_10_DATE
    event_data = exporter._create_event_data(collection, TEST_ADDRESS, event_date)
    assert event_data['summary'] == f"{collection.bin_type} bin collection"
    assert event_data['location'] == TEST_ADDRESS
    assert event_data['description'] == f"Bin collection day for: {collection.bin_type} ({collection.bin_colour} bin).\nLink: {collection.bin_link}"
    assert event_data['start']['date'] == event_date.isoformat()
    assert event_data['end']['date'] == (event_date + timedelta(days=1)).isoformat()
    assert event_data['transparency'] == 'transparent'
    assert 'reminders' in event_data


def test_find_existing_event_found(exporter, mock_service):
    """Test finding an existing event."""
    summary = "Household bin collection"
    event_date = APRIL_10_DATE
    existing_event_id = "existing_event_123"
    mock_service.events.return_value.list.return_value.execute.return_value = {
        'items': [
            {'id': existing_event_id, 'summary': summary, 'start': {'date': event_date.isoformat()}}
        ]
    }
    found_id = exporter._find_existing_event(summary, event_date)
    assert found_id == existing_event_id
    mock_service.events.return_value.list.assert_called_once()
    call_args, call_kwargs = mock_service.events.return_value.list.call_args
    assert call_kwargs['calendarId'] == exporter.calendar_id
    assert call_kwargs['q'] == summary
    expected_time_min = exporter.tz.localize(datetime.combine(event_date, datetime.min.time())).isoformat()
    expected_time_max = exporter.tz.localize(datetime.combine(event_date, datetime.max.time())).isoformat()
    assert call_kwargs['timeMin'] == expected_time_min
    assert call_kwargs['timeMax'] == expected_time_max


def test_find_existing_event_not_found(exporter, mock_service):
    """Test when no matching event is found."""
    summary = "NonExistent bin collection"
    event_date = APRIL_10_DATE
    mock_service.events.return_value.list.return_value.execute.return_value = {'items': []}
    found_id = exporter._find_existing_event(summary, event_date)
    assert found_id is None
    mock_service.events.return_value.list.assert_called_once()


def test_find_existing_event_api_error(exporter, mock_service, caplog):
    """Test handling of API errors during event search."""
    summary = "Household bin collection"
    event_date = APRIL_10_DATE
    mock_service.events.return_value.list.return_value.execute.side_effect = Exception("API Error")
    found_id = exporter._find_existing_event(summary, event_date)
    assert found_id is None
    assert "Error searching for existing Google Calendar events" in caplog.text
    assert "API Error" in caplog.text
    mock_service.events.return_value.list.assert_called_once()


def test_upload_events_success_no_duplicates(exporter, mock_service, mock_datetime_controlled_year):
    """Test successful upload when no duplicates exist."""
    with patch.object(exporter, '_find_existing_event', return_value=None) as mock_find:
        current_test_date = date(TEST_YEAR, 4, 1)
        with mock_datetime_controlled_year(current_test_date.year): # Use the new fixture
            result = exporter.upload_events(TEST_FETCHER_RESULT, current_date_override=current_test_date)
            assert result is True
            assert mock_find.call_count == len(TEST_COLLECTIONS)
            assert mock_service.events.return_value.insert.call_count == len(TEST_COLLECTIONS)
            mock_service.events.return_value.insert.assert_called()


def test_upload_events_skips_duplicates(exporter, mock_service, mock_datetime_controlled_year):
    """Test that duplicate events are skipped."""
    duplicate_collection = TEST_COLLECTIONS[1]
    duplicate_summary = f"{duplicate_collection.bin_type} bin collection"
    duplicate_event_date = APRIL_17_DATE
    existing_event_id = "existing_recycle_event"
    current_test_date = date(TEST_YEAR, 4, 1)

    def find_side_effect(summary, event_date_arg):
        if summary == duplicate_summary and event_date_arg == duplicate_event_date:
            return existing_event_id
        return None

    with patch.object(exporter, '_find_existing_event', side_effect=find_side_effect) as mock_find:
        with mock_datetime_controlled_year(current_test_date.year): # Use the new fixture
            result = exporter.upload_events(TEST_FETCHER_RESULT, current_date_override=current_test_date)
            assert result is True
            assert mock_find.call_count == len(TEST_COLLECTIONS)
            assert mock_service.events.return_value.insert.call_count == len(TEST_COLLECTIONS) - 1
            insert_calls = mock_service.events.return_value.insert.call_args_list
            inserted_summaries = [c.kwargs['body']['summary'] for c in insert_calls]
            assert f"{TEST_COLLECTIONS[0].bin_type} bin collection" in inserted_summaries
            assert f"{TEST_COLLECTIONS[2].bin_type} bin collection" in inserted_summaries
            assert duplicate_summary not in inserted_summaries


def test_upload_events_insert_failure(exporter, mock_service, caplog, mock_datetime_controlled_year):
    """Test failure during the insert operation (after duplicate check)."""
    current_test_date = date(TEST_YEAR, 4, 1)
    with patch.object(exporter, '_find_existing_event', return_value=None) as mock_find:
        mock_service.events.return_value.insert.return_value.execute.side_effect = [
            {'id': 'event1', 'htmlLink': 'link1'},
            Exception("API Insert Error"),
            {'id': 'event3', 'htmlLink': 'link3'}
        ]
        with mock_datetime_controlled_year(current_test_date.year): # Use the new fixture
            result = exporter.upload_events(TEST_FETCHER_RESULT, current_date_override=current_test_date)
            assert result is False
            assert mock_find.call_count == len(TEST_COLLECTIONS)
            assert mock_service.events.return_value.insert.call_count == len(TEST_COLLECTIONS)
            assert "Failed to process or upload event" in caplog.text
            assert "API Insert Error" in caplog.text


def test_upload_events_find_failure(exporter, mock_service, caplog, mock_datetime_controlled_year):
    """Test failure during the find operation."""
    current_test_date = date(TEST_YEAR, 4, 1)
    first_collection_parsed_date = date(TEST_YEAR, 4, 10)

    def find_side_effect(summary, event_date_arg):
        if summary == f"{TEST_COLLECTIONS[0].bin_type} bin collection" and event_date_arg == first_collection_parsed_date:
            raise Exception("API Find Error")
        return None

    with patch.object(exporter, '_find_existing_event', side_effect=find_side_effect) as mock_find:
        with mock_datetime_controlled_year(current_test_date.year): # Use the new fixture
            result = exporter.upload_events(TEST_FETCHER_RESULT, current_date_override=current_test_date)
            assert result is False
            assert mock_find.call_count == len(TEST_COLLECTIONS)
            assert mock_service.events.return_value.insert.call_count == len(TEST_COLLECTIONS) - 1
            assert "Failed to process or upload event" in caplog.text
            assert "API Find Error" in caplog.text


def test_upload_events_no_collections(exporter, mock_service, caplog):
    """Test upload with no collections in the result."""
    caplog.set_level(logging.INFO)
    empty_result = FetcherResult(address_text=TEST_ADDRESS, collections=[])
    result = exporter.upload_events(empty_result)
    assert result is True
    assert "No upcoming collections found. Skipping Google Calendar upload." in caplog.text
    mock_service.events.return_value.insert.assert_not_called()
    assert any(record.levelname == 'INFO' and record.message == "No upcoming collections found. Skipping Google Calendar upload." for record in caplog.records)


def test_upload_events_service_unavailable(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv('BINS_GOOGLE_CALENDAR_ID', 'test_id_for_no_service')
    
    with patch.object(GoogleCalendarExporter, '_build_service', return_value=None) as mock_internal_build_service:
        exporter_instance = GoogleCalendarExporter()
        assert exporter_instance.service is None
        
        result = exporter_instance.upload_events(TEST_FETCHER_RESULT)
        assert result is False
        assert "Google Calendar service not available. Upload aborted." in caplog.text
        mock_internal_build_service.assert_called_once()


def test_initialization_no_calendar_id(monkeypatch):
    with pytest.raises(ValueError, match="Calendar ID must be provided via parameter or 'BINS_GOOGLE_CALENDAR_ID' environment variable"):
        GoogleCalendarExporter(calendar_id=None)


def test_build_service_failure(mocker, monkeypatch, caplog, mock_google_creds_object):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv('BINS_GOOGLE_CALENDAR_ID', 'primary')
    mocker.patch.object(GoogleCalendarExporter, '_get_credentials', return_value=mock_google_creds_object)
    mocker.patch('src.google_calendar.build', side_effect=Exception("Build Failed"))
    
    exporter = GoogleCalendarExporter()
    assert exporter.service is None
    assert "Failed to build Google Calendar service" in caplog.text
    assert "Build Failed" in caplog.text

# --- Tests for _get_credentials logic ---

def test_get_credentials_success_from_json_env_var(monkeypatch, mocker, caplog, mock_google_creds_object):
    """Test _get_credentials loads successfully from BINS_GOOGLE_CREDENTIALS_JSON."""
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("BINS_GOOGLE_CALENDAR_ID", "test_json_cal_id")
    dummy_creds_json_str = '{"client_email": "test@example.com", "private_key": "key", "type": "service_account"}'
    monkeypatch.setenv("BINS_GOOGLE_CREDENTIALS_JSON", dummy_creds_json_str)

    mock_from_info = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_info', return_value=mock_google_creds_object)
    mock_build = mocker.patch('src.google_calendar.build')

    exporter = GoogleCalendarExporter()
    
    mock_from_info.assert_called_once_with(json.loads(dummy_creds_json_str), scopes=EXPECTED_SCOPES)
    assert "Credentials loaded successfully from BINS_GOOGLE_CREDENTIALS_JSON environment variable." in caplog.text
    mock_build.assert_called_once_with('calendar', 'v3', credentials=mock_google_creds_object, cache_discovery=False)


def test_get_credentials_success_from_file_env_var(monkeypatch, mocker, caplog, mock_google_creds_object):
    """Test _get_credentials loads successfully from BINS_GOOGLE_CREDENTIALS (file path)."""
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("BINS_GOOGLE_CALENDAR_ID", "test_file_cal_id")
    dummy_creds_file_path = "dummy_creds_path.json"
    monkeypatch.setenv("BINS_GOOGLE_CREDENTIALS", dummy_creds_file_path)

    mock_from_file = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_file', return_value=mock_google_creds_object)
    mock_from_info = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_info')
    mock_build = mocker.patch('src.google_calendar.build')

    exporter = GoogleCalendarExporter()
    
    mock_from_info.assert_not_called()
    mock_from_file.assert_called_once_with(dummy_creds_file_path, scopes=EXPECTED_SCOPES)
    assert f"Credentials loaded successfully from file path: {dummy_creds_file_path}" in caplog.text
    mock_build.assert_called_once_with('calendar', 'v3', credentials=mock_google_creds_object, cache_discovery=False)


def test_get_credentials_json_parse_error_fallback_to_file_success(monkeypatch, mocker, caplog, mock_google_creds_object):
    """Test _get_credentials tries file if BINS_GOOGLE_CREDENTIALS_JSON parsing fails."""
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("BINS_GOOGLE_CALENDAR_ID", "test_fallback_cal_id")
    invalid_json_str = '{"this is not valid json'
    dummy_creds_file_path = "fallback_creds_path.json"
    monkeypatch.setenv("BINS_GOOGLE_CREDENTIALS_JSON", invalid_json_str)
    monkeypatch.setenv("BINS_GOOGLE_CREDENTIALS", dummy_creds_file_path)

    mocker.patch('src.google_calendar.json.loads', side_effect=json.JSONDecodeError("mock_parse_error", "doc", 0))
    mock_from_info = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_info')
    mock_from_file = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_file', return_value=mock_google_creds_object)
    mock_build = mocker.patch('src.google_calendar.build')

    exporter = GoogleCalendarExporter()

    assert "Failed to parse JSON from BINS_GOOGLE_CREDENTIALS_JSON" in caplog.text
    mock_from_info.assert_not_called()
    mock_from_file.assert_called_once_with(dummy_creds_file_path, scopes=EXPECTED_SCOPES)
    assert f"Credentials loaded successfully from file path: {dummy_creds_file_path}" in caplog.text
    mock_build.assert_called_once_with('calendar', 'v3', credentials=mock_google_creds_object, cache_discovery=False)


def test_get_credentials_json_load_error_fallback_to_file_success(monkeypatch, mocker, caplog, mock_google_creds_object):
    """Test _get_credentials tries file if BINS_GOOGLE_CREDENTIALS_JSON loading (not parsing) fails."""
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("BINS_GOOGLE_CALENDAR_ID", "test_json_load_fail_cal_id")
    dummy_creds_json_str = '{"type": "service_account"}'
    dummy_creds_file_path = "fallback_path_after_json_fail.json"
    monkeypatch.setenv("BINS_GOOGLE_CREDENTIALS_JSON", dummy_creds_json_str)
    monkeypatch.setenv("BINS_GOOGLE_CREDENTIALS", dummy_creds_file_path)

    mock_from_info = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_info', side_effect=Exception("Simulated JSON credentials load error"))
    mock_from_file = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_file', return_value=mock_google_creds_object)
    mock_build = mocker.patch('src.google_calendar.build')

    exporter = GoogleCalendarExporter()

    assert "Failed to load credentials from BINS_GOOGLE_CREDENTIALS_JSON" in caplog.text
    assert "Simulated JSON credentials load error" in caplog.text
    mock_from_info.assert_called_once()
    mock_from_file.assert_called_once_with(dummy_creds_file_path, scopes=EXPECTED_SCOPES)
    assert f"Credentials loaded successfully from file path: {dummy_creds_file_path}" in caplog.text
    mock_build.assert_called_once_with('calendar', 'v3', credentials=mock_google_creds_object, cache_discovery=False)


def test_get_credentials_json_success_file_not_attempted(monkeypatch, mocker, caplog, mock_google_creds_object):
    """Test if JSON creds succeed, file path is not attempted."""
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("BINS_GOOGLE_CALENDAR_ID", "test_json_prio_cal_id")
    dummy_creds_json_str = '{"type": "service_account"}'
    monkeypatch.setenv("BINS_GOOGLE_CREDENTIALS_JSON", dummy_creds_json_str)
    monkeypatch.setenv("BINS_GOOGLE_CREDENTIALS", "should_not_be_used_file.json")

    mock_from_info = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_info', return_value=mock_google_creds_object)
    mock_from_file = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_file')
    mock_build = mocker.patch('src.google_calendar.build')

    exporter = GoogleCalendarExporter()

    mock_from_info.assert_called_once()
    mock_from_file.assert_not_called()
    assert "Credentials loaded successfully from BINS_GOOGLE_CREDENTIALS_JSON" in caplog.text
    mock_build.assert_called_once_with('calendar', 'v3', credentials=mock_google_creds_object, cache_discovery=False)


def test_get_credentials_neither_var_set(monkeypatch, mocker, caplog):
    """Test _get_credentials behavior when no credential env vars are set."""
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("BINS_GOOGLE_CALENDAR_ID", "test_no_creds_cal_id")
    # autouse fixture ensures BINS_GOOGLE_CREDENTIALS_JSON and BINS_GOOGLE_CREDENTIALS are not set.

    mock_from_info = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_info')
    mock_from_file = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_file')
    
    # This mock means that when _build_service calls build(), it gets None back for the service.
    mock_build_call = mocker.patch('src.google_calendar.build', return_value=None)

    exporter = GoogleCalendarExporter()

    mock_from_info.assert_not_called()
    mock_from_file.assert_not_called()
    assert "Neither BINS_GOOGLE_CREDENTIALS_JSON nor BINS_GOOGLE_CREDENTIALS environment variable is set." in caplog.text
    
    # _get_credentials returns None, so build is called with credentials=None
    mock_build_call.assert_called_once_with('calendar', 'v3', credentials=None, cache_discovery=False)
    
    # Since mock_build_call returns None, exporter.service becomes None.
    assert exporter.service is None
    
    # IMPORTANT CHANGE HERE:
    # The _build_service logs "Google Calendar service built successfully." if the call to
    # build() itself does NOT raise an exception. It then returns the result of build() (which is None here).
    # If build() *did* raise an exception, *then* "Failed to build Google Calendar service" would be logged.
    assert "Google Calendar service built successfully." in caplog.text # This is what happens if build returns None
    assert "Failed to build Google Calendar service" not in caplog.text # This should NOT be logged

def test_get_credentials_failure_on_file_load_path(monkeypatch, mocker, caplog):
    """Test _get_credentials when BINS_GOOGLE_CREDENTIALS file path loading fails."""
    caplog.set_level(logging.INFO)
    monkeypatch.setenv('BINS_GOOGLE_CALENDAR_ID', 'primary_file_fail')
    monkeypatch.setenv('BINS_GOOGLE_CREDENTIALS', 'path_that_will_fail.json')

    mock_from_file = mocker.patch('src.google_calendar.service_account.Credentials.from_service_account_file',
                                 side_effect=Exception("Credentials File Load Failed"))
    mock_service_obj_after_failed_creds = MagicMock(name="mock_service_after_failed_creds")
    mock_build_call = mocker.patch('src.google_calendar.build', return_value=mock_service_obj_after_failed_creds)

    exporter = GoogleCalendarExporter()

    assert "Failed to load service account credentials from file path 'path_that_will_fail.json'" in caplog.text
    assert "Credentials File Load Failed" in caplog.text
    mock_from_file.assert_called_once_with('path_that_will_fail.json', scopes=EXPECTED_SCOPES)
    
    mock_build_call.assert_called_once_with('calendar', 'v3', credentials=None, cache_discovery=False)
    assert exporter.service is mock_service_obj_after_failed_creds
    assert "Google Calendar service built successfully." in caplog.text
    assert "Failed to build Google Calendar service" not in caplog.text

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
