import requests
import json
import sys
import os
import random
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional, List, Tuple
from .base_fetcher import BinDataFetcher
from ..data_models import BinCollection, FetcherResult

# --- Configuration ---
BASE_URL = "https://www.gateshead.gov.uk"
BIN_CHECKER_URL = f"{BASE_URL}/article/3150/Bin-collection-day-checker"
ADDRESS_LOOKUP_URL = f"{BASE_URL}/apiserver/postcode"
PROCESS_SUBMISSION_URL = f"{BASE_URL}/apiserver/formsservice/http/processsubmission"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}
# Define the standard keys used for color lookups
BIN_COLOURS = {
    "Household Waste": "green",
    "Garden Waste": "garden",
    "Recycling - Glass, plastic and cans": "dark blue",
    "Recycling - Paper and cardboard": "light blue with red top",
}
# FIX: Define a mapping for short names found in link text to the standard name
SHORT_NAME_MAP = {
    "Household": "Household Waste",
    "Garden": "Garden Waste",
    # Add other short names here if discovered
}


class GatesheadBinData(BinDataFetcher):
    """Fetches bin collection data from the Gateshead Council website."""

    # _get_form_session_data unchanged
    def _get_form_session_data(self, session):
        # ... (implementation unchanged) ...
        try: response = session.get(BIN_CHECKER_URL, headers=HEADERS, timeout=30); response.raise_for_status(); soup = BeautifulSoup(response.text, 'html.parser'); page_session_id_input = soup.find('input', {'name': 'BINCOLLECTIONCHECKER_PAGESESSIONID'}); fsid_input = soup.find('input', {'name': 'BINCOLLECTIONCHECKER_SESSIONID'}); nonce_input = soup.find('input', {'name': 'BINCOLLECTIONCHECKER_NONCE'}); return {'pageSessionId': page_session_id_input.get('value'), 'fsid': fsid_input.get('value'), 'nonce': nonce_input.get('value')} if page_session_id_input and fsid_input and nonce_input else None
        except Exception as e: print(f"Error getting session: {e}", file=sys.stderr); return None

    # _get_address_udprn unchanged
    def _get_address_udprn(self, postcode: str, house_number_target: Optional[str], session_data) -> Tuple[Optional[str], Optional[str]]:
        # ... (implementation unchanged) ...
        try:
            with requests.Session() as session:
                 session.headers.update(HEADERS); jsonrpc_payload = {"jsonrpc": "2.0", "id": 1, "method": "postcodeSearch", "params": {"provider": "EndPoint", "postcode": requests.utils.quote(postcode)}}; params = {'jsonrpc': json.dumps(jsonrpc_payload), 'callback': 'getAddresses'}; response = session.get(ADDRESS_LOOKUP_URL, params=params, timeout=30); response.raise_for_status(); response_text = response.text
                 if not response_text.startswith('getAddresses('): return None, None
                 try: json_string = response_text[len('getAddresses('):-1]; json_data = json.loads(json_string)
                 except: print(f"Error: Decode JSONP {postcode}", file=sys.stderr); return None, None
                 if not json_data or 'result' not in json_data or not isinstance(json_data.get('result'), list): return None, None
                 addresses = json_data.get('result', []); target_udprn, target_address_text = None, None
                 if house_number_target:
                    found = False
                    for address_obj in addresses:
                        line1 = (address_obj.get('line1') or '').lower(); addr_postcode = address_obj.get('postcode') or ''
                        if house_number_target.lower() in line1: target_udprn = address_obj.get('udprn'); target_address_text = f"{address_obj.get('line1') or ''} {address_obj.get('line2') or ''}, {addr_postcode}".strip().replace(" ,", ","); found = True; break
                    if not found: print(f"Warn: Address match fail {house_number_target} {postcode}", file=sys.stderr); return None, None
                 else: # Random
                    if addresses:
                        try: address_obj = random.choice(addresses); target_udprn = address_obj.get('udprn'); target_address_text = f"{address_obj.get('line1') or ''} {address_obj.get('line2') or ''}, {address_obj.get('postcode') or ''}".strip().replace(" ,", ",")
                        except Exception as e_rand: print(f"Error random select: {e_rand}", file=sys.stderr); return None, None
                    else: print(f"Warn: No addresses for random {postcode}", file=sys.stderr); return None, None
                 if target_udprn and target_address_text: return target_udprn, target_address_text
                 else: print(f"Error: Failed final addr select {postcode}", file=sys.stderr); return None, None
        except Exception as e: print(f"Error: Unexpected address lookup {postcode}: {e}", file=sys.stderr); return None, None


    # _get_bin_schedule_html unchanged
    def _get_bin_schedule_html(self, udprn, session_data, address_text, postcode, house_number_target):
        # ... (implementation unchanged) ...
         try:
            form_data = {'BINCOLLECTIONCHECKER_PAGESESSIONID': session_data['pageSessionId'], 'BINCOLLECTIONCHECKER_SESSIONID': session_data['fsid'], 'BINCOLLECTIONCHECKER_NONCE': session_data['nonce'], 'BINCOLLECTIONCHECKER_VARIABLES': 'e30=', 'BINCOLLECTIONCHECKER_PAGENAME': 'ADDRESSSEARCH', 'BINCOLLECTIONCHECKER_PAGEINSTANCE': '0', 'BINCOLLECTIONCHECKER_ADDRESSSEARCH_ASSISTOFF': 'false', 'BINCOLLECTIONCHECKER_ADDRESSSEARCH_ASSISTON': 'true', 'BINCOLLECTIONCHECKER_ADDRESSSEARCH_STAFFLAYOUT': 'false', 'BINCOLLECTIONCHECKER_ADDRESSSEARCH_ADDRESSLOOKUPPOSTCODE': postcode, 'BINCOLLECTIONCHECKER_ADDRESSSEARCH_ADDRESSLOOKUPADDRESS': '', 'BINCOLLECTIONCHECKER_ADDRESSSEARCH_FIELD125': 'false', 'BINCOLLECTIONCHECKER_ADDRESSSEARCH_UPRN': udprn, 'BINCOLLECTIONCHECKER_ADDRESSSEARCH_ADDRESSTEXT': address_text, 'BINCOLLECTIONCHECKER_FORMACTION_NEXT': 'BINCOLLECTIONCHECKER_ADDRESSSEARCH_NEXTBUTTON'}; params = {'pageSessionId': session_data['pageSessionId'], 'fsid': session_data['fsid'], 'fsn': session_data['nonce']}; response = requests.post(PROCESS_SUBMISSION_URL, params=params, headers=HEADERS, data=form_data, timeout=30, allow_redirects=True); response.raise_for_status(); return response.text
         except Exception as e: print(f"Error fetching schedule HTML: {e}", file=sys.stderr); return None

    # Modify _parse_bin_schedule
    def _parse_bin_schedule(self, schedule_html: str) -> Optional[List[BinCollection]]:
        """Parses the bin collection schedule HTML into BinCollection objects."""
        if not schedule_html: return None
        try:
            soup = BeautifulSoup(schedule_html, 'html.parser'); upcoming_collections = []; current_month = None
            upcoming_collections_table = soup.find('table', class_='bincollections__table')
            if upcoming_collections_table:
                for row in upcoming_collections_table.find_all('tr'):
                    month_header = row.find('th', colspan="3"); cells = row.find_all('td')
                    if month_header: current_month = month_header.text.strip(); continue
                    if len(cells) == 3 and current_month:
                        day_of_month, day_of_week = cells[0].text.strip(), cells[1].text.strip()
                        for link in cells[2].find_all('a', class_='bincollections__link'):
                            # --- Start Bin Type Normalization ---
                            bin_type_raw = link.text.strip()
                            # 1. Remove " only" suffix
                            if bin_type_raw.lower().endswith(" only"):
                                bin_type_processed = bin_type_raw[:-len(" only")].strip()
                            else:
                                bin_type_processed = bin_type_raw
                            # 2. Use mapping for short names -> standard names
                            standardized_bin_type = SHORT_NAME_MAP.get(bin_type_processed, bin_type_processed)
                            # --- End Bin Type Normalization ---

                            # Uses BIN_COLOURS dictionary with the standardized bin_type
                            bin_colour = BIN_COLOURS.get(standardized_bin_type, "unknown")
                            b_link_raw, b_link = link.get('href'), None
                            if b_link_raw:
                                if not b_link_raw.startswith('http'): b_link = f"{BASE_URL}{b_link_raw}" if b_link_raw.startswith('/') else f"{BASE_URL}/{b_link_raw}"
                                else: b_link = b_link_raw

                            # Use standardized bin_type when creating object
                            upcoming_collections.append(BinCollection(
                                date=f"{day_of_month} {day_of_week}",
                                month=current_month,
                                bin_type=standardized_bin_type, # Use standardized type
                                bin_colour=bin_colour,
                                bin_link=b_link
                            ))
            elif soup.find('p', string=lambda t: t and "no collection dates found" in t.lower()): return []
            else: print("Error: No table/msg", file=sys.stderr); return None
            return upcoming_collections
        except Exception as e: print(f"Error parsing HTML: {e}", file=sys.stderr); return None

    # _fetch_bin_dates_from_website unchanged
    def _fetch_bin_dates_from_website(self, postcode: str, house_number: Optional[str]) -> Optional[FetcherResult]:
        # ... (implementation unchanged) ...
        session = requests.Session(); session.headers.update(HEADERS); session_data = self._get_form_session_data(session)
        if not session_data: return None
        udprn, address_text = self._get_address_udprn(postcode, house_number, session_data)
        if not (udprn and address_text): return None
        schedule_html = self._get_bin_schedule_html(udprn, session_data, address_text, postcode, house_number)
        schedule = self._parse_bin_schedule(schedule_html) # Uses updated parsing
        if schedule is not None: return FetcherResult(address_text=address_text, collections=schedule)
        else: return None

    # get_bin_dates unchanged
    def get_bin_dates(self, postcode: str, house_number: Optional[str]) -> Optional[FetcherResult]:
        # ... (implementation unchanged) ...
        return self._fetch_bin_dates_from_website(postcode, house_number)