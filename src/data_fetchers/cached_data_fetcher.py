import logging
import json
import os
import sys
from typing import Optional, List, Dict, Any
from dataclasses import asdict
from .base_fetcher import BinDataFetcher
from ..data_models import BinCollection, FetcherResult

# --- Define Cache Directory ---
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(project_root, 'cache')

logger = logging.getLogger(__name__)

# --- Cache Helper Functions ---
def _get_cache_filename(postcode: str, house_number: Optional[str]) -> str: # Allow None for house_number
    """Generates the cache filename within the CACHE_DIR."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe_postcode = postcode.replace(' ', '_').upper()
    # FIX: Handle None case for house_number before calling replace
    if house_number is None:
        safe_house_number = "__random__" # Use a specific placeholder string
    else:
        safe_house_number = house_number.replace('/', '_').replace('\\', '_')
    return os.path.join(CACHE_DIR, f"{safe_postcode}_{safe_house_number}.json")

# load_schedule_from_cache remains the same
def load_schedule_from_cache(postcode: str, house_number: Optional[str]) -> Optional[Dict[str, Any]]:
    """ Loads the cached data as a dictionary. """
    filename = _get_cache_filename(postcode, house_number) # Pass potentially None house_number
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            if isinstance(data.get("schedule"), list) and isinstance(data.get("address_text"), str):
                logger.info(f"Cache HIT for {postcode} {house_number or 'random'} from file: {filename}")
                return data
            else:
                 logger.warning(f"Invalid cache format {filename}.")
                 return None
    except FileNotFoundError:
        logger.info(f"Cache MISS for {postcode} {house_number or 'random'}. File not found: {filename}")
        return None
    except (json.JSONDecodeError, KeyError, IOError, TypeError) as e:
        logger.error(f"Error loading cache {filename}: {e}", exc_info=True)
        return None

# save_schedule_to_cache remains the same
def save_schedule_to_cache(postcode: str, house_number: Optional[str], result_data: FetcherResult):
    """ Saves the FetcherResult data (converting collections to dicts) to cache. """
    if not isinstance(result_data, FetcherResult): return
    filename = _get_cache_filename(postcode, house_number) # Pass potentially None house_number
    data_to_save = { "address_text": result_data.address_text, "schedule": result_data.collections_as_dicts() }
    try:
        with open(filename, 'w') as f: json.dump(data_to_save, f, indent=4)
        logger.info(f"Schedule saved to cache file: {filename}")
    except IOError as e:
        logger.error(f"Error saving cache {filename}: {e}", exc_info=True)
        print(f"Error: Could not save cache {filename}. Check logs.", file=sys.stderr)


class CachedBinData(BinDataFetcher):
    """ Caching layer for another BinDataFetcher. """
    def __init__(self, underlying_fetcher: BinDataFetcher):
        if not isinstance(underlying_fetcher, BinDataFetcher): raise TypeError("...")
        self._fetcher = underlying_fetcher
        logger.info(f"CachedBinData initialized, wrapping {type(underlying_fetcher).__name__}")

    # Update get_bin_dates signature to accept Optional house_number
    def get_bin_dates(self, postcode: str, house_number: Optional[str]) -> Optional[FetcherResult]:
        log_hn = house_number or 'random' # For logging clarity
        logger.info(f"CachedBinData: Requesting bin dates for {postcode} {log_hn}")

        # 1. Try loading from cache (pass potentially None house_number)
        cached_data = load_schedule_from_cache(postcode, house_number)

        if cached_data is not None:
            logger.info(f"CachedBinData: Cache HIT for {postcode} {log_hn}")
            try:
                # Reconstruct using potentially None house_number in filename logic
                reconstructed_collections = [BinCollection(**item) for item in cached_data["schedule"]]
                return FetcherResult(address_text=cached_data["address_text"], collections=reconstructed_collections)
            except (TypeError, KeyError) as e:
                 logger.error(f"Failed to reconstruct FetcherResult from cache: {e}", exc_info=True)
                 pass # Fall through to fetch

        # 2. Cache MISS or reconstruction failed (pass potentially None house_number)
        logger.info(f"CachedBinData: Cache MISS for {postcode} {log_hn}. Calling underlying fetcher.")
        fetched_result: Optional[FetcherResult] = self._fetcher.get_bin_dates(postcode, house_number)

        # 3. Save successful fetches (pass potentially None house_number)
        if fetched_result is not None:
            logger.info(f"CachedBinData: Underlying fetcher succeeded. Saving result to cache.")
            save_schedule_to_cache(postcode, house_number, fetched_result)
        else:
            logger.warning(f"CachedBinData: Underlying fetcher failed. Result not cached.")

        return fetched_result