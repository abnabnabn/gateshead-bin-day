# Renamed from lambda.py to avoid keyword clash

import json
import os
import logging
import base64
import sys
from typing import Dict, Any, Optional

# Add src directory to path if needed for Lambda deployment structure
# Assuming lambda_function.py is in the project root alongside src/
sys.path.insert(0, os.path.dirname(__file__)) # Add project root

try:
    from src.data_fetchers.fetcher_factory import create_fetcher
    from src.calendar_generator import generate_calendar_object
    from src.data_models import FetcherResult
except ImportError as e:
    print(f"ERROR: Failed to import project modules. Ensure script is run from project root or PYTHONPATH is set. Error: {e}")
    FetcherResult = None; create_fetcher = None; generate_calendar_object = None


# --- Basic Lambda Logging Setup ---
log_level_str = os.environ.get('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logger = logging.getLogger(__name__) # Use __name__ for logger
if not logging.getLogger().hasHandlers():
     logging.basicConfig(level=log_level, stream=sys.stdout, format='%(levelname)s:%(name)s: %(message)s')
else: logger.setLevel(log_level)


# --- Helper Function ---
def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    logger.error(f"Returning error {status_code}: {message}")
    return {"statusCode": status_code, "headers": {"Content-Type": "application/json"}, "body": json.dumps({"error": message}), "isBase64Encoded": False}

# --- Lambda Handler ---
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    handler_logger = logging.getLogger(f"{__name__}.lambda_handler")
    handler_logger.info(f"Received event: {json.dumps(event)}")

    if not create_fetcher or not generate_calendar_object:
         return create_error_response(500, "Internal configuration error: Core modules not loaded.")

    # 1. Parse Input Parameters with priority: pathParameters > environment variables
    params = event.get("pathParameters", {})
    if params is None: params = {}
    
    # Get postcode with priority: pathParameters > environment variables
    postcode = params.get("postcode")
    if not postcode:
        postcode = os.environ.get("MY_POSTCODE")
    
    # Get housenumber with priority: pathParameters > environment variables
    house_number = params.get("housenumber")
    if not house_number:
        house_number = os.environ.get("MY_HOUSE_NUMBER")
    
    # Validate required parameters after checking both sources
    if not postcode and not house_number:
        return create_error_response(400, "Missing required parameters: postcode and housenumber")
    elif not postcode:
        return create_error_response(400, "Missing required path parameter: postcode")
    elif not house_number:
        return create_error_response(400, "Missing required path parameter: housenumber")

    # 2. Create Fetcher (Cache is always OFF for Lambda)
    fetcher_source = os.environ.get("FETCHER_SOURCE", "gateshead")
    handler_logger.info(f"Using source '{fetcher_source}', cache: False")
    try: fetcher = create_fetcher(source=fetcher_source, use_cache=False)
    except ValueError as e: return create_error_response(400, f"Invalid configuration: {e}")
    except Exception as e: handler_logger.exception("Error creating fetcher"); return create_error_response(500, f"Internal server error creating fetcher.")

    # 3. Get Bin Data
    handler_logger.info(f"Fetching bin dates for postcode '{postcode}', house number '{house_number}'")
    try: result: Optional[FetcherResult] = fetcher.get_bin_dates(postcode, house_number)
    except Exception as e: handler_logger.exception(f"Error fetching bin dates"); return create_error_response(502, f"Error fetching data from upstream source.")
    if not result: return create_error_response(404, f"Could not find bin schedule for the specified address.")
    if not result.collections: return create_error_response(404, f"Found address '{result.address_text}' but no upcoming collections.")

    # 4. Generate Calendar Object
    try:
        handler_logger.info(f"Generating Calendar object...")
        cal = generate_calendar_object(result)
        if not cal: raise ValueError("Calendar object generation returned None")
        handler_logger.info(f"Successfully generated Calendar object.")
    except Exception as e: handler_logger.exception("Error generating Calendar object"); return create_error_response(500, "Internal server error generating calendar data.")

    # 5. Serialize Calendar Object and Encode
    try:
        ics_content_bytes = cal.to_ical()
        handler_logger.info(f"Serialized calendar object to {len(ics_content_bytes)} bytes.")
        encoded_body = base64.b64encode(ics_content_bytes).decode('utf-8')
        handler_logger.info(f"Base64 encoded body length: {len(encoded_body)}")
    except Exception as e: handler_logger.exception(f"Error serializing or encoding Calendar object"); return create_error_response(500, "Internal server error preparing calendar data.")

    # 6. Format Success Response
    handler_logger.info("Successfully generated and encoded ICS, returning response.")
    response = {"statusCode": 200, "headers": { "Content-Type": "text/calendar", "Content-Disposition": 'attachment; filename="bin_collections.ics"' }, "body": encoded_body, "isBase64Encoded": True }
    return response

# Example local test block
if __name__ == '__main__':
    logger.info("Testing lambda handler locally (using command line args or environment variables for defaults)...")
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Test Lambda handler with optional command line parameters')
    parser.add_argument('--postcode', help='Postcode for testing')
    parser.add_argument('--housenumber', help='House number for testing')
    args = parser.parse_args()
    
    # Get parameters with priority: command line args > environment variables
    postcode = args.postcode if args.postcode else os.environ.get("MY_POSTCODE")
    house_number = args.housenumber if args.housenumber else os.environ.get("MY_HOUSE_NUMBER")
    
    if not postcode or not house_number:
        logger.error("Error: Postcode and house number must be provided via command line args or environment variables.")
        sys.exit(1)
    
    test_event = {"pathParameters": {"postcode": postcode, "housenumber": house_number}}
    logger.info(f"Using test event: {json.dumps(test_event)}")
    result = lambda_handler(test_event, None)
    logger.info("\nLambda Handler Response:")
    if result.get("isBase64Encoded") and len(result.get("body", "")) > 100:
        result_to_print = result.copy()
        result_to_print["body"] = result_to_print["body"][:100] + "... (truncated)"
        logger.info(json.dumps(result_to_print, indent=2))
    else:
        logger.info(json.dumps(result, indent=2))