import pytest
import os
import sys

# Add project root to sys.path to allow importing src modules
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Imports from the modules being tested or used in tests
from src.data_fetchers.fetcher_factory import create_fetcher
from src.data_fetchers.gateshead_bin_data import GatesheadBinData
from src.data_fetchers.cached_data_fetcher import CachedBinData
from src.data_fetchers.base_fetcher import BinDataFetcher


def test_create_gateshead_fetcher_no_cache():
    """Test creating a Gateshead fetcher without caching."""
    fetcher = create_fetcher(source="gateshead", use_cache=False)
    assert isinstance(fetcher, GatesheadBinData)
    # Check it's not the cached version
    assert not isinstance(fetcher, CachedBinData)

def test_create_gateshead_fetcher_with_cache():
    """Test creating a Gateshead fetcher with caching."""
    fetcher = create_fetcher(source="gateshead", use_cache=True)
    assert isinstance(fetcher, CachedBinData)
    # Check the wrapped fetcher is the correct type
    assert isinstance(fetcher._fetcher, GatesheadBinData)

def test_create_gateshead_fetcher_case_insensitive():
    """Test creating a Gateshead fetcher with different casing."""
    fetcher_lower = create_fetcher(source="gateshead", use_cache=False)
    fetcher_title = create_fetcher(source="Gateshead", use_cache=False)
    fetcher_upper = create_fetcher(source="GATESHEAD", use_cache=False)

    assert isinstance(fetcher_lower, GatesheadBinData)
    assert isinstance(fetcher_title, GatesheadBinData)
    assert isinstance(fetcher_upper, GatesheadBinData)

    fetcher_cached = create_fetcher(source="Gateshead", use_cache=True)
    assert isinstance(fetcher_cached, CachedBinData)
    assert isinstance(fetcher_cached._fetcher, GatesheadBinData)


def test_create_unknown_source_raises_error():
    """Test creating a fetcher with an unknown source raises ValueError."""
    unknown_source = "some_other_council"
    with pytest.raises(ValueError) as excinfo:
        create_fetcher(source=unknown_source, use_cache=False)
    # Check the error message contains the unknown source name
    assert unknown_source in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo_cache:
        create_fetcher(source=unknown_source, use_cache=True)
    assert unknown_source in str(excinfo_cache.value)