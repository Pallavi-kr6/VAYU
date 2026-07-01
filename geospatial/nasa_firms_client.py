from typing import Any, Dict, List
from fastapi import params
import httpx
import json
import logging
from datetime import datetime, timedelta

from config.settings import NASA_FIRMS_API_KEY, NASA_FIRMS_API_KEY_FALLBACK

logger = logging.getLogger(__name__)


class NASAFIRMSClient:
    """Standalone NASA FIRMS client for fire/thermal anomaly retrieval.
    
    NASA FIRMS API reference:
    https://firms.modaps.eosdis.nasa.gov/api/
    
    Endpoints:
    - /api/v1/data/VIIRS_SNPP/csv/world/
    - /api/v1/data/VIIRS_NOAA20/csv/world/
    - /api/v1/data/MODIS_NRT/csv/world/
    
    Format: /api/v1/data/<source>/<format>/<extent>/date-range/<date>
    """

    BASE_URL = "https://firms.modaps.eosdis.nasa.gov"
    SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "MODIS_NRT"
]  # In order of preference

    def __init__(self, api_key: str = None):
        self._api_keys = self._build_api_keys(api_key)
        self.api_key = self._api_keys[0] if self._api_keys else None
        self.available = bool(self._api_keys)

    def is_available(self) -> bool:
        return self.available and bool(self.api_key)

    def _build_api_keys(self, api_key: str = None) -> List[str]:
        candidates: List[str] = []
        for candidate in [api_key, NASA_FIRMS_API_KEY, NASA_FIRMS_API_KEY_FALLBACK]:
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    def fetch_hotspots(self, lat: float, lon: float, radius_km: float = 50.0) -> List[Dict[str, Any]]:
        """Fetch fire hotspots within a bounding box around a point.
        
        Args:
            lat: Center latitude
            lon: Center longitude
            radius_km: Search radius in kilometers (converted to bbox)
            
        Returns:
            List of hotspot dictionaries with coordinates, brightness, confidence, etc.
        """
        if not self.is_available():
            print("NASA FIRMS: no API key configured")
            logger.error("NASA FIRMS: no API key configured")
            raise RuntimeError("NASA FIRMS unavailable")

        # Convert point + radius to bounding box
        # 1 degree of latitude ≈ 111 km, 1 degree of longitude ≈ 111 * cos(lat) km
        delta_lat = radius_km / 111.0
        delta_lon = radius_km / (111.0 * abs(__import__("math").cos(__import__("math").radians(lat))))
        
        bbox = {
            "west": lon - delta_lon,
            "south": lat - delta_lat,
            "east": lon + delta_lon,
            "north": lat + delta_lat,
        }

        print(f"NASA FIRMS: Fetching hotspots for lat={lat}, lon={lon}, radius={radius_km}km")
        print(f"  BBox: W={bbox['west']:.4f}, S={bbox['south']:.4f}, E={bbox['east']:.4f}, N={bbox['north']:.4f}")

        last_error: Exception | None = None
        
        for api_key_idx, api_key in enumerate(self._api_keys, start=1):
            self.api_key = api_key
            print(f"NASA FIRMS: trying API key {api_key_idx}/{len(self._api_keys)}")
            
            # Try each data source
            for source_idx, source in enumerate(self.SOURCES, start=1):
                print(f"NASA FIRMS: trying source {source} ({source_idx}/{len(self.SOURCES)})")
                
                # NASA FIRMS API expects: /api/v1/data/<source>/csv/world/date-range/<days>?api_key=<key>
                # Alternative: Use bounding box format for custom areas
                try:
                    # Generate date range for last 7 days
                    days = 3
                    url = (
    f"{self.BASE_URL}/api/area/csv/"
    f"{self.api_key}/"
    f"{source}/"
    f"{bbox['west']},{bbox['south']},"
    f"{bbox['east']},{bbox['north']}/"
    f"{days}"
)

                    
                    print(f"NASA FIRMS: Request URL: {url}")
                  
                    
                    with httpx.Client(timeout=30.0) as client:
                        response = client.get(url)
                    
                    print(f"NASA FIRMS: Response status: {response.status_code}")
                    logger.debug(f"NASA FIRMS: Response headers: {dict(response.headers)}")
                    
                    if response.status_code >= 400:
                        response_text = response.text[:500]
                        print(f"NASA FIRMS: Error response: {response_text}")
                        logger.error(f"NASA FIRMS ({source}): Request rejected ({response.status_code}): {response_text}")
                        last_error = RuntimeError(f"NASA FIRMS request rejected ({response.status_code})")
                        continue
                    
                    response.raise_for_status()
                    hotspots = self._parse_csv_response(response.text, bbox)
                    if hotspots is not None:
                        print(f"NASA FIRMS: Found {len(hotspots)} hotspots from {source}")
                        logger.info(f"NASA FIRMS: Successfully retrieved {len(hotspots)} hotspots from {source}")
                        return hotspots
                    else:
                        print(f"NASA FIRMS: No hotspots found in response from {source}")
                        return []
                        
                except Exception as exc:
                    print(f"NASA FIRMS: {source} failed - {exc}")
                    logger.error(f"NASA FIRMS ({source}): {exc}")
                    last_error = exc

        self.available = False
        error_msg = f"NASA FIRMS fetch failed: {last_error}" if last_error else "NASA FIRMS fetch failed"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    def _parse_csv_response(self, csv_text: str, bbox: Dict[str, float]) -> List[Dict[str, Any]]:
        """Parse CSV response from NASA FIRMS API.
        
        CSV format (comma-separated):
        latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,
        confidence,version,bright_ti4,bright_ti5,frp,daynight
        
        Only include points within the specified bounding box.
        """
        results = []
        
        if not csv_text or not csv_text.strip():
            logger.warning("NASA FIRMS: Empty CSV response")
            return results
        
        lines = csv_text.strip().split("\n")
        if len(lines) < 2:
            logger.warning(f"NASA FIRMS: CSV has no data rows (only {len(lines)} lines)")
            return results
        
        # Parse header
        header = lines[0].split(",")
        header = [h.strip() for h in header]
        print("NASA FIRMS Header:", header)
        try:
            lat_idx = header.index("latitude")
            lon_idx = header.index("longitude")
            if "brightness" in header:
                brightness_idx = header.index("brightness")
            else:
                brightness_idx = None
            confidence_idx = header.index("confidence")
            acq_date_idx = header.index("acq_date")
            acq_time_idx = header.index("acq_time")
        except ValueError as e:
            logger.error(f"NASA FIRMS: Missing required CSV column: {e}")
            return results
        
        # Parse data rows
        for line_num, line in enumerate(lines[1:], start=2):
            try:
                values = line.split(",")
                if len(values) < len(header):
                    logger.warning(f"NASA FIRMS: Line {line_num} has fewer columns than header")
                    continue
                
                lat = float(values[lat_idx].strip())
                lon = float(values[lon_idx].strip())
                
                # Filter by bounding box
                if not (bbox["south"] <= lat <= bbox["north"] and 
                        bbox["west"] <= lon <= bbox["east"]):
                    continue
                
                brightness = float(values[brightness_idx].strip()) if brightness_idx is not None and brightness_idx < len(values) else 0.0
                confidence = values[confidence_idx].strip() if confidence_idx < len(values) else "unknown"
                acq_date = values[acq_date_idx].strip() if acq_date_idx < len(values) else ""
                acq_time = values[acq_time_idx].strip() if acq_time_idx < len(values) else "00:00"
                
                results.append({
                    "lat": lat,
                    "lon": lon,
                    "brightness": brightness,
                    "confidence": confidence,
                    "timestamp": f"{acq_date}T{acq_time}Z" if acq_date else None,
                })
            except (ValueError, IndexError) as e:
                logger.warning(f"NASA FIRMS: Failed to parse line {line_num}: {e}")
                continue
        
        logger.debug(f"NASA FIRMS: Parsed {len(results)} hotspots from CSV within bbox")
        return results
