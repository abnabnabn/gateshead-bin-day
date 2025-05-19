from dataclasses import dataclass, asdict # Import asdict
from typing import Optional, List # Import List

@dataclass
class BinCollection:
    """Represents a single upcoming bin collection."""
    date: str
    month: str
    bin_type: str
    bin_colour: str
    bin_link: Optional[str] = None

@dataclass
class FetcherResult:
    """Represents the successful result from a BinDataFetcher."""
    address_text: str
    collections: List[BinCollection]

    # Helper method to convert collections to list of dicts for JSON/cache
    def collections_as_dicts(self) -> List[dict]:
        return [asdict(collection) for collection in self.collections]