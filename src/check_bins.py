import logging
import sys
import argparse
import json
import os
from dataclasses import asdict
from dotenv import load_dotenv

# Use absolute imports from the 'src' package namespace
from src.data_fetchers.fetcher_factory import create_fetcher
from src.calendar_generator import create_ics_file
from src.google_calendar import GoogleCalendarExporter # Import the exporter
# Import data model for type hint if desired
from src.data_models import FetcherResult
from typing import Optional

# Setup code (paths, logging) remains the same...
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()
DEFAULT_POSTCODE = os.environ.get("MY_POSTCODE")
DEFAULT_HOUSE_NUMBER = os.environ.get("MY_HOUSE_NUMBER") # Can be None
LOG_FILE = os.path.join(project_root, 'error.log')
log_configured = False
if not log_configured: # Simplified logging setup
    log_dir = os.path.dirname(LOG_FILE); os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s', filename=LOG_FILE, filemode='a')
    console_handler = logging.StreamHandler(sys.stderr); console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s: %(message)s'); console_handler.setFormatter(formatter)
    if not logging.getLogger('').hasHandlers(): logging.getLogger('').addHandler(console_handler)
    log_configured = True
logger = logging.getLogger(__name__)

def main(argv=None):
    parser = argparse.ArgumentParser(description="Check bin collection schedule.")
    parser.add_argument("--postcode", "-p", help="Postcode (Defaults to MY_POSTCODE env var).")
    parser.add_argument("--house-number", "-n", type=str, default=DEFAULT_HOUSE_NUMBER, help="House number/name (Optional, defaults to MY_HOUSE_NUMBER env var. If omitted, a random address for the postcode is used).")
    # FIX: Change cache flags to have cache OFF by default
    parser.add_argument("--use-cache", "-c", action="store_true", help="Enable cache usage (checks cache first). Default is OFF.")
    parser.set_defaults(use_cache=False) # Cache is now OFF by default

    parser.add_argument("--upload-google", "-g", action="store_true", help="Upload schedule to Google Calendar.")
    parser.add_argument("--save-ics", "-i", action="store_true", help="Save schedule to ICS file.")
    parser.add_argument("--source", default="gateshead", choices=["gateshead"], help="Data source.")
    args = parser.parse_args(argv)

    postcode = args.postcode if args.postcode else DEFAULT_POSTCODE
    house_number: Optional[str] = args.house_number

    # Argument Validation (remains same)
    if not postcode: print("Error: Postcode required.", file=sys.stderr); sys.exit(1)

    save_ics = args.save_ics
    upload_google = args.upload_google # Get the flag value

    # --- Use the factory to get the fetcher ---
    log_info_hn = f" for house number '{house_number}'" if house_number else " (random house number)"
    cache_status = "enabled" if args.use_cache else "disabled"
    logger.info(f"Checking bins for postcode '{postcode}'{log_info_hn} using source '{args.source}' (Cache: {cache_status})") # Log cache status
    try:
        # Pass the use_cache flag value from args
        fetcher = create_fetcher(source=args.source, use_cache=args.use_cache)
    except ValueError as e:
        logger.error(f"Fetcher creation failed: {e}", exc_info=True); print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)

    # --- Call the fetcher's method ---
    try:
        result: Optional[FetcherResult] = fetcher.get_bin_dates(postcode, house_number)

        if result:
            logger.info(f"\n--- Bin Collection Schedule for {result.address_text} ---")
            if result.collections:
                print(json.dumps(result.collections_as_dicts(), indent=4))
            else:
                logger.info("No upcoming collections found for this address.")
                print("No upcoming collections found.")
            logger.info("---------------------------------------------------")

            # Save to ICS if requested
            if save_ics:
                if result.collections:
                    logger.info("Saving schedule to ICS file...")
                    create_ics_file(result)
                    logger.info("ICS file generation complete.")
                else:
                    logger.info("Skipping ICS file generation (no collections).")

            # Upload to Google Calendar if requested
            if upload_google:
                if result.collections:
                    logger.info("Uploading schedule to Google Calendar...")
                    try:
                        # Instantiate the exporter (credentials need setup)
                        google_exporter = GoogleCalendarExporter()
                        upload_success = google_exporter.upload_events(result)
                        if upload_success:
                            logger.info("Google Calendar upload complete.")
                        else:
                            # Specific errors logged within upload_events
                            logger.error("Google Calendar upload finished with errors.")
                            # Decide if this should be a fatal error
                            # sys.exit(1)
                    except Exception as e:
                        # Catch potential errors during exporter init or general upload issues
                        logger.error(f"Google Calendar upload failed: {e}", exc_info=True)
                        print(f"\nERROR: Google Calendar upload failed. Check {LOG_FILE}.", file=sys.stderr)
                        # Decide if this should be a fatal error
                        # sys.exit(1)
                else:
                    logger.info("Skipping Google Calendar upload (no collections).")
        else:
            # Handle case where fetcher returned None (failure)
            log_msg = f"\nFailed to fetch schedule for postcode '{postcode}'{log_info_hn}."
            logger.error(log_msg + " Check logs/details.")
            print(f"\nERROR: {log_msg} Check address details and consult error.log.", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        # Catch any other unexpected errors during the main fetch/process block
        logger.error(f"Unexpected error during fetch/processing: {e}", exc_info=True)
        print(f"\nUnexpected error. Check {LOG_FILE}.", file=sys.stderr)
        sys.exit(1)

    logger.info("\nCheck complete.")


if __name__ == "__main__":
    main()