from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta, date # Import date
import pytz
import sys
# Import the data models
from .data_models import BinCollection, FetcherResult

from typing import List, Optional # Import List, Optional

# New function to generate the Calendar object
def generate_calendar_object(fetcher_result: FetcherResult, current_date: Optional[datetime] = None) -> Calendar:
    """
    Generates an icalendar.Calendar object based on the fetched bin data.
    """
    if current_date is None:
        current_date = datetime.now()

    # Extract data from the FetcherResult object
    upcoming_collections = fetcher_result.collections
    address_text = fetcher_result.address_text

    cal = Calendar()
    cal.add('prodid', '-//Bin Calendar//Gateshead//EN')
    cal.add('version', '2.0')

    print(f"DEBUG: Generating Calendar object for {len(upcoming_collections)} collections for {address_text}...") # Debug print

    for collection in upcoming_collections:
        event = Event()
        bin_type = collection.bin_type
        bin_colour = collection.bin_colour
        bin_link = collection.bin_link if collection.bin_link else "Link not found"

        event.add('summary', f"{bin_type} bin collection")
        event.add('description', f"Bin collection day for: {bin_type} ({bin_colour} bin).\nLink: {bin_link}")

        date_str = collection.date
        collection_month = collection.month
        if not collection_month:
            print(f"Warning: Skipping collection due to missing month: {collection}", file=sys.stderr)
            continue

        day_of_month_str = date_str.split()[0]
        try:
            # Add a dummy year to avoid deprecation warning about ambiguous date parsing
            dummy_year = 2000
            collection_dt = datetime.strptime(f"{day_of_month_str} {collection_month} {dummy_year}", "%d %B %Y")
            collection_dt = collection_dt.replace(year=current_date.year)
        except ValueError as e:
            print(f"Error parsing date '{day_of_month_str} {collection_month}': {e}", file=sys.stderr)
            continue

        if collection_dt < current_date:
            collection_dt = collection_dt.replace(year=current_date.year + 1)

        # All-Day Event
        event_date_obj: date = collection_dt.date()
        event.add('dtstart', event_date_obj)
        # Mark as Free Time
        event.add('transp', 'TRANSPARENT')
        # Location
        event.add('location', address_text)

        # Reminder (Alarm) at 7:30 PM day before
        alarm = Alarm()
        alarm.add('action', 'DISPLAY')
        alarm.add('description', f"Put out {bin_type} ({bin_colour} bin) tomorrow")
        trigger_timedelta = timedelta(hours=-4.5) # 4.5 hours before midnight
        alarm.add('trigger', trigger_timedelta)
        event.add_component(alarm)

        cal.add_component(event)

    return cal # Return the calendar object


# Modified function to generate AND save the file
def create_ics_file(fetcher_result: FetcherResult, current_date: Optional[datetime] = None):
    """
    Generates and saves an .ics file using data from a FetcherResult object.
    """
    # Call the new function to get the calendar object
    cal = generate_calendar_object(fetcher_result, current_date)

    # Write to file
    try:
        with open('bin_collections.ics', 'wb') as f:
            f.write(cal.to_ical())
        print("Calendar file 'bin_collections.ics' generated successfully.")
    except IOError as e:
         print(f"Error writing ICS file: {e}", file=sys.stderr)
