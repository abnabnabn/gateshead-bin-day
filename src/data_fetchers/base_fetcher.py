import abc
from typing import Optional, List
# Import both models now
from ..data_models import BinCollection, FetcherResult

class BinDataFetcher(abc.ABC):
    """Abstract base class for fetching bin collection data."""

    @abc.abstractmethod
    def get_bin_dates(self, postcode: str, house_number: str) -> Optional[FetcherResult]: # Updated return type
        """
        Fetches bin collection dates and address text for a given location.

        Args:
            postcode: The postcode of the address.
            house_number: The house number or name.

        Returns:
            A FetcherResult object containing the address and list of collections,
            or None if fetching or parsing failed.
        """
        pass