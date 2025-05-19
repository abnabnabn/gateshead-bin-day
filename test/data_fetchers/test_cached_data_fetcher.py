import pytest
import os
import sys
import json
from unittest.mock import MagicMock, call # Keep MagicMock/call for underlying fetcher mock

# Update sys.path to include the project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Imports for the class under test and the base class
from src.data_fetchers.cached_data_fetcher import CachedBinData
from src.data_fetchers.base_fetcher import BinDataFetcher
# Import the data model to create test instances
from src.data_models import BinCollection, FetcherResult # Import FetcherResult
# Import constants and helpers FROM the module under test now
from src.data_fetchers.cached_data_fetcher import CACHE_DIR, _get_cache_filename

# Define constants for testing
TEST_POSTCODE = "XX9 9XX"
TEST_HOUSE_NUMBER = "123"
TEST_ADDRESS = f"{TEST_HOUSE_NUMBER} Cache Test Lane, {TEST_POSTCODE}"
# Use BinCollection for test data
TEST_SCHEDULE_OBJS = [BinCollection(date="1 Monday", month="July", bin_type="Test Bin", bin_colour="rainbow", bin_link="/test")]
# Represent the data as it would be in the JSON cache file
TEST_SCHEDULE_DICT = [{"date": "1 Monday", "month": "July", "bin_type": "Test Bin", "bin_colour": "rainbow", "bin_link": "/test"}]
# Expected FetcherResult object
EXPECTED_RESULT_OBJ = FetcherResult(address_text=TEST_ADDRESS, collections=TEST_SCHEDULE_OBJS)
# Expected cache dictionary format
EXPECTED_CACHE_DICT = {"address_text": TEST_ADDRESS, "schedule": TEST_SCHEDULE_DICT}


# --- Fixture for setting up mocks and cleaning cache ---
@pytest.fixture
def mock_fetcher_and_cache(mocker):
    mock_underlying = MagicMock(spec=BinDataFetcher)
    # Mock load/save within the cached_data_fetcher module
    mock_load = mocker.patch('src.data_fetchers.cached_data_fetcher.load_schedule_from_cache')
    mock_save = mocker.patch('src.data_fetchers.cached_data_fetcher.save_schedule_to_cache')
    cache_file = _get_cache_filename(TEST_POSTCODE, TEST_HOUSE_NUMBER)
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    if os.path.exists(cache_file): os.remove(cache_file)
    yield mock_underlying, mock_load, mock_save
    if os.path.exists(cache_file): os.remove(cache_file)


def test_cache_hit(mock_fetcher_and_cache):
    """Test cache hit scenario."""
    mock_underlying, mock_load_cache, mock_save_cache = mock_fetcher_and_cache
    # FIX: load_schedule_from_cache now returns a single dict or None
    mock_load_cache.return_value = EXPECTED_CACHE_DICT
    cached_fetcher = CachedBinData(mock_underlying)
    result = cached_fetcher.get_bin_dates(TEST_POSTCODE, TEST_HOUSE_NUMBER) # Get single result object

    mock_load_cache.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE_NUMBER)
    mock_underlying.get_bin_dates.assert_not_called()
    mock_save_cache.assert_not_called()
    # Assert the reconstructed object matches the expected object
    assert result == EXPECTED_RESULT_OBJ


def test_cache_miss_fetch_success(mock_fetcher_and_cache, mocker): # Added mocker
    """Test cache miss followed by successful fetch from underlying fetcher."""
    mock_underlying, mock_load_cache, mock_save_cache = mock_fetcher_and_cache
    ANY = mocker.ANY # Get ANY from mocker

    mock_load_cache.return_value = None # Simulate cache miss
    # Underlying fetcher returns the FetcherResult object
    mock_underlying.get_bin_dates.return_value = EXPECTED_RESULT_OBJ

    cached_fetcher = CachedBinData(mock_underlying)
    result = cached_fetcher.get_bin_dates(TEST_POSTCODE, TEST_HOUSE_NUMBER) # Get single result object

    mock_load_cache.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE_NUMBER)
    mock_underlying.get_bin_dates.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE_NUMBER)
    # FIX: save_schedule_to_cache should be called with postcode, house_number, and the FetcherResult object
    mock_save_cache.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE_NUMBER, EXPECTED_RESULT_OBJ)
    # Final result should be the FetcherResult object
    assert result == EXPECTED_RESULT_OBJ


def test_cache_miss_fetch_failure(mock_fetcher_and_cache):
    """Test cache miss followed by failure from underlying fetcher."""
    mock_underlying, mock_load_cache, mock_save_cache = mock_fetcher_and_cache
    mock_load_cache.return_value = None # Simulate cache miss
    # FIX: Underlying fetcher returns None on failure
    mock_underlying.get_bin_dates.return_value = None

    cached_fetcher = CachedBinData(mock_underlying)
    result = cached_fetcher.get_bin_dates(TEST_POSTCODE, TEST_HOUSE_NUMBER) # Get single result

    mock_load_cache.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE_NUMBER)
    mock_underlying.get_bin_dates.assert_called_once_with(TEST_POSTCODE, TEST_HOUSE_NUMBER)
    # FIX: save_schedule_to_cache should NOT be called if fetch failed
    mock_save_cache.assert_not_called()
    assert result is None


def test_init_with_invalid_fetcher():
    with pytest.raises(TypeError): CachedBinData("not a fetcher")