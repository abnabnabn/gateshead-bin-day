import logging
from .base_fetcher import BinDataFetcher
from .gateshead_bin_data import GatesheadBinData
from .cached_data_fetcher import CachedBinData

logger = logging.getLogger(__name__)

def create_fetcher(source: str, use_cache: bool) -> BinDataFetcher:
    """
    Factory function to create the appropriate BinDataFetcher instance.

    Args:
        source: The identifier for the data source (e.g., "gateshead").
        use_cache: Whether to wrap the fetcher with the caching layer.

    Returns:
        An instance conforming to the BinDataFetcher interface.

    Raises:
        ValueError: If the specified source is unknown.
    """
    logger.info(f"Creating fetcher for source: '{source}', use_cache: {use_cache}")

    base_fetcher: BinDataFetcher

    # 1. Instantiate the base fetcher based on the source
    if source.lower() == "gateshead":
        base_fetcher = GatesheadBinData()
    # --- Add other sources here using elif ---
    # elif source.lower() == "another_council":
    #     base_fetcher = AnotherCouncilBinData()
    else:
        logger.error(f"Unknown data source requested: {source}")
        raise ValueError(f"Unknown data source: {source}")

    # 2. Conditionally wrap with the caching fetcher
    if use_cache:
        logger.info(f"Wrapping {type(base_fetcher).__name__} with CachedBinData.")
        return CachedBinData(base_fetcher)
    else:
        logger.info(f"Using direct fetcher {type(base_fetcher).__name__} (cache disabled).")
        return base_fetcher