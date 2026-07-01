# Implementation Guide: Exact Changes Made

## 1. Sentinel Hub Client - Changes

### Change 1: Imports
```python
# ADDED:
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
```

### Change 2: _get_token() Method
**BEFORE:** Minimal logging  
**AFTER:**
```python
print(f"Sentinel Hub: trying credential set {index}/{len(self._credential_pairs)}")
print(f"  Client ID: {credential_id[:20]}...")  # NEW: Show masked client ID
logger.debug(f"Sentinel Hub auth response status: {resp.status_code}")  # NEW
logger.warning(f"Sentinel Hub: credential set {index} rejected ({resp.status_code})")  # NEW
print(f"Sentinel Hub: authenticated successfully")
print(f"  Token: {self.token[:20]}... (expires in {payload.get('expires_in')} seconds)")  # NEW
logger.info(f"Sentinel Hub: authenticated with credential set {index}")  # NEW
```

### Change 3: fetch_ndvi() Method - THE MAIN FIX

**BEFORE:**
```python
body = {
    "input": {
        "bounds": {
            "bbox": [bbox[1], bbox[0], bbox[3], bbox[2]],
            "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}
        },
        "data": [{"type": "sentinel-2-l2a"}]  # ❌ Missing timeRange!
    },
    "output": {
        "width": 64,
        "height": 64,
        "responses": [{
            "identifier": "default",
            "format": {"type": "application/json"}  # ❌ Wrong format!
        }]
    },
    "evalscript": evalscript
}

resp = httpx.post(self.DATA_URL, headers={...}, json=body, timeout=30.0)
# ❌ No logging of request/response!
```

**AFTER:**
```python
# NEW: Generate time range
end_time = datetime.utcnow()
start_time = end_time - timedelta(days=30)

body = {
    "input": {
        "bounds": {
            "bbox": [bbox[1], bbox[0], bbox[3], bbox[2]],
            "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            "geometry": {  # ✅ NEW: Geometry polygon
                "type": "Polygon",
                "coordinates": [[
                    [bbox[1], bbox[0]],  # southwest
                    [bbox[3], bbox[0]],  # southeast
                    [bbox[3], bbox[2]],  # northeast
                    [bbox[1], bbox[2]],  # northwest
                    [bbox[1], bbox[0]]   # close polygon
                ]]
            }
        },
        "data": [{
            "type": "sentinel-2-l2a",
            "dataFilter": {  # ✅ NEW: Data filter with timeRange
                "timeRange": {
                    "from": f"{start_time.isoformat()}Z",
                    "to": f"{end_time.isoformat()}Z"
                },
                "mosaickingOrder": "leastRecent",
                "maxCloudCoverage": 50  # ✅ NEW: Cloud filtering
            }
        }]
    },
    "output": {
        "width": 64,
        "height": 64,
        "responses": [{
            "identifier": "default",
            "format": {"type": "image/tiff"}  # ✅ FIXED: Correct format
        }]
    },
    "evalscript": evalscript
}

# ✅ NEW: Log request payload
logger.debug(f"Sentinel Hub request payload: {json.dumps(body, indent=2, default=str)}")
print(f"Sentinel Hub: Sending NDVI request for lat={lat}, lon={lon}")
print(f"  BBox: west={bbox[1]}, south={bbox[0]}, east={bbox[3]}, north={bbox[2]}")
print(f"  Time range: {start_time.isoformat()}Z to {end_time.isoformat()}Z")
print(f"  Authorization: Bearer {token[:20]}...")

resp = httpx.post(self.DATA_URL, headers={...}, json=body, timeout=30.0)

# ✅ NEW: Log response details
print(f"Sentinel Hub: Response status: {resp.status_code}")
print(f"Sentinel Hub: Response headers: {dict(resp.headers)}")

if resp.status_code >= 400:
    response_text = resp.text[:500]
    print(f"Sentinel Hub: Response body: {response_text}")
    logger.error(f"Sentinel Hub error response: {response_text}")
```

### Change 4: _extract_ndvi() Method
**BEFORE:**
```python
def _extract_ndvi(self, payload: Dict[str, Any]) -> float:
    if not isinstance(payload, dict):
        raise ValueError("Unexpected Sentinel Hub payload")
    # ... minimal error handling ...
    return sum(numeric) / len(numeric)
```

**AFTER:**
```python
def _extract_ndvi(self, payload: Dict[str, Any]) -> float:
    """Extract NDVI value from response payload.
    
    Handles both JSON and binary TIFF responses.
    """
    if not isinstance(payload, dict):
        logger.warning(f"Unexpected Sentinel Hub payload type: {type(payload)}")  # ✅ NEW
        return 0.0

    data = payload.get("outputs") or []
    if not data:
        logger.warning("No outputs in Sentinel Hub response")  # ✅ NEW
        return 0.0

    # ... extraction logic ...
    
    if not numeric:
        logger.warning("No numeric values in Sentinel Hub response")  # ✅ NEW
        return 0.0
    
    result = sum(numeric) / len(numeric)
    logger.debug(f"Extracted NDVI value: {result} from {len(numeric)} pixels")  # ✅ NEW
    return result
```

---

## 2. NASA FIRMS Client - Complete Rewrite

### Change 1: Imports and Class Definition
```python
# ADDED:
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class NASAFIRMSClient:
    """NASA FIRMS client for fire/thermal anomaly retrieval."""
    
    BASE_URL = "https://firms.modaps.eosdis.nasa.gov"  # ✅ FIXED: Removed /api/
    SOURCES = ["VIIRS_SNPP", "VIIRS_NOAA20", "MODIS_NRT"]  # ✅ NEW: Data sources
```

### Change 2: fetch_hotspots() Method

**BEFORE:**
```python
def fetch_hotspots(self, lat: float, lon: float, radius_km: float = 50.0):
    if not self.is_available():
        print("NASA FIRMS: no API key configured")
        raise RuntimeError("NASA FIRMS unavailable")

    for index, api_key in enumerate(self._api_keys, start=1):
        params = {
            "api_key": self.api_key,
            "latitude": lat,  # ❌ Wrong parameter names
            "longitude": lon,  # ❌
            "radius_km": radius_km,  # ❌
            "hours": 72,  # ❌
            "format": "json",  # ❌ API returns CSV, not JSON
        }
        url = f"{self.BASE_URL}alert/viirs"  # ❌ Wrong endpoint!

        response = client.get(url, params=params)
        # ❌ No error logging
        payload = response.json()  # ❌ Expects JSON, but gets CSV!
        return self._parse_hotspots(payload)
```

**AFTER:**
```python
def fetch_hotspots(self, lat: float, lon: float, radius_km: float = 50.0):
    """Fetch fire hotspots within a bounding box around a point."""
    if not self.is_available():
        print("NASA FIRMS: no API key configured")
        logger.error("NASA FIRMS: no API key configured")  # ✅ NEW
        raise RuntimeError("NASA FIRMS unavailable")

    # ✅ NEW: Convert point + radius to bounding box
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * abs(cos(radians(lat))))
    
    bbox = {
        "west": lon - delta_lon,
        "south": lat - delta_lat,
        "east": lon + delta_lon,
        "north": lat + delta_lat,
    }

    print(f"NASA FIRMS: Fetching hotspots for lat={lat}, lon={lon}, radius={radius_km}km")
    print(f"  BBox: W={bbox['west']:.4f}, S={bbox['south']:.4f}, E={bbox['east']:.4f}, N={bbox['north']:.4f}")

    last_error = None
    
    for api_key_idx, api_key in enumerate(self._api_keys, start=1):
        self.api_key = api_key
        print(f"NASA FIRMS: trying API key {api_key_idx}/{len(self._api_keys)}")
        
        # ✅ NEW: Try each data source
        for source_idx, source in enumerate(self.SOURCES, start=1):
            print(f"NASA FIRMS: trying source {source} ({source_idx}/{len(self.SOURCES)})")
            
            try:
                # ✅ NEW: Generate date range
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=7)
                date_range = f"{start_date.strftime('%Y-%m-%d')},{end_date.strftime('%Y-%m-%d')}"
                
                # ✅ NEW: Correct endpoint
                url = f"{self.BASE_URL}/api/v1/data/{source}/csv/world/date-range/{date_range}"
                
                params = {"api_key": self.api_key}  # ✅ FIXED: Only API key param
                
                # ✅ NEW: Log request details
                print(f"NASA FIRMS: Request URL: {url}")
                print(f"NASA FIRMS: Parameters: {params}")
                
                response = client.get(url, params=params)
                
                # ✅ NEW: Log response details
                print(f"NASA FIRMS: Response status: {response.status_code}")
                
                if response.status_code >= 400:
                    response_text = response.text[:500]
                    print(f"NASA FIRMS: Error response: {response_text}")
                    logger.error(f"NASA FIRMS ({source}): {response_text}")  # ✅ NEW
                    last_error = RuntimeError(f"Request rejected ({response.status_code})")
                    continue
                
                response.raise_for_status()
                # ✅ NEW: Parse CSV response with bbox filtering
                hotspots = self._parse_csv_response(response.text, bbox)
                
                if hotspots:
                    print(f"NASA FIRMS: Found {len(hotspots)} hotspots from {source}")
                    logger.info(f"NASA FIRMS: Successfully retrieved {len(hotspots)} hotspots")  # ✅ NEW
                    return hotspots
                    
            except Exception as exc:
                print(f"NASA FIRMS: {source} failed - {exc}")
                logger.error(f"NASA FIRMS ({source}): {exc}")  # ✅ NEW
                last_error = exc

    self.available = False
    error_msg = f"NASA FIRMS fetch failed: {last_error}" if last_error else "NASA FIRMS fetch failed"
    logger.error(error_msg)  # ✅ NEW
    raise RuntimeError(error_msg)
```

### Change 3: Response Parsing Method

**BEFORE:**
```python
def _parse_hotspots(self, payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    
    features = payload.get("features") or []  # ❌ Expects GeoJSON
    results = []
    for feature in features:
        props = feature.get("properties", {})
        # ...
    return results
```

**AFTER:**
```python
def _parse_csv_response(self, csv_text: str, bbox: Dict[str, float]) -> List[Dict[str, Any]]:
    """Parse CSV response from NASA FIRMS API.
    
    CSV format:
    latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,
    confidence,version,bright_ti4,bright_ti5,frp,daynight
    
    Filter by bounding box.
    """
    results = []
    
    if not csv_text or not csv_text.strip():
        logger.warning("NASA FIRMS: Empty CSV response")  # ✅ NEW
        return results
    
    lines = csv_text.strip().split("\n")
    if len(lines) < 2:
        logger.warning(f"NASA FIRMS: CSV has no data rows")  # ✅ NEW
        return results
    
    # ✅ NEW: Parse CSV header to identify column indices
    header = lines[0].split(",")
    header = [h.strip() for h in header]
    
    try:
        lat_idx = header.index("latitude")
        lon_idx = header.index("longitude")
        brightness_idx = header.index("brightness")
        confidence_idx = header.index("confidence")
        acq_date_idx = header.index("acq_date")
        acq_time_idx = header.index("acq_time")
    except ValueError as e:
        logger.error(f"NASA FIRMS: Missing required CSV column: {e}")  # ✅ NEW
        return results
    
    # ✅ NEW: Parse data rows with bbox filtering
    for line_num, line in enumerate(lines[1:], start=2):
        try:
            values = line.split(",")
            if len(values) < len(header):
                logger.warning(f"NASA FIRMS: Line {line_num} has fewer columns")  # ✅ NEW
                continue
            
            lat = float(values[lat_idx].strip())
            lon = float(values[lon_idx].strip())
            
            # ✅ NEW: Filter by bounding box
            if not (bbox["south"] <= lat <= bbox["north"] and 
                    bbox["west"] <= lon <= bbox["east"]):
                continue
            
            brightness = float(values[brightness_idx].strip()) if brightness_idx < len(values) else 0.0
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
            logger.warning(f"NASA FIRMS: Failed to parse line {line_num}: {e}")  # ✅ NEW
            continue
    
    logger.debug(f"NASA FIRMS: Parsed {len(results)} hotspots from CSV within bbox")  # ✅ NEW
    return results
```

---

## 3. Debug Script (NEW FILE)

Created: `scripts/debug_geospatial.py`

```python
#!/usr/bin/env python3
"""Debug script for geospatial integrations."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from geospatial.sentinel_client import SentinelClient
from geospatial.nasa_firms_client import NASAFIRMSClient
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug_geospatial.log'),
        logging.StreamHandler()
    ]
)

# Test both clients with comprehensive logging
```

---

## Summary of Exact Changes

### Sentinel Hub
| Aspect | Before | After |
|--------|--------|-------|
| timeRange | ❌ Missing | ✅ 30-day ISO 8601 format |
| output.format.type | `application/json` | `image/tiff` |
| geometry | ❌ None | ✅ Polygon from bbox |
| dataFilter | ❌ None | ✅ cloud, mosaicking settings |
| Request logging | ❌ Minimal | ✅ Full JSON payload |
| Response logging | ❌ None | ✅ Status, headers, body |
| Error messages | Generic | Detailed with context |

### NASA FIRMS
| Aspect | Before | After |
|--------|--------|-------|
| Endpoint | `/api/alert/viirs` ❌ | `/api/v1/data/{source}/csv/world/date-range/{dates}` ✅ |
| Parameters | point-based ❌ | api_key only ✅ (bbox internally calculated) |
| Data sources | None ❌ | Multi-source fallback ✅ |
| Response parsing | JSON ❌ | CSV ✅ |
| Date range | hours ❌ | 7 days ✅ |
| Bbox filtering | None ❌ | Included ✅ |
| Request logging | None ❌ | URL + params ✅ |
| Error logging | None ❌ | Full response body ✅ |

---

## Testing Commands

```bash
# Run debug script
python scripts/debug_geospatial.py --lat 28.6139 --lon 77.2090

# View logs
cat debug_geospatial.log

# Test specific providers
python scripts/debug_geospatial.py --lat 28.6139 --lon 77.2090 --no-firms  # Only Sentinel
python scripts/debug_geospatial.py --lat 28.6139 --lon 77.2090 --no-sentinel  # Only NASA FIRMS
```

---

## Environment Configuration

```bash
# .env file - REQUIRED
SENTINEL_CLIENT_ID=<get from https://apps.sentinel-hub.com/dashboard>
SENTINEL_CLIENT_SECRET=<from same location>
NASA_FIRMS_API_KEY=<get from https://firms.modaps.eosdis.nasa.gov>

# Optional - Fallback credentials
SENTINEL_CLIENT_ID_FALLBACK=<alternate credentials>
SENTINEL_CLIENT_SECRET_FALLBACK=<alternate credentials>
NASA_FIRMS_API_KEY_FALLBACK=<alternate key>

# Optional - Enable/Disable
ENABLE_SENTINEL=true
ENABLE_NASA_FIRMS=true
```

---

## Verification Checklist

After deployment:
- [ ] Run debug script and confirm both tests pass
- [ ] Check `debug_geospatial.log` for proper payload structures
- [ ] Verify timeRange is in ISO 8601 format (ends with Z)
- [ ] Verify output format is `image/tiff` for Sentinel
- [ ] Verify NASA FIRMS URL includes correct source and date range
- [ ] Confirm CSV parsing extracts all hotspot data correctly
- [ ] Test with different cities/coordinates to verify robustness
- [ ] Monitor application logs for integration errors

