import pytest
import requests
import os
import sys
import json
from unittest.mock import MagicMock

# Update sys.path to include the project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Updated imports
from src.data_fetchers.gateshead_bin_data import GatesheadBinData, BASE_URL, BIN_CHECKER_URL, ADDRESS_LOOKUP_URL, PROCESS_SUBMISSION_URL
from src.data_models import BinCollection, FetcherResult
from src.data_fetchers.cached_data_fetcher import CACHE_DIR, _get_cache_filename

# --- Mock HTML/JSON Data --- (Remains the same)
MOCK_INITIAL_HTML = """<html><body><input name="BINCOLLECTIONCHECKER_PAGESESSIONID" value="mockPageSessionId123"/><input name="BINCOLLECTIONCHECKER_SESSIONID" value="mockFsid456"/><input name="BINCOLLECTIONCHECKER_NONCE" value="mockNonce789"/></body></html>"""
MOCK_ADDRESS_JSONP = """getAddresses({"jsonrpc": "2.0", "id": 1, "result": [{"line1": "1", "line2": "Test Street", "postcode": "AB1 2CD", "udprn": "100000000001"}, {"line1": "22", "line2": "Oak Street", "postcode": "CD3 4EF", "udprn": "100000031493"}, {"line1": "100", "line2": "Test Avenue", "postcode": "EF5 6GH", "udprn": "100000000002"}]})"""
MOCK_SCHEDULE_HTML = """<html><body><span class="jumboinfo__text--extralarge">Next collection Thursday 10 April</span><table class="bincollections__table"><tr><th colspan="3">April</th></tr><tr><td>10</td><td>Thursday</td><td><a class="bincollections__link" href="/household">Household Waste</a></td></tr><tr><td>17</td><td>Thursday</td><td><a class="bincollections__link" href="/recycling">Recycling - Glass, plastic and cans</a></td></tr><tr><th colspan="3">May</th></tr><tr><td>1</td><td>Thursday</td><td><a class="bincollections__link" href="/garden">Garden Waste</a></td></tr></table></body></html>"""
MOCK_EMPTY_SCHEDULE_HTML = """<html><body><p>no collection dates found for this address.</p></body></html>"""
MOCK_NO_TABLE_HTML = "<html><body><p>Some other content</p></body></html>"
MOCK_INVALID_SCHEDULE_HTML = "<html><body><table class='bincollections__table'><tr><td>Missing data</tr></table></body></html>"
MOCK_SCHEDULE_NEEDS_NORMALIZATION_HTML = """
<html><body>
<table class="bincollections__table">
    <tr><th colspan="3">June</th></tr>
    <tr><td>5</td><td>Friday</td><td><a class="bincollections__link" href="/pap">Recycling - Paper and cardboard only</a></td></tr>
    <tr><td>12</td><td>Friday</td><td><a class="bincollections__link" href="/hh">Household</a></td></tr>
    <tr><td>19</td><td>Friday</td><td><a class="bincollections__link" href="/gw">Garden</a></td></tr>
</table>
</body></html>
"""

# Helper remains the same
def create_mock_response(text, status_code=200, url="http://mock.url"):
    """Creates a mock requests.Response object."""
    mock_resp = MagicMock(spec=requests.Response); mock_resp.text = text; mock_resp.status_code = status_code; mock_resp.url = url; mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(f"{status_code}", response=mock_resp) if status_code >= 400 else None; return mock_resp

# --- Fixture ---
@pytest.fixture
def gateshead_test_setup():
    """Fixture to set up test constants and clean cache."""
    postcode = "AB1 2CD"
    house_num = "1"
    cache_file = _get_cache_filename(postcode, house_num)

    # --- Setup phase ---
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(cache_file):
        os.remove(cache_file)

    # --- Yield values to test ---
    yield postcode, house_num, cache_file

    # --- Teardown phase ---
    if os.path.exists(cache_file):
        try:
            os.remove(cache_file)
        except OSError as e:
             print(f"Warning: Error removing cache file during teardown: {e}", file=sys.stderr)


# --- Tests ---
def test_get_bin_dates_always_fetches(mocker, gateshead_test_setup):
    postcode, house_number, cache_file = gateshead_test_setup
    street_name = "Test Street"; ANY = mocker.ANY; call = mocker.call
    mock_post = mocker.patch('src.data_fetchers.gateshead_bin_data.requests.post')
    mock_session_get = mocker.patch('src.data_fetchers.gateshead_bin_data.requests.Session.get')
    fetcher = GatesheadBinData()
    mock_session_get.side_effect = [create_mock_response(MOCK_INITIAL_HTML), create_mock_response(MOCK_ADDRESS_JSONP)]
    mock_post.return_value = create_mock_response(MOCK_SCHEDULE_HTML)
    result = fetcher.get_bin_dates(postcode, house_number)
    expected_address = f"{house_number} {street_name}, {postcode}"
    expected_collections = [
        BinCollection(date='10 Thursday', month='April', bin_type='Household Waste', bin_colour='green', bin_link=f'{BASE_URL}/household'),
        BinCollection(date='17 Thursday', month='April', bin_type='Recycling - Glass, plastic and cans', bin_colour='dark blue', bin_link=f'{BASE_URL}/recycling'),
        BinCollection(date='1 Thursday', month='May', bin_type='Garden Waste', bin_colour='garden', bin_link=f'{BASE_URL}/garden')
    ]
    expected_result_obj = FetcherResult(address_text=expected_address, collections=expected_collections)
    assert result == expected_result_obj
    mock_session_get.assert_has_calls([call(BIN_CHECKER_URL, headers=ANY, timeout=ANY), call(ADDRESS_LOOKUP_URL, params=ANY, timeout=ANY)])
    assert mock_session_get.call_count == 2
    mock_post.assert_called_once_with(PROCESS_SUBMISSION_URL, params=ANY, headers=ANY, data=ANY, timeout=ANY, allow_redirects=True)

def test_get_bin_dates_fetch_fails_address(mocker):
     mock_post = mocker.patch('src.data_fetchers.gateshead_bin_data.requests.post')
     mock_session_get = mocker.patch('src.data_fetchers.gateshead_bin_data.requests.Session.get')
     fetcher = GatesheadBinData(); postcode = "FA1 1KE"; house_number = "1"
     mock_session_get.side_effect = [create_mock_response(MOCK_INITIAL_HTML), create_mock_response("Not Found", 404)]
     result = fetcher.get_bin_dates(postcode, house_number)
     assert result is None
     mock_post.assert_not_called()

def test_get_bin_dates_fetch_fails_schedule(mocker, gateshead_test_setup):
     postcode, house_number, _ = gateshead_test_setup
     mock_post = mocker.patch('src.data_fetchers.gateshead_bin_data.requests.post')
     mock_session_get = mocker.patch('src.data_fetchers.gateshead_bin_data.requests.Session.get')
     fetcher = GatesheadBinData()
     mock_session_get.side_effect = [create_mock_response(MOCK_INITIAL_HTML), create_mock_response(MOCK_ADDRESS_JSONP)]
     mock_post.return_value = create_mock_response("Server Error", 500)
     result = fetcher.get_bin_dates(postcode, house_number)
     assert result is None

def test_internal_get_address_udprn_found(mocker):
     ANY = mocker.ANY
     mock_session_get = mocker.patch('src.data_fetchers.gateshead_bin_data.requests.Session.get')
     fetcher = GatesheadBinData(); postcode = "CD3 4EF"; house_number_target = "22"
     mock_session_get.return_value = create_mock_response(MOCK_ADDRESS_JSONP)
     udprn, address_text = fetcher._get_address_udprn(postcode, house_number_target, {})
     assert udprn == "100000031493"
     assert address_text == "22 Oak Street, CD3 4EF"
     mock_session_get.assert_called_once_with(ADDRESS_LOOKUP_URL, params=ANY, timeout=ANY)

def test_internal_get_address_udprn_not_found(mocker):
     ANY = mocker.ANY
     mock_session_get = mocker.patch('src.data_fetchers.gateshead_bin_data.requests.Session.get')
     fetcher = GatesheadBinData(); postcode = "CD3 4EF"; house_number_target = "999"
     mock_session_get.return_value = create_mock_response(MOCK_ADDRESS_JSONP)
     udprn, address_text = fetcher._get_address_udprn(postcode, house_number_target, {})
     assert udprn is None
     assert address_text is None
     mock_session_get.assert_called_once_with(ADDRESS_LOOKUP_URL, params=ANY, timeout=ANY)

def test_internal_parse_bin_schedule_success():
     fetcher = GatesheadBinData()
     schedule = fetcher._parse_bin_schedule(MOCK_SCHEDULE_HTML)
     expected_schedule = [
        BinCollection(date='10 Thursday', month='April', bin_type='Household Waste', bin_colour='green', bin_link=f'{BASE_URL}/household'),
        BinCollection(date='17 Thursday', month='April', bin_type='Recycling - Glass, plastic and cans', bin_colour='dark blue', bin_link=f'{BASE_URL}/recycling'),
        BinCollection(date='1 Thursday', month='May', bin_type='Garden Waste', bin_colour='garden', bin_link=f'{BASE_URL}/garden')
     ]
     assert schedule == expected_schedule

def test_internal_parse_bin_schedule_normalization():
     """Tests suffix removal and short name mapping."""
     fetcher = GatesheadBinData()
     schedule = fetcher._parse_bin_schedule(MOCK_SCHEDULE_NEEDS_NORMALIZATION_HTML)
     expected_schedule = [
        BinCollection(date='5 Friday', month='June', bin_type='Recycling - Paper and cardboard', bin_colour='light blue with red top', bin_link=f'{BASE_URL}/pap'),
        BinCollection(date='12 Friday', month='June', bin_type='Household Waste', bin_colour='green', bin_link=f'{BASE_URL}/hh'),
        BinCollection(date='19 Friday', month='June', bin_type='Garden Waste', bin_colour='garden', bin_link=f'{BASE_URL}/gw'),
     ]
     assert schedule is not None
     assert len(schedule) == 3
     assert schedule == expected_schedule

def test_internal_parse_bin_schedule_empty():
     fetcher = GatesheadBinData()
     schedule = fetcher._parse_bin_schedule(MOCK_EMPTY_SCHEDULE_HTML)
     assert schedule == []

def test_internal_parse_bin_schedule_table_not_found_no_message(mocker):
     fetcher = GatesheadBinData(); ANY = mocker.ANY
     mock_print = mocker.patch('src.data_fetchers.gateshead_bin_data.print')
     schedule = fetcher._parse_bin_schedule(MOCK_NO_TABLE_HTML)
     assert schedule is None
     mock_print.assert_any_call(ANY, file=sys.stderr)

def test_internal_parse_bin_schedule_error(mocker):
     fetcher = GatesheadBinData()
     schedule = fetcher._parse_bin_schedule(MOCK_INVALID_SCHEDULE_HTML)
     assert schedule == []