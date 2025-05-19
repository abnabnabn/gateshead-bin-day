from googleapiclient.discovery import build
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple
import logging
import os
import sys
import json
import pytz # Import pytz for timezone handling
from google.oauth2 import service_account

# Add project root to sys.path if needed
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Imports from the module being tested and the data model
from src.data_models import BinCollection, FetcherResult

logger = logging.getLogger(__name__)

class GoogleCalendarExporter:
    """Class to export bin collection data to Google Calendar."""

    def __init__(self, calendar_id: str = None, timezone: str = 'Europe/London'):
        """
        Initialize the Google Calendar exporter.

        Args:
            calendar_id: The ID of the Google Calendar to use. If not provided, will look for CALENDAR_ID environment variable.
            timezone: The timezone for the events
        """
        # Handle calendar_id: check parameter first, then environment variable
        if calendar_id is None:
            calendar_id = os.environ.get('BINS_GOOGLE_CALENDAR_ID')
        
        # Ensure calendar_id is provided
        if not calendar_id:
            raise ValueError("Calendar ID must be provided via parameter or 'BINS_GOOGLE_CALENDAR_ID' environment variable")
        
        self.calendar_id = calendar_id
        self.timezone = timezone
        self.tz = pytz.timezone(self.timezone) # Store timezone object
        self.service = self._build_service()

    def _build_service(self):
        """Build the Google Calendar service object."""
        try:
            # Credentials should be handled via environment variables or a secure method
            # See Google API Python Client library documentation for details
            # https://developers.google.com/calendar/api/quickstart/python
            # This placeholder assumes credentials are set up externally (e.g., ADC)
            credentials = self._get_credentials()
            service = build('calendar', 'v3', credentials=credentials, cache_discovery=False)
            logger.info("Google Calendar service built successfully.")
            return service
        except Exception as e:
            logger.error(f"Failed to build Google Calendar service: {e}", exc_info=True)
            # Depending on the application, you might want to raise this
            # or handle it gracefully (e.g., disable upload functionality)
            return None

    def _get_credentials(self):
        """Get Google Calendar API credentials using service account.
           Tries to load from a JSON string in BINS_GOOGLE_CREDENTIALS_JSON first,
           then falls back to a file path in BINS_GOOGLE_CREDENTIALS.
        """
        scopes = ['https://www.googleapis.com/auth/calendar']
        credentials = None

        # Option 1: Try to load from an environment variable containing the JSON string
        credentials_json_str = os.environ.get('BINS_GOOGLE_CREDENTIALS_JSON') # New environment variable name
        if credentials_json_str:
            try:
                info_dict = json.loads(credentials_json_str)
                credentials = service_account.Credentials.from_service_account_info(
                    info_dict, scopes=scopes)
                logger.info("Credentials loaded successfully from BINS_GOOGLE_CREDENTIALS_JSON environment variable.")
                return credentials
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from BINS_GOOGLE_CREDENTIALS_JSON: {e}", exc_info=True)
                # Fall through to try the file path method if JSON parsing fails, or you could choose to return None here.
            except Exception as e:
                logger.error(f"Failed to load credentials from BINS_GOOGLE_CREDENTIALS_JSON: {e}", exc_info=True)
                # Fall through or return None

        # Option 2: Fallback or primary method - load from a file path
        # This will only be attempted if credentials were not successfully loaded from BINS_GOOGLE_CREDENTIALS_JSON
        if not credentials: # Check if credentials are still None
            credentials_path = os.environ.get('BINS_GOOGLE_CREDENTIALS') # Original environment variable
            if credentials_path:
                try:
                    credentials = service_account.Credentials.from_service_account_file(
                        credentials_path, scopes=scopes)
                    logger.info(f"Credentials loaded successfully from file path: {credentials_path}")
                    return credentials
                except FileNotFoundError:
                    logger.error(f"Credentials file not found at path specified by BINS_GOOGLE_CREDENTIALS: {credentials_path}", exc_info=False) # No need for full traceback for FileNotFoundError
                    return None
                except Exception as e:
                    logger.error(f"Failed to load service account credentials from file path '{credentials_path}': {e}", exc_info=True)
                    return None

        # If neither method yields credentials
        if not credentials:
            if not credentials_json_str and not os.environ.get('BINS_GOOGLE_CREDENTIALS'):
                 logger.error("Neither BINS_GOOGLE_CREDENTIALS_JSON nor BINS_GOOGLE_CREDENTIALS environment variable is set.")
            # If one was set but failed and didn't set credentials, an error would have already been logged.
        return credentials # Will be None if all attempts failed
        

    def _parse_collection_date(self, collection: BinCollection, current_date: date) -> Optional[date]:
        """Parses the date from a BinCollection, handling year rollover."""
        try:
            day_of_month_str = collection.date.split()[0]
            collection_month = collection.month
            if not collection_month:
                logger.warning(f"Skipping collection due to missing month: {collection}")
                return None
            current_year = datetime.now().year
            collection_dt = datetime.strptime(f"{day_of_month_str} {collection_month} {current_year}", "%d %B %Y")
            collection_dt = collection_dt.replace(year=current_date.year)

            # Handle year rollover
            if collection_dt.date() < current_date:
                collection_dt = collection_dt.replace(year=current_date.year + 1)

            return collection_dt.date()
        except ValueError as e:
            logger.error(f"Error parsing date for collection '{collection}': {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing date for collection '{collection}': {e}", exc_info=True)
            return None


    def _create_event_data(self, collection: BinCollection, address: str, event_date: date) -> dict:
        """
        Create event data dictionary for Google Calendar API.

        Args:
            collection: BinCollection object with collection data.
            address: Address string for the event location.
            event_date: The specific date for the event.

        Returns:
            dict: Google Calendar event data.
        """
        summary = f"{collection.bin_type} bin collection"
        description = f"Bin collection day for: {collection.bin_type} ({collection.bin_colour} bin).\nLink: {collection.bin_link or 'N/A'}"

        event = {
            'summary': summary,
            'location': address,
            'description': description,
            'start': {
                'date': event_date.isoformat(),
                'timeZone': self.timezone,
            },
            'end': {
                # Google Calendar API requires end date to be exclusive for all-day events
                'date': (event_date + timedelta(days=1)).isoformat(),
                'timeZone': self.timezone,
            },
            # Add a reminder (optional, adjust as needed)
            'reminders': {
                'useDefault': False,
                'overrides': [
                    # Reminder 5 hours before midnight (7 PM previous day)
                    {'method': 'popup', 'minutes': 300}
                ],
            },
            # Mark as free time (optional)
            'transparency': 'transparent',
        }
        return event

    def _find_existing_event(self, summary: str, event_date: date) -> Optional[str]:
        """
        Check if an event with the same summary and date already exists.

        Args:
            summary: The event summary to search for.
            event_date: The date of the event.

        Returns:
            The event ID if found, otherwise None.
        """
        if not self.service:
            logger.error("Google Calendar service not available. Cannot check for existing events.")
            return None

        try:
            # Define the time range for the search (the specific day)
            # Convert date to datetime objects at the beginning and end of the day in the target timezone
            start_dt = self.tz.localize(datetime.combine(event_date, datetime.min.time()))
            end_dt = self.tz.localize(datetime.combine(event_date, datetime.max.time()))

            # Format times in RFC3339 format required by the API
            time_min = start_dt.isoformat()
            time_max = end_dt.isoformat()

            logger.debug(f"Searching for event '{summary}' between {time_min} and {time_max}")

            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                q=summary, # Use query to narrow down, but still verify exact match
                singleEvents=True,
                orderBy='startTime',
                maxResults=10 # Limit results, we only need one match
            ).execute()

            events = events_result.get('items', [])

            for event in events:
                event_summary = event.get('summary')
                start = event.get('start', {})
                # Handle both 'date' and 'dateTime' fields
                existing_event_date_str = start.get('date') or start.get('dateTime', '').split('T')[0]

                if not existing_event_date_str:
                    continue # Skip if no valid start date found

                try:
                    existing_event_date = date.fromisoformat(existing_event_date_str)
                except ValueError:
                    logger.warning(f"Could not parse date '{existing_event_date_str}' for event ID {event.get('id')}")
                    continue # Skip if date parsing fails

                # Check for exact match on summary and date
                if event_summary == summary and existing_event_date == event_date:
                    logger.info(f"Found existing event for '{summary}' on {event_date} (ID: {event.get('id')})")
                    return event.get('id') # Return the ID of the existing event

            logger.debug(f"No existing event found for '{summary}' on {event_date}.")
            return None # No matching event found

        except Exception as e:
            logger.error(f"Error searching for existing Google Calendar events: {e}", exc_info=True)
            # Treat errors as "not found" to avoid blocking uploads, but log it.
            return None


    def upload_events(self, fetcher_result: FetcherResult, current_date_override: Optional[date] = None) -> bool:
        """
        Upload bin collection events to Google Calendar, avoiding duplicates.

        Args:
            fetcher_result: FetcherResult object with bin collection data.
            current_date_override: Optional date to override the current date for testing/rollover.

        Returns:
            bool: True if all operations (checks and potential uploads) completed without API errors,
                  False otherwise. Note: Skipping duplicates is considered a success.
        """
        if not self.service:
            logger.error("Google Calendar service not available. Upload aborted.")
            return False
        
        if not fetcher_result.collections:
            logger.info("No upcoming collections found. Skipping Google Calendar upload.")
            return True # Success, nothing to do

        current_date = current_date_override if current_date_override else datetime.now(self.tz).date()
        overall_success = True

        for collection in fetcher_result.collections:
            try:
                event_date = self._parse_collection_date(collection, current_date)
                if not event_date:
                    continue # Skip if date parsing failed

                event_data = self._create_event_data(collection, fetcher_result.address_text, event_date)
                summary = event_data['summary']

                # Check if event already exists
                existing_event_id = self._find_existing_event(summary, event_date)

                if existing_event_id:
                    logger.info(f"Skipping duplicate event: '{summary}' on {event_date}")
                    continue # Skip insertion

                # Insert the new event
                logger.info(f"Creating event: '{summary}' on {event_date}")
                created_event = self.service.events().insert(
                    calendarId=self.calendar_id,
                    body=event_data
                ).execute()
                logger.info(f"Event created successfully: {created_event.get('htmlLink')}")

            except Exception as e:
                # Log errors for individual event creation/checking attempts
                logger.error(f"Failed to process or upload event for {collection} on {event_date}: {e}", exc_info=True)
                overall_success = False # Mark the overall process as having encountered issues

        return overall_success
