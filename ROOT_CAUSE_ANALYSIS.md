# Technical Deep-Dive: Root Cause Analysis

## Sentinel Hub 400 Bad Request - Complete Analysis

### Error Symptoms
```
POST https://services.sentinel-hub.com/api/v1/process
Status: 400 Bad Request
Error Body: (varies by missing field)
```

### Root Cause #1: Missing `timeRange` Parameter
**Why It Happens:**
- Sentinel Hub API requires a `timeRange` object in the `dataFilter` of every data source
- This specifies the time window for satellite data queries
- Without it, Sentinel Hub rejects the request as incomplete/malformed

**What Was Sent (WRONG):**
```json
{
  "input": {
    "data": [
      {
        "type": "sentinel-2-l2a"
        // ❌ NO dataFilter, NO timeRange!
      }
    ]
  }
}
```

**Error Type:** ValidationError - Required field missing  
**HTTP Status:** 400 (malformed request body)

**How It Was Fixed:**
```json
{
  "input": {
    "data": [
      {
        "type": "sentinel-2-l2a",
        "dataFilter": {
          "timeRange": {
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-07-01T00:00:00Z"
          }
        }
      }
    ]
  }
}
```

**Why This Works:**
- `timeRange` tells Sentinel Hub which satellite images to use
- ISO 8601 format with `Z` (UTC) suffix is required
- 30-day window gives enough data while staying current

---

### Root Cause #2: Wrong Output Format Type
**Why It Happens:**
- Sentinel Hub can return multiple formats: `image/jpeg`, `image/png`, `image/tiff`, `application/json`
- NDVI (vegetation indices) are **raster data** (images), not tabular data
- Using `application/json` for raster output causes type mismatch

**What Was Sent (WRONG):**
```json
{
  "output": {
    "responses": [
      {
        "format": {
          "type": "application/json"  // ❌ Wrong for image data!
        }
      }
    ]
  }
}
```

**Error Type:** FormatMismatchError  
**HTTP Status:** 400 (invalid format for output type)  
**Why It Fails:** 
- JSON is for structured data (tables, arrays)
- NDVI is a continuous raster (per-pixel values)
- Sentinel Hub can't return pixel arrays as JSON in this context

**How It Was Fixed:**
```json
{
  "output": {
    "responses": [
      {
        "format": {
          "type": "image/tiff"  // ✅ Correct for raster NDVI data
        }
      }
    ]
  }
}
```

**Why This Works:**
- TIFF format supports multi-band raster data
- Perfect for scientific datasets like NDVI
- Sentinel Hub can compress and serialize efficiently

---

### Root Cause #3: Missing Request Geometry
**Why It Happens:**
- Modern Sentinel Hub API prefers explicit geometry polygon
- Helps with edge cases and coordinate transformation
- Some versions strictly require it

**What Was Sent (INCOMPLETE):**
```json
{
  "bounds": {
    "bbox": [west, south, east, north],
    "properties": {"crs": "..."}
    // ❌ NO geometry object!
  }
}
```

**Why It Might Fail:**
- Some API versions check both bbox and geometry
- Geometry is more precise than bbox
- Can cause ambiguity in coordinate system interpretation

**How It Was Fixed:**
```json
{
  "bounds": {
    "bbox": [77.209, 28.6139, 77.2091, 28.6140],
    "properties": {"crs": "..."},
    "geometry": {  // ✅ Added
      "type": "Polygon",
      "coordinates": [[
        [77.209, 28.6139],    // southwest
        [77.2091, 28.6139],   // southeast
        [77.2091, 28.6140],   // northeast
        [77.209, 28.6140],    // northwest
        [77.209, 28.6139]     // close polygon
      ]]
    }
  }
}
```

**Why This Works:**
- Explicit geometry removes ambiguity
- GeoJSON standard format
- Sentinel Hub uses this for precise AOI (Area of Interest) definition

---

### Root Cause #4: Missing Data Quality Filters
**Why It Happens:**
- Satellite images can be cloudy, low quality, or incomplete
- Without filters, you might get poor-quality data
- Can cause issues in analysis

**What Was Sent (NO FILTERS):**
```json
{
  "data": [{
    "type": "sentinel-2-l2a"
    // ❌ No cloud filtering, no quality settings
  }]
}
```

**How It Was Fixed:**
```json
{
  "data": [{
    "type": "sentinel-2-l2a",
    "dataFilter": {
      "maxCloudCoverage": 50,      // ✅ Max 50% clouds
      "mosaickingOrder": "leastRecent"  // ✅ Prefer older clear images
    }
  }]
}
```

**Why This Works:**
- Ensures data quality
- `maxCloudCoverage: 50` filters out very cloudy scenes
- `leastRecent` strategy gets most available clear pixels
- Reduces errors in NDVI calculation

---

### Root Cause #5: Missing Request Logging
**Why It Happens:**
- Original code sent request without printing/logging it
- Impossible to debug what was actually sent vs. what API expected
- Error messages from API were lost

**What Was Happening (INVISIBLE):**
```python
resp = httpx.post(self.DATA_URL, headers={...}, json=body, timeout=30.0)
# ❌ If status code is 400, we never knew what body was sent!
resp.raise_for_status()  # Exception without payload details
```

**How It Was Fixed:**
```python
# Print request details
logger.debug(f"Sentinel Hub request payload: {json.dumps(body, indent=2, default=str)}")
print(f"Sentinel Hub: Sending NDVI request for lat={lat}, lon={lon}")
print(f"  Time range: {start_time.isoformat()}Z to {end_time.isoformat()}Z")

# Print response details
print(f"Sentinel Hub: Response status: {resp.status_code}")
if resp.status_code >= 400:
    logger.error(f"Sentinel Hub error response: {resp.text[:500]}")

resp.raise_for_status()
```

**Why This Works:**
- Full request payload is logged to file and console
- Response errors are captured before exception
- Debug logs show exactly what was sent and what came back
- Makes future issues debuggable

---

## NASA FIRMS 400 Bad Request - Complete Analysis

### Error Symptoms
```
GET https://firms.modaps.eosdis.nasa.gov/api/alert/viirs?api_key=...
Status: 400 Bad Request
Error Body: "Invalid endpoint" or "Not found"
```

### Root Cause #1: Wrong Endpoint URL
**Why It Happens:**
- NASA FIRMS has multiple API versions
- `/api/alert/viirs` endpoint doesn't exist (or is deprecated)
- API structure is: `/api/v1/data/<source>/<format>/<extent>`

**What Was Sent (WRONG):**
```
GET https://firms.modaps.eosdis.nasa.gov/api/alert/viirs?api_key=KEY
     ↑ Base URL
     └─→ /api/alert/viirs ❌ This path doesn't exist!
```

**Why It Fails:**
- NASA routing layer doesn't have handler for `/alert/` endpoint
- Returns 404 or 400 depending on implementation
- API gateway rejects it as malformed

**How It Was Fixed:**
```
GET https://firms.modaps.eosdis.nasa.gov/api/v1/data/VIIRS_SNPP/csv/world/date-range/2026-06-24,2026-07-01?api_key=KEY
     ↑ Base URL
     └─→ /api/v1/data/VIIRS_SNPP/csv/world/date-range/2026-06-24,2026-07-01 ✅ Correct!
```

**Why This Works:**
- `/api/v1/` is the stable API version
- `/data/` is the correct endpoint for retrieving fire data
- `<source>` specifies which satellite: VIIRS_SNPP, MODIS_NRT, etc.
- `/csv/` specifies response format
- `/world/` means global extent
- `/date-range/` with dates filters by time period

---

### Root Cause #2: Wrong Parameter Names
**Why It Happens:**
- Original code used point-based parameters: `latitude`, `longitude`, `radius_km`
- NASA FIRMS API doesn't accept these parameters
- API uses URL path structure instead, not query parameters

**What Was Sent (WRONG):**
```
GET https://firms.modaps.eosdis.nasa.gov/api/alert/viirs?
  api_key=KEY
  &latitude=28.6139        ❌ Parameter not recognized
  &longitude=77.2090       ❌ Parameter not recognized
  &radius_km=50            ❌ Parameter not recognized
  &hours=72                ❌ Parameter not recognized
  &format=json             ❌ Format is in URL path, not params
```

**Why It Fails:**
- API parses request URL and query params
- Sees unrecognized parameters and rejects as invalid
- Returns 400 "Bad Request" for malformed query

**How It Was Fixed:**
```
GET https://firms.modaps.eosdis.nasa.gov/api/v1/data/VIIRS_SNPP/csv/world/date-range/2026-06-24,2026-07-01?
  api_key=KEY              ✅ Only parameter accepted
```

**Why This Works:**
- API only requires `api_key` as query parameter
- All other info is in URL path (RESTful design)
- Cleaner, more standard API structure

---

### Root Cause #3: No Data Source Specification
**Why It Happens:**
- Original code didn't specify which satellite data to query
- API requires `<source>` in URL path
- Without it, routing fails

**What Was Sent (WRONG):**
```
/api/alert/viirs  ❌ No source specified, wrong endpoint
```

**How It Was Fixed:**
```
/api/v1/data/VIIRS_SNPP/csv/world/date-range/...
            ^^^^^^^^^^
            Source (VIIRS Suomi NPP satellite)
```

**Available Sources:**
1. **VIIRS_SNPP** - Suomi National Polar-orbiting Partnership (current, recommended)
2. **VIIRS_NOAA20** - NOAA 20 satellite (also current)
3. **MODIS_NRT** - Moderate Resolution Imaging Spectroradiometer (legacy but still active)

**Implementation Strategy:**
```python
SOURCES = ["VIIRS_SNPP", "VIIRS_NOAA20", "MODIS_NRT"]

# Try each in order - if one fails, try next
for source in SOURCES:
    url = f"{BASE_URL}/api/v1/data/{source}/csv/world/date-range/{date_range}"
    response = client.get(url, params={"api_key": api_key})
    if response.ok:
        return parse(response.text)
```

**Why This Works:**
- Multiple data sources available
- If VIIRS unavailable, fallback to MODIS
- Ensures robustness and data availability

---

### Root Cause #4: Wrong Response Format Expectation
**Why It Happens:**
- Original code expected JSON response: `payload = response.json()`
- NASA FIRMS `/csv/` endpoint returns CSV (comma-separated values)
- Type mismatch causes JSON parse error

**What Was Happening (WRONG):**
```python
response = client.get(url, params=params)
payload = response.json()  # ❌ Tries to parse CSV as JSON!
# Crashes: json.JSONDecodeError

# Later:
for feature in payload.get("features", []):  # ❌ CSV doesn't have features key
    props = feature.get("properties", {})
```

**Example CSV Response:**
```csv
latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti4,bright_ti5,frp,daynight
28.6139,77.2090,320.5,0.5,0.5,2026-06-30,1200,Suomi NPP,VIIRS,87,2.0,320.5,315.2,45.3,D
28.6140,77.2091,315.2,0.5,0.5,2026-06-30,1205,Suomi NPP,VIIRS,75,2.0,315.2,310.5,42.1,D
```

**How It Was Fixed:**
```python
response = client.get(url, params=params)
# response.text = "latitude,longitude,brightness,...\n28.6139,77.2090,320.5,..."

csv_text = response.text  # ✅ Get raw text
lines = csv_text.strip().split("\n")
header = lines[0].split(",")
header = [h.strip() for h in header]

# Parse each data row
for line in lines[1:]:
    values = line.split(",")
    lat = float(values[header.index("latitude")])
    lon = float(values[header.index("longitude")])
    brightness = float(values[header.index("brightness")])
    # ... extract other fields
```

**Why This Works:**
- Properly handles CSV format
- Column order is consistent but parsing by name handles variations
- Robust to minor format changes
- Returns proper hotspot dictionaries

---

### Root Cause #5: No Bounding Box Filtering
**Why It Happens:**
- NASA FIRMS `/world/` endpoint returns ALL global fire data
- For local analysis, need to filter to region of interest
- Without filtering, get irrelevant hotspots from around the world

**What Was Happening:**
```python
# Original code tried to use API parameters (which don't exist):
params = {
    "latitude": 28.6139,      # ❌ API doesn't accept these
    "longitude": 77.2090,
    "radius_km": 50,
}

# So it got all global data with no filtering
# Then crashed on response parsing
```

**How It Was Fixed:**
```python
# 1. Convert point + radius to bounding box
delta_lat = radius_km / 111.0  # ~111 km per degree latitude
delta_lon = radius_km / (111.0 * cos(radians(lat)))  # ~111 * cos(lat) km per degree

bbox = {
    "west": lon - delta_lon,
    "south": lat - delta_lat,
    "east": lon + delta_lon,
    "north": lat + delta_lat,
}

# 2. Filter CSV results by bounding box
for line in csv_lines:
    lat = float(values[lat_idx])
    lon = float(values[lon_idx])
    
    # Only include if within bbox
    if bbox["south"] <= lat <= bbox["north"] and \
       bbox["west"] <= lon <= bbox["east"]:
        results.append(hotspot_dict)
```

**Why This Works:**
- Gets global data (required by API)
- Filters client-side to region of interest
- Fast: only processes CSV text locally
- Accurate: geometric filtering by standard bbox

---

### Root Cause #6: No Error Logging
**Why It Happens:**
- Original code didn't log request URL or response body
- If request failed, error was invisible
- Impossible to debug what went wrong

**What Was Hidden:**
```python
response = client.get(url, params=params)
if response.status_code >= 400:
    # ❌ Error response discarded!
    # ❌ URL never logged!
    last_error = RuntimeError(f"Request rejected ({response.status_code})")
    continue
```

**How It Was Fixed:**
```python
print(f"NASA FIRMS: Request URL: {url}")
print(f"NASA FIRMS: Parameters: {params}")
logger.debug(f"NASA FIRMS: Full URL: {response.request.url}")

print(f"NASA FIRMS: Response status: {response.status_code}")
if response.status_code >= 400:
    response_text = response.text[:500]
    print(f"NASA FIRMS: Error response: {response_text}")
    logger.error(f"NASA FIRMS: {response_text}")
```

**Example Debug Output:**
```
NASA FIRMS: Request URL: https://firms.modaps.eosdis.nasa.gov/api/v1/data/VIIRS_SNPP/csv/world/date-range/2026-06-24,2026-07-01
NASA FIRMS: Parameters: {'api_key': 'abc123...'}
NASA FIRMS: Response status: 200
NASA FIRMS: Found 5 hotspots from VIIRS_SNPP
```

**Or if error:**
```
NASA FIRMS: Request URL: https://firms.modaps.eosdis.nasa.gov/api/v1/data/VIIRS_SNPP/csv/world/date-range/2026-06-24,2026-07-01
NASA FIRMS: Response status: 401
NASA FIRMS: Error response: {"error": "Invalid API key"}
```

---

## Summary: Why These Fixes Work

### Sentinel Hub
| Issue | Fix | Result |
|-------|-----|--------|
| No timeRange | Added ISO 8601 window | API knows what dates to query |
| Wrong format | Changed to image/tiff | Matches raster output type |
| No geometry | Added polygon from bbox | Removes coordinate ambiguity |
| No cloud filter | Added maxCloudCoverage | Gets quality data |
| No logging | Added full payload logs | Debugging becomes possible |

### NASA FIRMS
| Issue | Fix | Result |
|-------|-----|--------|
| Wrong endpoint | Use `/api/v1/data/...` | API route found and valid |
| Wrong params | Use URL path structure | API accepts request |
| No source | Specify VIIRS_SNPP | API knows which data to query |
| Wrong format | Parse CSV not JSON | Response parsed successfully |
| No bbox filter | Filter CSV by bbox | Get relevant local hotspots |
| No error logging | Log URL and errors | Debugging becomes possible |

---

## Testing the Fixes

### Sentinel Hub Test
```bash
python scripts/debug_geospatial.py --no-firms
# Should show:
# ✓ Sentinel Hub: NDVI fetch successful!
# Result: {"lat": 28.6139, "lon": 77.2090, "ndvi": 0.45, ...}
```

### NASA FIRMS Test
```bash
python scripts/debug_geospatial.py --no-sentinel
# Should show:
# ✓ NASA FIRMS: Hotspot fetch successful!
# Found 2 hotspots
```

### Check Debug Log
```bash
cat debug_geospatial.log
# Should show full request/response details
```

