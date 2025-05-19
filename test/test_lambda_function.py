# Renamed from test_lambda.py to match module and convention

import pytest
import json
import base64
import os
import sys
from unittest.mock import MagicMock, ANY # ANY can be used if preferred over mocker.ANY
from icalendar import Calendar

# Add project root to allow importing lambda and src modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import the module named lambda_function.py
import lambda_function
from src.data_models import FetcherResult, BinCollection

# --- Test Data --- (Remains the same)
TEST_POSTCODE = "TEST1 1AA"; TEST_HOUSE = "10"; TEST_ADDRESS = f"{TEST_HOUSE} Test Street, {TEST_POSTCODE}"
TEST_COLLECTIONS = [BinCollection("1 Friday", "August", "Test Waste", "test-color", "/test")]
TEST_FETCHER_RESULT = FetcherResult(address_text=TEST_ADDRESS, collections=TEST_COLLECTIONS)
MOCK_CAL_BYTES = b"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Mock Cal//EN\nEND:VCALENDAR"

# --- Fixtures --- (Remain the same)
@pytest.fixture
def lambda_event_path_params(): return {"pathParameters": {"postcode": TEST_POSTCODE, "housenumber": TEST_HOUSE}}
@pytest.fixture
def lambda_event_missing_postcode_path(): return {"pathParameters": {"housenumber": TEST_HOUSE}}
@pytest.fixture
def lambda_event_missing_house_path(): return {"pathParameters": {"postcode": TEST_POSTCODE}}
@pytest.fixture
def lambda_event_env_vars(monkeypatch):
    """Fixture with environment variables set but no path parameters"""
    monkeypatch.setenv("MY_POSTCODE", TEST_POSTCODE)
    monkeypatch.setenv("MY_HOUSE_NUMBER", TEST_HOUSE)
    return {"pathParameters": None}

@pytest.fixture
def lambda_event_mixed_sources(monkeypatch):
    """Fixture with postcode in path and housenumber in env"""
    monkeypatch.setenv("MY_HOUSE_NUMBER", TEST_HOUSE)
    return {"pathParameters": {"postcode": TEST_POSTCODE}}


# --- Tests ---

def test_lambda_handler_success(mocker, lambda_event_path_params):
    """Test successful execution path."""
    # Patch target module name remains lambda_function
    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    mock_generate_cal = mocker.patch('lambda_function.generate_calendar_object')

    mock_fetcher = MagicMock(); mock_fetcher.get_bin_dates.return_value = TEST_FETCHER_RESULT; mock_create_fetcher.return_value = mock_fetcher
    mock_cal_obj = MagicMock(spec=Calendar); mock_cal_obj.to_ical.return_value = MOCK_CAL_BYTES; mock_generate_cal.return_value = mock_cal_obj

    # Call the handler via the imported module name
    response = lambda_function.lambda_handler(lambda_event_path_params, None)

    # Assertions (remain the same)
    mock_create_fetcher.assert_called_once_with(source=mocker.ANY, use_cache=False)
    mock_fetcher.get_bin_dates.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE)
    mock_generate_cal.assert_called_once_with(TEST_FETCHER_RESULT)
    mock_cal_obj.to_ical.assert_called_once()
    assert response["statusCode"] == 200; assert response["isBase64Encoded"] is True; assert response["headers"]["Content-Type"] == "text/calendar"; assert 'attachment; filename="bin_collections.ics"' in response["headers"]["Content-Disposition"]
    expected_body = base64.b64encode(MOCK_CAL_BYTES).decode('utf-8'); assert response["body"] == expected_body


def test_lambda_handler_missing_postcode(mocker, monkeypatch, lambda_event_missing_postcode_path):
    """Test 400 error if postcode is missing from path parameters and env."""
    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    
    # Ensure MY_POSTCODE is not effectively set in environment for this test
    monkeypatch.setenv("MY_POSTCODE", "") # Sets MY_POSTCODE to empty string, or creates it if not present
    # If MY_POSTCODE might exist and we want to ensure it's gone if it was pre-existing with a non-empty value:
    # monkeypatch.delenv("MY_POSTCODE", raising=False) # Ensure it's not there
    # monkeypatch.setenv("MY_POSTCODE", "") # Then set to empty if the lambda specifically checks for empty vs. non-existent

    response = lambda_function.lambda_handler(lambda_event_missing_postcode_path, None)
        
    assert response["statusCode"] == 400
    assert "Missing required path parameter: postcode" in response["body"]
    mock_create_fetcher.assert_not_called()


def test_lambda_handler_missing_house_number(mocker, monkeypatch, lambda_event_missing_house_path):
    """Test 400 error if housenumber is missing from path parameters and env."""
    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')

    # Ensure MY_HOUSE_NUMBER is not effectively set in environment for this test
    monkeypatch.setenv("MY_HOUSE_NUMBER", "")

    response = lambda_function.lambda_handler(lambda_event_missing_house_path, None)

    assert response["statusCode"] == 400
    assert "Missing required path parameter: housenumber" in response["body"]
    mock_create_fetcher.assert_not_called()


def test_lambda_handler_fetch_fail(mocker, lambda_event_path_params):
    """Test error response if fetcher returns None."""
    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    mock_generate_cal = mocker.patch('lambda_function.generate_calendar_object')
    mock_fetcher = MagicMock(); mock_fetcher.get_bin_dates.return_value = None; mock_create_fetcher.return_value = mock_fetcher

    response = lambda_function.lambda_handler(lambda_event_path_params, None)

    mock_fetcher.get_bin_dates.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE)
    mock_generate_cal.assert_not_called()
    assert response["statusCode"] == 404; assert "Could not find bin schedule" in response["body"]


def test_lambda_handler_calendar_gen_fail(mocker, lambda_event_path_params):
    """Test error response if calendar generation fails."""
    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    mock_generate_cal = mocker.patch('lambda_function.generate_calendar_object')
    mock_fetcher = MagicMock(); mock_fetcher.get_bin_dates.return_value = TEST_FETCHER_RESULT; mock_create_fetcher.return_value = mock_fetcher
    mock_generate_cal.side_effect = ValueError("Test calendar generation error")

    response = lambda_function.lambda_handler(lambda_event_path_params, None)

    mock_generate_cal.assert_called_once_with(TEST_FETCHER_RESULT)
    assert response["statusCode"] == 500; assert "Internal server error generating calendar data" in response["body"]


def test_lambda_handler_use_env_vars(mocker, lambda_event_env_vars):
    """Test environment variables used when path parameters are missing."""
    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    mock_generate_cal = mocker.patch('lambda_function.generate_calendar_object')
    mock_fetcher = MagicMock(); mock_fetcher.get_bin_dates.return_value = TEST_FETCHER_RESULT; mock_create_fetcher.return_value = mock_fetcher
    mock_cal_obj = MagicMock(spec=Calendar); mock_cal_obj.to_ical.return_value = MOCK_CAL_BYTES; mock_generate_cal.return_value = mock_cal_obj

    response = lambda_function.lambda_handler(lambda_event_env_vars, None)

    mock_create_fetcher.assert_called_once_with(source=mocker.ANY, use_cache=False)
    mock_fetcher.get_bin_dates.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE) # From env vars set in fixture
    mock_generate_cal.assert_called_once_with(TEST_FETCHER_RESULT)
    mock_cal_obj.to_ical.assert_called_once()
    assert response["statusCode"] == 200
    expected_body = base64.b64encode(MOCK_CAL_BYTES).decode('utf-8')
    assert response["body"] == expected_body


def test_lambda_handler_mixed_sources(mocker, lambda_event_mixed_sources):
    """Test path parameter precedence for postcode and env var for housenumber."""
    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    mock_generate_cal = mocker.patch('lambda_function.generate_calendar_object')
    mock_fetcher = MagicMock(); mock_fetcher.get_bin_dates.return_value = TEST_FETCHER_RESULT; mock_create_fetcher.return_value = mock_fetcher
    mock_cal_obj = MagicMock(spec=Calendar); mock_cal_obj.to_ical.return_value = MOCK_CAL_BYTES; mock_generate_cal.return_value = mock_cal_obj

    response = lambda_function.lambda_handler(lambda_event_mixed_sources, None)

    # TEST_POSTCODE from path, TEST_HOUSE from env (set in fixture)
    mock_fetcher.get_bin_dates.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE)
    mock_generate_cal.assert_called_once_with(TEST_FETCHER_RESULT) # Added this assertion for completeness
    mock_cal_obj.to_ical.assert_called_once()
    assert response["statusCode"] == 200
    expected_body = base64.b64encode(MOCK_CAL_BYTES).decode('utf-8')
    assert response["body"] == expected_body

# --- New Test Cases for Environment Variable Fallback ---

def test_lambda_handler_house_number_from_env(mocker, monkeypatch):
    """Test 200 when housenumber is from env, postcode from path."""
    event = {"pathParameters": {"postcode": TEST_POSTCODE}}  # housenumber missing from path
    env_house_number = "11"

    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    mock_generate_cal = mocker.patch('lambda_function.generate_calendar_object')
    mock_fetcher = MagicMock()
    mock_fetcher.get_bin_dates.return_value = TEST_FETCHER_RESULT
    mock_create_fetcher.return_value = mock_fetcher
    mock_cal_obj = MagicMock(spec=Calendar); mock_cal_obj.to_ical.return_value = MOCK_CAL_BYTES
    mock_generate_cal.return_value = mock_cal_obj

    monkeypatch.delenv("MY_POSTCODE", raising=False) # Ensure MY_POSTCODE is not set
    monkeypatch.setenv("MY_HOUSE_NUMBER", env_house_number)
    
    response = lambda_function.lambda_handler(event, None)

    assert response["statusCode"] == 200
    mock_create_fetcher.assert_called_once_with(source=mocker.ANY, use_cache=False)
    mock_fetcher.get_bin_dates.assert_called_once_with(TEST_POSTCODE, env_house_number)
    mock_generate_cal.assert_called_once_with(TEST_FETCHER_RESULT)
    expected_body = base64.b64encode(MOCK_CAL_BYTES).decode('utf-8')
    assert response["body"] == expected_body
    assert response["headers"]["Content-Type"] == "text/calendar"


def test_lambda_handler_postcode_from_env(mocker, monkeypatch):
    """Test 200 when postcode is from env, housenumber from path."""
    event = {"pathParameters": {"housenumber": TEST_HOUSE}}  # postcode missing from path
    env_postcode = "ENV1 1PC"

    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    mock_generate_cal = mocker.patch('lambda_function.generate_calendar_object')
    mock_fetcher = MagicMock()
    mock_fetcher.get_bin_dates.return_value = TEST_FETCHER_RESULT
    mock_create_fetcher.return_value = mock_fetcher
    mock_cal_obj = MagicMock(spec=Calendar); mock_cal_obj.to_ical.return_value = MOCK_CAL_BYTES
    mock_generate_cal.return_value = mock_cal_obj

    monkeypatch.delenv("MY_HOUSE_NUMBER", raising=False) # Ensure MY_HOUSE_NUMBER is not set
    monkeypatch.setenv("MY_POSTCODE", env_postcode)

    response = lambda_function.lambda_handler(event, None)

    assert response["statusCode"] == 200
    mock_create_fetcher.assert_called_once_with(source=mocker.ANY, use_cache=False)
    mock_fetcher.get_bin_dates.assert_called_once_with(env_postcode, TEST_HOUSE)
    mock_generate_cal.assert_called_once_with(TEST_FETCHER_RESULT)
    expected_body = base64.b64encode(MOCK_CAL_BYTES).decode('utf-8')
    assert response["body"] == expected_body


def test_lambda_handler_both_params_from_env(mocker, monkeypatch):
    """Test 200 when both postcode and housenumber are from env."""
    event = {"pathParameters": {}}  # Neither in path
    env_postcode = "ENV2 2PC"
    env_house_number = "22"

    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    mock_generate_cal = mocker.patch('lambda_function.generate_calendar_object')
    mock_fetcher = MagicMock()
    mock_fetcher.get_bin_dates.return_value = TEST_FETCHER_RESULT
    mock_create_fetcher.return_value = mock_fetcher
    mock_cal_obj = MagicMock(spec=Calendar); mock_cal_obj.to_ical.return_value = MOCK_CAL_BYTES
    mock_generate_cal.return_value = mock_cal_obj

    monkeypatch.setenv("MY_POSTCODE", env_postcode)
    monkeypatch.setenv("MY_HOUSE_NUMBER", env_house_number)

    response = lambda_function.lambda_handler(event, None)

    assert response["statusCode"] == 200
    mock_create_fetcher.assert_called_once_with(source=mocker.ANY, use_cache=False)
    mock_fetcher.get_bin_dates.assert_called_once_with(env_postcode, env_house_number)
    mock_generate_cal.assert_called_once_with(TEST_FETCHER_RESULT)
    expected_body = base64.b64encode(MOCK_CAL_BYTES).decode('utf-8')
    assert response["body"] == expected_body

# --- End of New Test Cases ---

def test_lambda_handler_both_missing(mocker):
    """Test error when parameters missing in both sources."""
    event = {"pathParameters": None}
    mocker.patch.dict(os.environ, {}, clear=True)  # Clear all env vars
    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')

    response = lambda_function.lambda_handler(event, None)

    assert response["statusCode"] == 400
    assert "Missing required parameters: postcode and housenumber" in response["body"]
    mock_create_fetcher.assert_not_called()

def test_lambda_handler_ical_encode_fail(mocker, lambda_event_path_params):
    """Test error response if calendar serialization/encoding fails."""
    mock_create_fetcher = mocker.patch('lambda_function.create_fetcher')
    mock_generate_cal = mocker.patch('lambda_function.generate_calendar_object')
    mock_fetcher = MagicMock(); mock_fetcher.get_bin_dates.return_value = TEST_FETCHER_RESULT; mock_create_fetcher.return_value = mock_fetcher
    mock_cal_obj = MagicMock(spec=Calendar)
    mock_cal_obj.to_ical.side_effect = TypeError("Test serialization error")
    mock_generate_cal.return_value = mock_cal_obj

    response = lambda_function.lambda_handler(lambda_event_path_params, None)

    mock_cal_obj.to_ical.assert_called_once()
    assert response["statusCode"] == 500; assert "Internal server error preparing calendar data" in response["body"]
