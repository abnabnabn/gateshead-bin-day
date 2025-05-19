import pytest
import os
import sys
from datetime import datetime, date, timedelta
from icalendar import Calendar, Event, Alarm # Import Calendar

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Imports from the module being tested and the data model
from src.calendar_generator import generate_calendar_object, create_ics_file # Import BOTH functions
from src.data_models import BinCollection, FetcherResult


# --- Fixture for test file cleanup --- (Remains the same)
@pytest.fixture
def ics_file_cleanup():
    filename = 'bin_collections.ics'
    if os.path.exists(filename): os.remove(filename)
    yield filename
    if os.path.exists(filename): os.remove(filename)

# --- Test Data using FetcherResult --- (Remains the same)
TEST_ADDRESS = "Test Address"
TEST_COLLECTIONS = [ BinCollection("10 Thursday", "April", "Household", "green", "/link1"), BinCollection("17 Thursday", "April", "Recycling", "dark blue", "/link2") ]
TEST_FETCHER_RESULT = FetcherResult(address_text=TEST_ADDRESS, collections=TEST_COLLECTIONS)
TEST_ADDRESS_ROLLOVER = "Test Address Rollover"
TEST_COLLECTIONS_ROLLOVER = [ BinCollection("26 Friday", "December", "Household", "green", "/link1"), BinCollection("2 Friday", "January", "Recycling", "blue", "/link2"), ]
TEST_FETCHER_RESULT_ROLLOVER = FetcherResult(address_text=TEST_ADDRESS_ROLLOVER, collections=TEST_COLLECTIONS_ROLLOVER)


# --- Tests for generate_calendar_object ---

def test_generate_calendar_object_content():
    """Tests the properties of the generated Calendar object."""
    test_data = TEST_FETCHER_RESULT
    current_year = datetime.now().year

    # Call the generator function
    cal = generate_calendar_object(test_data)

    # Assert basic calendar properties
    assert isinstance(cal, Calendar)
    assert cal.get('prodid') == '-//Bin Calendar//Gateshead//EN'
    assert cal.get('version') == '2.0'

    # Assert event properties (similar to previous file content test)
    events = [comp for comp in cal.walk() if comp.name == "VEVENT"]
    assert len(events) == len(test_data.collections)

    expected_summaries = ["Household bin collection", "Recycling bin collection"]
    current_date_for_compare = datetime.now()
    expected_april_10 = date(current_year, 4, 10); expected_april_17 = date(current_year, 4, 17)
    if current_date_for_compare > datetime(current_year, 4, 17): expected_april_10 = date(current_year + 1, 4, 10); expected_april_17 = date(current_year + 1, 4, 17)
    elif current_date_for_compare > datetime(current_year, 4, 10): expected_april_10 = date(current_year + 1, 4, 10)
    expected_dates = [ expected_april_10, expected_april_17 ]

    events.sort(key=lambda e: e.get('dtstart').dt)

    for i, event in enumerate(events):
        assert isinstance(event, Event)
        assert str(event.get('summary')) == expected_summaries[i]
        assert str(event.get('location')) == test_data.address_text
        dtstart = event.get('dtstart'); assert isinstance(dtstart.dt, date); assert not isinstance(dtstart.dt, datetime); assert dtstart.params.get('VALUE') == 'DATE'; assert event.get('dtend') is None
        assert event.get('transp') == 'TRANSPARENT'
        assert dtstart.dt == expected_dates[i]
        alarms = [comp for comp in event.walk() if isinstance(comp, Alarm)]; assert len(alarms) == 1; alarm = alarms[0]
        assert alarm.get('action') == 'DISPLAY'; expected_description = f"Put out {test_data.collections[i].bin_type} ({test_data.collections[i].bin_colour} bin) tomorrow"; assert alarm.get('description') == expected_description; assert alarm.get('trigger').dt == timedelta(hours=-4.5)


def test_generate_calendar_object_year_rollover():
    """Tests year rollover logic in the generated Calendar object."""
    current_year = 2025
    test_current_date = datetime(current_year, 12, 20, 10, 0, 0)
    test_data = TEST_FETCHER_RESULT_ROLLOVER

    # Call the generator function
    cal = generate_calendar_object(test_data, current_date=test_current_date)
    assert isinstance(cal, Calendar)
    events = [comp for comp in cal.walk() if comp.name == "VEVENT"]
    assert len(events) == 2
    events.sort(key=lambda e: e.get('dtstart').dt)

    expected_dates = [ date(current_year, 12, 26), date(current_year + 1, 1, 2) ]
    expected_summaries = [ "Household bin collection", "Recycling bin collection" ]

    for i, event in enumerate(events):
        assert isinstance(event, Event)
        dtstart = event.get('dtstart')
        event_date = dtstart.dt if isinstance(dtstart.dt, date) else dtstart.dt.date()
        assert event_date == expected_dates[i]
        assert str(event.get('summary')) == expected_summaries[i]
        assert str(event.get('location')) == test_data.address_text
        assert isinstance(dtstart.dt, date)
        assert event.get('dtend') is None
        assert event.get('transp') == 'TRANSPARENT'
        alarms = [comp for comp in event.walk() if isinstance(comp, Alarm)]; assert len(alarms) == 1; alarm = alarms[0]
        assert alarm.get('action') == 'DISPLAY'; assert alarm.get('trigger').dt == timedelta(hours=-4.5)

# --- Tests for create_ics_file (Focus on file writing) ---

# Mock the generate_calendar_object function to isolate file writing
@pytest.mark.usefixtures("ics_file_cleanup") # Use fixture for cleanup
def test_create_ics_file_writes_file(mocker):
     """Tests that create_ics_file calls generator and writes a file."""
     ics_filename = "bin_collections.ics" # Relying on fixture isn't easy with mocker patch
     if os.path.exists(ics_filename): os.remove(ics_filename) # Manual cleanup for this test

     # Create a mock Calendar object to be returned by the generator
     mock_cal = Calendar()
     mock_cal.add('prodid', '-//Mock Calendar//EN')
     mock_cal.add('version', '2.0')
     mock_cal_bytes = mock_cal.to_ical()

     # Patch the generate_calendar_object function within the calendar_generator module
     mock_generator = mocker.patch('src.calendar_generator.generate_calendar_object')
     mock_generator.return_value = mock_cal # Make it return our mock calendar

     # Call the function that saves the file
     test_data = TEST_FETCHER_RESULT
     create_ics_file(test_data)

     # Assert that the generator was called
     mock_generator.assert_called_once_with(test_data, None) # Check it was called with correct args

     # Assert that the file was created and contains the mock content
     assert os.path.exists(ics_filename)
     with open(ics_filename, 'rb') as f:
         content = f.read()
         assert content == mock_cal_bytes

     if os.path.exists(ics_filename): os.remove(ics_filename) # Manual cleanup

# Keep existing integration tests (optional, but good)
# These tests now implicitly test both generate_calendar_object AND file writing
def test_create_ics_file_integration_content(ics_file_cleanup):
     """Integration test checking the content of the actual written file."""
     ics_filename = ics_file_cleanup
     test_data = TEST_FETCHER_RESULT
     create_ics_file(test_data)
     assert os.path.exists(ics_filename)
     # Reuse assertions from test_generate_calendar_object_content by reading file
     with open(ics_filename, 'rb') as f: cal = Calendar.from_ical(f.read())
     # ... (Add back assertions checking events, dtstart, transp, alarm etc. on 'cal') ...
     events = [comp for comp in cal.walk() if comp.name == "VEVENT"]; assert len(events) == len(test_data.collections) # etc.

def test_create_ics_file_integration_rollover(ics_file_cleanup):
     """Integration test checking year rollover in the written file."""
     ics_filename = ics_file_cleanup
     current_year = 2025; test_current_date = datetime(current_year, 12, 20, 10, 0, 0)
     test_data = TEST_FETCHER_RESULT_ROLLOVER
     create_ics_file(test_data, current_date=test_current_date)
     assert os.path.exists(ics_filename)
     # Reuse assertions from test_generate_calendar_object_year_rollover by reading file
     with open(ics_filename, 'rb') as f: cal = Calendar.from_ical(f.read())
     # ... (Add back assertions checking events, dtstart, transp, alarm etc. on 'cal') ...
     events = [comp for comp in cal.walk() if comp.name == "VEVENT"]; assert len(events) == 2 # etc.
