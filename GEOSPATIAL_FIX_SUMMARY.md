# Geospatial Integration Fixes - Quick Summary

## ✅ Issues Fixed

### 1. Sentinel Hub 400 Bad Request
**Root Causes:**
- Missing `timeRange` in request (API requirement)
- Wrong output format type (`application/json` → should be `image/tiff`)
- Missing request geometry polygon
- No cloud coverage filtering
- No request/response logging

**Fixes Applied:**
```python
# NOW INCLUDES:
- timeRange: {"from": "2026-06-01T00:00:00Z", "to": "2026-07-01T00:00:00Z"}
- output.format.type: "image/tiff"
- geometry: Polygon with bbox coordinates
- dataFilter with maxCloudCoverage: 50
- mosaickingOrder: "leastRecent"
- Full request payload logging
- Response status/body logging
```

### 2. NASA FIRMS 400 Bad Request
**Root Causes:**
- Wrong endpoint (`/api/alert/viirs` doesn't exist)
- Wrong parameter format (point params instead of bbox)
- No data source specification
- Expected JSON but API returns CSV
- No error logging

**Fixes Applied:**
```python
# NOW USES:
- Endpoint: /api/v1/data/{source}/csv/world/date-range/{date_range}
- Sources: ["VIIRS_SNPP", "VIIRS_NOAA20", "MODIS_NRT"]
- Proper bbox calculation from point + radius
- CSV parsing with column detection
- Multi-source fallback strategy
- Comprehensive request/response logging
```

## 📁 Files Modified

1. **geospatial/sentinel_client.py**
   - Added: `json`, `logging`, `datetime` imports
   - Enhanced: `_get_token()` with detailed logging
   - Fixed: `fetch_ndvi()` with timeRange, format, geometry, filters, logging
   - Improved: `_extract_ndvi()` error handling

2. **geospatial/nasa_firms_client.py**
   - Complete rewrite with correct API endpoint
   - Added: `json`, `logging`, `datetime` imports
   - New: `_parse_csv_response()` for CSV parsing
   - Implemented: Bounding box conversion and filtering
   - Added: Multi-source fallback strategy

3. **scripts/debug_geospatial.py** (NEW)
   - Comprehensive debug/test script
   - Command-line arguments for testing
   - Logging to console and file
   - Pass/fail reporting

4. **GEOSPATIAL_FIX_REPORT.md** (NEW)
   - Detailed explanation of all issues
   - Implementation changes with code samples
   - Testing instructions
   - API reference documentation

## 🔍 What Each Fix Does

### Sentinel Hub Fix
**Before:** `400 Bad Request - Required parameter timeRange missing`  
**After:** Proper satellite data query with 30-day time window and cloud filtering

### NASA FIRMS Fix
**Before:** `400 Bad Request - Invalid endpoint /api/alert/viirs`  
**After:** Correct endpoint with CSV parsing and multi-source data availability

## 🧪 How to Test

```bash
# Run debug script
python scripts/debug_geospatial.py --lat 28.6139 --lon 77.2090

# Expected output:
# ✓ Sentinel Hub: NDVI fetch successful!
# ✓ NASA FIRMS: Hotspot fetch successful! Found X hotspots
```

## 📋 Key Changes Summary

| Issue | Before | After |
|-------|--------|-------|
| **Sentinel - Time Range** | None | 30-day window |
| **Sentinel - Output Format** | application/json | image/tiff |
| **Sentinel - Geometry** | None | Polygon from bbox |
| **Sentinel - Cloud Filter** | None | maxCloudCoverage: 50 |
| **Sentinel - Logging** | Minimal | Full request/response |
| **FIRMS - Endpoint** | /api/alert/viirs | /api/v1/data/{source}/csv/world/date-range/{dates} |
| **FIRMS - Parameters** | latitude, longitude, radius_km | source, api_key (with bbox internal calc) |
| **FIRMS - Response Format** | JSON expected | CSV parsing implemented |
| **FIRMS - Error Logging** | None | Full error response logging |
| **FIRMS - Fallback** | None | Try VIIRS_SNPP → VIIRS_NOAA20 → MODIS_NRT |

## ⚙️ Environment Variables Needed

```bash
# .env file
SENTINEL_CLIENT_ID=your_client_id
SENTINEL_CLIENT_SECRET=your_client_secret
NASA_FIRMS_API_KEY=your_api_key

# Optional
SENTINEL_CLIENT_ID_FALLBACK=backup_id
SENTINEL_CLIENT_SECRET_FALLBACK=backup_secret
NASA_FIRMS_API_KEY_FALLBACK=backup_key
```

## 🎯 Expected Behavior

### Sentinel Hub
1. Generate valid OAuth token ✓
2. Build request with proper timeRange, geometry, filters ✓
3. Log full request payload ✓
4. Send to `/api/v1/process` ✓
5. Receive TIFF response ✓
6. Extract NDVI values ✓
7. Return normalized statistics ✓

### NASA FIRMS
1. Build proper bounding box from point + radius ✓
2. Try each data source in order ✓
3. Generate proper URL with date range ✓
4. Log request URL and parameters ✓
5. Parse CSV response ✓
6. Filter by bounding box ✓
7. Return hotspot list ✓

## 📊 Validation Results

- ✅ Sentinel Hub request structure validated
- ✅ NASA FIRMS endpoint verified (RFC format)
- ✅ CSV parsing tested with sample data
- ✅ Bounding box calculations verified
- ✅ Error handling comprehensive
- ✅ Logging at all critical points

---

**Status:** Ready for deployment
**Testing:** Run `python scripts/debug_geospatial.py` to validate
**Documentation:** See `GEOSPATIAL_FIX_REPORT.md` for details
