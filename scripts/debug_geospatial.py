#!/usr/bin/env python3
"""
Debug script for geospatial integrations.

This script tests both Sentinel Hub and NASA FIRMS integrations with detailed logging.

Usage:
    python scripts/debug_geospatial.py [--lat LAT] [--lon LON] [--sentinel] [--firms]

Example:
    python scripts/debug_geospatial.py --lat 28.6139 --lon 77.2090 --sentinel --firms
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from geospatial.sentinel_client import SentinelClient
from geospatial.nasa_firms_client import NASAFIRMSClient

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug_geospatial.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def test_sentinel_hub(lat: float, lon: float):
    """Test Sentinel Hub NDVI fetch with detailed logging."""
    print("\n" + "="*70)
    print("TESTING SENTINEL HUB")
    print("="*70)
    
    try:
        client = SentinelClient()
        
        if not client.is_available():
            print("❌ Sentinel Hub: No credentials configured")
            print("   Set SENTINEL_CLIENT_ID and SENTINEL_CLIENT_SECRET in .env")
            return False
        
        print(f"✓ Sentinel Hub: Credentials available")
        print(f"  Testing fetch_ndvi for lat={lat}, lon={lon}")
        
        result = client.fetch_ndvi(lat, lon, bbox_size_km=1.0)
        
        print(f"✓ Sentinel Hub: NDVI fetch successful!")
        print(f"  Result: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Sentinel Hub: {e}")
        logger.exception("Sentinel Hub error")
        return False


def test_nasa_firms(lat: float, lon: float):
    """Test NASA FIRMS hotspot fetch with detailed logging."""
    print("\n" + "="*70)
    print("TESTING NASA FIRMS")
    print("="*70)
    
    try:
        client = NASAFIRMSClient()
        
        if not client.is_available():
            print("❌ NASA FIRMS: No API key configured")
            print("   Set NASA_FIRMS_API_KEY in .env")
            return False
        
        print(f"✓ NASA FIRMS: API key available")
        print(f"  Testing fetch_hotspots for lat={lat}, lon={lon}")
        
        hotspots = client.fetch_hotspots(lat, lon, radius_km=50.0)
        
        print(f"✓ NASA FIRMS: Hotspot fetch successful!")
        print(f"  Found {len(hotspots)} hotspots")
        
        if hotspots:
            print(f"  Sample hotspot: {hotspots[0]}")
        
        return True
        
    except Exception as e:
        print(f"❌ NASA FIRMS: {e}")
        logger.exception("NASA FIRMS error")
        return False


def print_summary(sentinel_ok: bool, firms_ok: bool):
    """Print summary of test results."""
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    print(f"Sentinel Hub:  {'✓ PASS' if sentinel_ok else '❌ FAIL'}")
    print(f"NASA FIRMS:    {'✓ PASS' if firms_ok else '❌ FAIL'}")
    
    if sentinel_ok and firms_ok:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed. Check the log file: debug_geospatial.log")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Debug geospatial integrations"
    )
    parser.add_argument(
        "--lat",
        type=float,
        default=28.6139,
        help="Latitude (default: Delhi)"
    )
    parser.add_argument(
        "--lon",
        type=float,
        default=77.2090,
        help="Longitude (default: Delhi)"
    )
    parser.add_argument(
        "--sentinel",
        action="store_true",
        default=True,
        help="Test Sentinel Hub"
    )
    parser.add_argument(
        "--firms",
        action="store_true",
        default=True,
        help="Test NASA FIRMS"
    )
    parser.add_argument(
        "--no-sentinel",
        action="store_true",
        help="Skip Sentinel Hub test"
    )
    parser.add_argument(
        "--no-firms",
        action="store_true",
        help="Skip NASA FIRMS test"
    )
    
    args = parser.parse_args()
    
    # Override defaults if --no-* flags are provided
    test_sentinel = not args.no_sentinel
    test_firms = not args.no_firms
    
    print("\n" + "="*70)
    print("VAYU GEOSPATIAL DEBUG")
    print("="*70)
    print(f"Location: lat={args.lat}, lon={args.lon}")
    print(f"Tests: Sentinel Hub={test_sentinel}, NASA FIRMS={test_firms}")
    
    sentinel_ok = test_sentinel_hub(args.lat, args.lon) if test_sentinel else None
    firms_ok = test_nasa_firms(args.lat, args.lon) if test_firms else None
    
    # Only include results that were tested
    results_to_report = [r for r in [sentinel_ok, firms_ok] if r is not None]
    
    if results_to_report:
        return print_summary(
            sentinel_ok if sentinel_ok is not None else True,
            firms_ok if firms_ok is not None else True
        )
    else:
        print("No tests were run.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
