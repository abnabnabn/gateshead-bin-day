import pytest
import os
import sys
import json
from unittest.mock import MagicMock, patch

# Adjust path to add project root so src imports work
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.check_bins import main as check_bins_main
# Import the specific variables we might need to assert against or modify
import src.check_bins # To use for setattr
from src.check_bins import LOG_FILE as CHECK_BINS_LOG_FILE # For asserting error messages
from src.data_models import FetcherResult, BinCollection

# Helper to simulate command line arguments for check_bins_main
def run_main_with_args(capsys, monkeypatch, args_list, expected_exit_code=None):
    """
    Runs the check_bins_main function with specified arguments and environment.
    Asserts exit code if provided.
    Returns captured stdout and stderr.
    """
    if expected_exit_code is not None:
        with pytest.raises(SystemExit) as e:
            check_bins_main(argv=args_list)
        assert e.value.code == expected_exit_code
    else:
        check_bins_main(argv=args_list)

    captured = capsys.readouterr()
    return captured.out, captured.err

@pytest.fixture(autouse=True)
def mock_load_dotenv(monkeypatch):
    """Mocks load_dotenv to prevent loading real .env files."""
    monkeypatch.setattr('src.check_bins.load_dotenv', lambda: None)

@pytest.fixture(autouse=True)
def isolated_module_defaults_and_os_env(monkeypatch):
    """
    Ensures a clean state for each test by:
    1. Clearing relevant OS environment variables.
    2. Resetting the module-level DEFAULT_POSTCODE and DEFAULT_HOUSE_NUMBER
       in check_bins.py to None, simulating an environment where these
       were not set when check_bins.py was imported.
    """
    # Clear OS environment variables
    monkeypatch.delenv("MY_POSTCODE", raising=False)
    monkeypatch.delenv("MY_HOUSE_NUMBER", raising=False)
    monkeypatch.delenv("GOOGLE_CALENDAR_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    # Add any other potentially interfering OS env vars here

    # Reset module-level defaults in check_bins.py
    # This simulates these env vars not being set at check_bins.py import time.
    # We need to do this because check_bins.py reads os.environ at import time.
    monkeypatch.setattr(src.check_bins, 'DEFAULT_POSTCODE', None)
    monkeypatch.setattr(src.check_bins, 'DEFAULT_HOUSE_NUMBER', None)


@pytest.fixture(autouse=True)
def mock_dependencies(mocker):
    """Mocks external dependencies using mocker."""
    mock_fetcher_instance = MagicMock()
    mock_create_fetcher = mocker.patch('src.check_bins.create_fetcher', return_value=mock_fetcher_instance)

    mock_exporter_instance = MagicMock()
    mock_google_calendar_exporter_class = mocker.patch('src.check_bins.GoogleCalendarExporter', return_value=mock_exporter_instance)

    mock_create_ics_file = mocker.patch('src.check_bins.create_ics_file')

    return mock_create_fetcher, mock_fetcher_instance, mock_google_calendar_exporter_class, mock_exporter_instance, mock_create_ics_file

# --- Tests ---

def test_missing_postcode_arg_and_env(capsys, monkeypatch, mock_dependencies):
    """Test script exits if postcode is not provided via arg or MY_POSTCODE (at import)."""
    # isolated_module_defaults_and_os_env ensures src.check_bins.DEFAULT_POSTCODE is None
    mock_create_fetcher, _, _, _, _ = mock_dependencies
    _, err = run_main_with_args(capsys, monkeypatch, ["--house-number", "22"], expected_exit_code=1)
    # The error message includes the specific format from check_bins.py
    assert "Error: Postcode required." in err
    mock_create_fetcher.assert_not_called() # Ensure fetcher factory is not called

def test_postcode_from_env_var(capsys, monkeypatch, mock_dependencies):
    """Test script uses MY_POSTCODE env var if --postcode arg is not provided."""
    # Simulate MY_POSTCODE="ENV1 1PC" being set at import time of check_bins.py
    # This is handled by setting the module attribute directly in isolated_module_defaults_and_os_env.
    monkeypatch.setattr(src.check_bins, 'DEFAULT_POSTCODE', 'ENV1 1PC')

    mock_create_fetcher, mock_fetcher, _, _, _ = mock_dependencies
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="Env Address", collections=[])

    run_main_with_args(capsys, monkeypatch, []) # No args, should use the modified DEFAULT_POSTCODE

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("ENV1 1PC", None)

def test_house_number_from_env_var(capsys, monkeypatch, mock_dependencies):
    """Test script uses MY_HOUSE_NUMBER env var if --house-number arg is not provided."""
    # args.postcode will be "NE1 1AA"
    # Simulate MY_HOUSE_NUMBER="101" being set at import time of check_bins.py
    monkeypatch.setattr(src.check_bins, 'DEFAULT_HOUSE_NUMBER', '101')
    # DEFAULT_POSTCODE remains None from fixture, but arg "-p NE1 1AA" is used.

    mock_create_fetcher, mock_fetcher, _, _, _ = mock_dependencies
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="Env Address HN", collections=[])

    run_main_with_args(capsys, monkeypatch, ["-p", "NE1 1AA"]) # Postcode from arg

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    # House number should come from env because arg is not provided
    mock_fetcher.get_bin_dates.assert_called_once_with("NE1 1AA", "101")

def test_postcode_and_house_number_from_args(capsys, monkeypatch, mock_dependencies):
    """Test script uses --postcode and --house-number args."""
    # isolated_module_defaults_and_os_env ensures DEFAULT_POSTCODE and DEFAULT_HOUSE_NUMBER are None,
    # so they won't interfere when args are provided.
    mock_create_fetcher, mock_fetcher, _, _, _ = mock_dependencies
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="Arg Address", collections=[])

    run_main_with_args(capsys, monkeypatch, ["-p", "ARG1 1PA", "-n", "22A"])

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("ARG1 1PA", "22A")

def test_fetch_success_no_collections_output(capsys, monkeypatch, mock_dependencies):
    """Test successful fetch with no collections, verifies output."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    mock_create_fetcher, mock_fetcher, _, _, _ = mock_dependencies
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="Test Address", collections=[])

    out, err = run_main_with_args(capsys, monkeypatch, ["-p", "NE1"])

    assert "No upcoming collections found." in out
    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("NE1", None)

def test_fetch_success_with_collections_output(capsys, monkeypatch, mock_dependencies):
    """Test successful fetch with collections, verifies JSON output."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    mock_create_fetcher, mock_fetcher, _, _, _ = mock_dependencies
    collections = [
        BinCollection(date="2024-01-10", month="Jan", bin_type="Recycling", bin_colour="Blue", bin_link=None),
        BinCollection(date="2024-01-17", month="Jan", bin_type="General Waste", bin_colour="Green", bin_link=None)
    ]
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="Test Address", collections=collections)

    out, err = run_main_with_args(capsys, monkeypatch, ["-p", "NE1"])

    assert "No upcoming collections found." not in out
    try:
        output_json = json.loads(out)
        assert len(output_json) == 2
        assert output_json[0]["bin_type"] == "Recycling"
        assert output_json[1]["bin_colour"] == "Green"
    except json.JSONDecodeError:
        pytest.fail(f"Output was not valid JSON: {out}")

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("NE1", None)

def test_use_cache_true(capsys, monkeypatch, mock_dependencies):
    """Test --use-cache flag enables cache."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    mock_create_fetcher, mock_fetcher, _, _, _ = mock_dependencies
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="Cache Address", collections=[])

    run_main_with_args(capsys, monkeypatch, ["-p", "CACHE1", "--use-cache"])

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=True)
    mock_fetcher.get_bin_dates.assert_called_once_with("CACHE1", None)

def test_use_cache_false_default(capsys, monkeypatch, mock_dependencies):
    """Test cache is disabled by default."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    mock_create_fetcher, mock_fetcher, _, _, _ = mock_dependencies
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="NoCache Address", collections=[])

    run_main_with_args(capsys, monkeypatch, ["-p", "NOCACHE1"])

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default
    mock_fetcher.get_bin_dates.assert_called_once_with("NOCACHE1", None)

def test_save_ics_with_collections(capsys, monkeypatch, mock_dependencies):
    """Test --save-ics calls create_ics_file when collections exist."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    mock_create_fetcher, mock_fetcher, _, _, mock_create_ics_file = mock_dependencies
    collections = [BinCollection(date="d", month="m", bin_type="t", bin_colour="c", bin_link=None)]
    fetch_result = FetcherResult(address_text="ICS Address", collections=collections)
    mock_fetcher.get_bin_dates.return_value = fetch_result

    run_main_with_args(capsys, monkeypatch, ["-p", "ICS1", "--save-ics"])

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("ICS1", None)
    mock_create_ics_file.assert_called_once_with(fetch_result)

def test_save_ics_no_collections(capsys, monkeypatch, mock_dependencies):
    """Test --save-ics does not call create_ics_file when no collections."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    mock_create_fetcher, mock_fetcher, _, _, mock_create_ics_file = mock_dependencies
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="NoICS Address", collections=[])

    run_main_with_args(capsys, monkeypatch, ["-p", "NOICS1", "--save-ics"])

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("NOICS1", None)
    mock_create_ics_file.assert_not_called()

def test_upload_google_with_collections(capsys, monkeypatch, mock_dependencies):
    """Test --upload-google calls GoogleCalendarExporter when collections exist."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "test_cal_id")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "dummy_creds.json")

    mock_create_fetcher, mock_fetcher, mock_exporter_class, mock_exporter_instance, _ = mock_dependencies

    collections = [BinCollection(date="d", month="m", bin_type="t", bin_colour="c", bin_link=None)]
    fetch_result = FetcherResult(address_text="Google Address", collections=collections)
    mock_fetcher.get_bin_dates.return_value = fetch_result
    mock_exporter_instance.upload_events.return_value = True

    run_main_with_args(capsys, monkeypatch, ["-p", "GOOGLE1", "--upload-google"])

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("GOOGLE1", None)
    mock_exporter_class.assert_called_once()
    mock_exporter_instance.upload_events.assert_called_once_with(fetch_result)

def test_upload_google_no_collections(capsys, monkeypatch, mock_dependencies):
    """Test --upload-google does not call GoogleCalendarExporter when no collections."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "test_cal_id")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "dummy_creds.json")

    mock_create_fetcher, mock_fetcher, mock_exporter_class, mock_exporter_instance, _ = mock_dependencies
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="NoGoogle Address", collections=[])

    run_main_with_args(capsys, monkeypatch, ["-p", "NOGOOGLE1", "--upload-google"])

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("NOGOOGLE1", None)
    mock_exporter_class.assert_not_called()
    mock_exporter_instance.upload_events.assert_not_called()

def test_upload_google_missing_cal_id(capsys, monkeypatch, mock_dependencies):
    """Test --upload-google fails gracefully if GOOGLE_CALENDAR_ID is missing."""
    # isolated_module_defaults_and_os_env ensures defaults are None and GOOGLE_CALENDAR_ID is cleared. Postcode from arg.
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "dummy_creds.json")

    mock_create_fetcher, mock_fetcher, mock_exporter_class, mock_exporter_instance, _ = mock_dependencies
    # Simulate GoogleCalendarExporter raising an error if init fails due to missing CAL_ID
    mock_exporter_class.side_effect = ValueError("Missing Google Calendar ID")

    collections = [BinCollection(date="d", month="m", bin_type="t", bin_colour="c", bin_link=None)]
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="GoogleFail Address", collections=collections)

    out, err = run_main_with_args(capsys, monkeypatch, ["-p", "GOOGLEFAIL1", "--upload-google"])

    # check_bins.py prints: print(f"\nERROR: Google Calendar upload failed. Check {LOG_FILE}.", file=sys.stderr)
    # It does NOT include the specific error {e} from the exporter init in the stderr print.
    expected_error_message_part = f"ERROR: Google Calendar upload failed. Check {CHECK_BINS_LOG_FILE}."
    assert expected_error_message_part in err

    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("GOOGLEFAIL1", None)
    mock_exporter_class.assert_called_once() # Attempt to create is made
    mock_exporter_instance.upload_events.assert_not_called()


def test_upload_google_exporter_init_fails(capsys, monkeypatch, mock_dependencies):
    """Test --upload-google when GoogleCalendarExporter instantiation fails with a general error."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "test_cal_id")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "invalid_creds.json")

    mock_create_fetcher, mock_fetcher, mock_exporter_class, mock_exporter_instance, _ = mock_dependencies
    mock_exporter_class.side_effect = Exception("Credentials error") # Simulate init failure

    collections = [BinCollection(date="d", month="m", bin_type="t", bin_colour="c", bin_link=None)]
    mock_fetcher.get_bin_dates.return_value = FetcherResult(address_text="GoogleInitFail", collections=collections)

    out, err = run_main_with_args(capsys, monkeypatch, ["-p", "GINITFAIL", "--upload-google"])

    # check_bins.py prints a generic message to stderr for this case:
    # print(f"\nERROR: Google Calendar upload failed. Check {LOG_FILE}.", file=sys.stderr)
    # The specific "Credentials error" is logged but not printed to stderr.
    expected_error_message_part = f"ERROR: Google Calendar upload failed. Check {CHECK_BINS_LOG_FILE}."
    assert expected_error_message_part in err
    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("GINITFAIL", None)
    mock_exporter_class.assert_called_once()
    mock_exporter_instance.upload_events.assert_not_called()


def test_upload_google_upload_events_returns_false(capsys, monkeypatch, mock_dependencies):
    """Test --upload-google when upload_events returns False."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "test_cal_id")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "dummy_creds.json")

    mock_create_fetcher, mock_fetcher, mock_exporter_class, mock_exporter_instance, _ = mock_dependencies

    collections = [BinCollection(date="d", month="m", bin_type="t", bin_colour="c", bin_link=None)]
    fetch_result = FetcherResult(address_text="GoogleUploadFalse", collections=collections)
    mock_fetcher.get_bin_dates.return_value = fetch_result
    mock_exporter_instance.upload_events.return_value = False # Simulate upload failure

    out, err = run_main_with_args(capsys, monkeypatch, ["-p", "GUPLOADFALSE", "--upload-google"])

    # The script logs "Google Calendar upload finished with errors." but doesn't print to stderr
    # for this specific case, nor does it exit.
    # So, we mainly check that the flow completed and methods were called.
    assert not err # No error output to stderr is expected for this path
    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("GUPLOADFALSE", None)
    mock_exporter_class.assert_called_once()
    mock_exporter_instance.upload_events.assert_called_once_with(fetch_result)

def test_fetcher_get_bin_dates_returns_none(capsys, monkeypatch, mock_dependencies):
    """Test main handles fetcher.get_bin_dates() returning None."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    mock_create_fetcher, mock_fetcher, _, _, _ = mock_dependencies
    mock_fetcher.get_bin_dates.return_value = None

    _, err = run_main_with_args(capsys, monkeypatch, ["-p", "FETCHFAIL"], expected_exit_code=1)

    # check_bins.py prints: print(f"\nERROR: {log_msg} Check address details and consult error.log.", file=sys.stderr)
    # log_msg is f"\nFailed to fetch schedule for postcode '{postcode}'{log_info_hn}."
    # log_info_hn will be " (random house number)" because house_number is None
    assert f"\nERROR: \nFailed to fetch schedule for postcode 'FETCHFAIL' (random house number). Check address details and consult error.log.\n" in err
    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("FETCHFAIL", None)

def test_create_fetcher_raises_value_error(capsys, monkeypatch, mock_dependencies):
    """Test main handles create_fetcher raising ValueError."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    mock_create_fetcher, _, _, _, _ = mock_dependencies
    mock_create_fetcher.side_effect = ValueError("Invalid source specified")

    # Pass a VALID source to argparse, so it doesn't exit first due to choices.
    # The mock_factory.side_effect will then be triggered when create_fetcher is called.
    _, err = run_main_with_args(capsys, monkeypatch, ["-p", "BADSOURCE", "--source", "gateshead"], expected_exit_code=1)

    # check_bins.py prints: print(f"ERROR: {e}", file=sys.stderr) where e is the ValueError.
    assert "ERROR: Invalid source specified" in err
    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False

def test_main_unexpected_error_in_fetch_block(capsys, monkeypatch, mock_dependencies):
    """Test main handles unexpected error during fetcher.get_bin_dates()."""
    # isolated_module_defaults_and_os_env ensures defaults are None. Postcode from arg.
    mock_create_fetcher, mock_fetcher, _, _, _ = mock_dependencies
    mock_fetcher.get_bin_dates.side_effect = Exception("Unexpected network issue")

    _, err = run_main_with_args(capsys, monkeypatch, ["-p", "UNEXPECTED"], expected_exit_code=1)

    # check_bins.py prints: print(f"\nUnexpected error. Check {LOG_FILE}.", file=sys.stderr)
    expected_error_message_part = f"\nUnexpected error. Check {CHECK_BINS_LOG_FILE}.\n"
    assert expected_error_message_part in err
    mock_create_fetcher.assert_called_once_with(source='gateshead', use_cache=False) # Default cache is False
    mock_fetcher.get_bin_dates.assert_called_once_with("UNEXPECTED", None)
