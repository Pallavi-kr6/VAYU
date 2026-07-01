from typing import Any, Dict, List, Tuple
import httpx
 
import logging
from io import BytesIO
import rasterio
import numpy as np
from datetime import datetime, timedelta

from config.settings import (
    SENTINEL_CLIENT_ID,
    SENTINEL_CLIENT_SECRET,
    SENTINEL_CLIENT_ID_FALLBACK,
    SENTINEL_CLIENT_SECRET_FALLBACK,
)

logger = logging.getLogger(__name__)


class SentinelClient:
    """Standalone Sentinel Hub client for NDVI fetches."""

    AUTH_URL = "https://services.sentinel-hub.com/oauth/token"
    DATA_URL = "https://services.sentinel-hub.com/api/v1/process"

    def __init__(self, client_id: str = None, client_secret: str = None):
        primary_client_id = client_id or SENTINEL_CLIENT_ID
        primary_client_secret = client_secret or SENTINEL_CLIENT_SECRET
        self._credential_pairs = self._build_credential_pairs(primary_client_id, primary_client_secret)
        self.client_id = primary_client_id
        self.client_secret = primary_client_secret
        self.token = None
        self.token_expires_at = None
        self.available = bool(self._credential_pairs)

    def authenticated(self) -> bool:
        return bool(self._credential_pairs)

    def is_available(self) -> bool:
        return self.available and self.authenticated()

    def _build_credential_pairs(self, client_id: str, client_secret: str) -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        for candidate_id, candidate_secret in [
            (client_id, client_secret),
            (SENTINEL_CLIENT_ID_FALLBACK, SENTINEL_CLIENT_SECRET_FALLBACK),
        ]:
            if candidate_id and candidate_secret and (candidate_id, candidate_secret) not in pairs:
                pairs.append((candidate_id, candidate_secret))
        return pairs

    def _get_token(self) -> str:
        if not self.authenticated():
            self.available = False
            print("Sentinel Hub: no credentials configured")
            logger.error("Sentinel Hub: no credentials configured")
            raise ValueError("Sentinel Hub credentials not configured")

        last_error: Exception | None = None
        for index, (credential_id, credential_secret) in enumerate(self._credential_pairs, start=1):
            self.client_id = credential_id
            self.client_secret = credential_secret
            print(f"Sentinel Hub: trying credential set {index}/{len(self._credential_pairs)}")
            print(f"  Client ID: {credential_id[:20]}...")
            try:
                resp = httpx.post(
                    self.AUTH_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    timeout=15.0,
                )
                logger.debug(f"Sentinel Hub auth response status: {resp.status_code}")
                if resp.status_code in {401, 403}:
                    print(f"Sentinel Hub: credential set {index} rejected with status {resp.status_code}")
                    logger.warning(f"Sentinel Hub: credential set {index} rejected ({resp.status_code})")
                    last_error = RuntimeError(f"Sentinel Hub authentication rejected ({resp.status_code})")
                    continue
                resp.raise_for_status() 
                payload = resp.json()
                self.token = payload.get("access_token")
                if self.token:
                    print(f"Sentinel Hub: credential set {index} authenticated successfully")
                    print(f"  Token: {self.token[:20]}... (expires in {payload.get('expires_in', 'unknown')} seconds)")
                    logger.info(f"Sentinel Hub: authenticated with credential set {index}")
                    return self.token
                print("Sentinel Hub: authentication response did not contain an access token")
                logger.error(f"Sentinel Hub: no access_token in response: {payload}")
                last_error = RuntimeError("Sentinel Hub authentication returned no access token")
            except Exception as exc:
                print(f"Sentinel Hub: credential set {index} failed - {exc}")
                logger.error(f"Sentinel Hub: credential set {index} failed - {exc}")
                last_error = exc

        self.available = False
        if last_error is not None:
            raise RuntimeError(f"Sentinel Hub auth failed: {last_error}") from last_error
        raise RuntimeError("Sentinel Hub auth failed")

    def fetch_ndvi(self, lat: float, lon: float, bbox_size_km: float = 1.0) -> Dict[str, Any]:
        """Fetch NDVI statistics around a point using Sentinel Hub process API."""
        if not self.is_available():
            print("Sentinel Hub: unavailable because no valid credentials were configured")
            raise RuntimeError("Sentinel Hub unavailable")

        token = self._get_token()
        bbox = self._build_bbox(lat, lon, bbox_size_km)
        evalscript = self._ndvi_evalscript()

        # Generate time range for the last 30 days (typical for NDVI queries)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=30)
        
        body = {
            "input": {
                "bounds": {
                    "bbox": [
                        bbox[1],  # west
                        bbox[0],  # south
                        bbox[3],  # east
                        bbox[2],  # north
                    ],
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                    },
                    "geometry": {
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
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{start_time.isoformat()}Z",
                                "to": f"{end_time.isoformat()}Z"
                            },
                            "mosaickingOrder": "leastRecent",
                            "maxCloudCoverage": 50
                        }
                    }
                ]
            },
            "output": {
                "width": 64,
                "height": 64,
                "responses": [
                    {
                        "identifier": "default",
                        "format": {
                            "type": "image/tiff"
                        }
                    }
                ]
            },
            "evalscript": evalscript
        }

        # Log the complete request payload for debugging
         
        print(f"Sentinel Hub: Sending NDVI request for lat={lat}, lon={lon}")
        print(f"  BBox: west={bbox[1]}, south={bbox[0]}, east={bbox[3]}, north={bbox[2]}")
        print(f"  Time range: {start_time.isoformat()}Z to {end_time.isoformat()}Z")
        print(f"  Authorization: Bearer {token[:20]}...")

        try:
            resp = httpx.post(
                self.DATA_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
                timeout=30.0,
            )
            
            # Log response status and headers
            print(f"Sentinel Hub: Response status: {resp.status_code}")
            print(f"Sentinel Hub: Response headers: {dict(resp.headers)}")
            
            if resp.status_code >= 400:
                response_text = resp.text[:500]
                print(f"Sentinel Hub: Response body: {response_text}")
                logger.error(f"Sentinel Hub error response: {response_text}")
            
            resp.raise_for_status()
            tiff_bytes = resp.content

            # Parse TIFF response
            with rasterio.open(BytesIO(tiff_bytes)) as dataset:
                ndvi_array = dataset.read(1)  # Read the first band
            
            valid_pixels = ndvi_array[
                np.isfinite(ndvi_array)
                & (ndvi_array >= -1.0)
                & (ndvi_array <= 1.0)
            ]
            avg_ndvi = (
                float(valid_pixels.mean())
                if len(valid_pixels) > 0
                else 0.0
            )
            
            print(f"Sentinel Hub: Calculated average NDVI = {avg_ndvi:.4f}")
            if len(valid_pixels) > 0:
                print(
                    f"NDVI stats -> "
                    f"min={valid_pixels.min():.4f}, "
                    f"max={valid_pixels.max():.4f}, "
                    f"mean={avg_ndvi:.4f}"
                )
            else:
                print("NDVI stats -> no valid pixels found")
            
            return {
                "lat": lat,
                "lon": lon,
                "ndvi": avg_ndvi,
                "source": "sentinel_hub",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        except Exception as exc:
            print(f"Sentinel Hub: NDVI fetch failed - {exc}")
            logger.error(f"Sentinel Hub: NDVI fetch failed - {exc}")
            raise RuntimeError(f"Sentinel Hub NDVI fetch failed: {exc}") from exc

    def _build_bbox(self, lat: float, lon: float, radius_km: float) -> tuple:
        delta = radius_km / 111.0
        return (lat - delta, lon - delta, lat + delta, lon + delta)

    def _ndvi_evalscript(self) -> str:
        return """
            //VERSION=3
            function setup() {
                return {
                    input: [{
                        bands: ["B04", "B08"],
                        units: "REFLECTANCE"
                    }],
                    output: [{
                        id: "default",
                        bands: 1,
                        sampleType: "FLOAT32"
                    }]
                };
            }

            function evaluatePixel(sample) {
                let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-6);
                return [ndvi];
            }
        """

    def _extract_ndvi(self, payload: Dict[str, Any]) -> float:
        """Extract NDVI value from response payload.
        
        Handles both JSON and binary TIFF responses.
        For JSON responses, extracts from outputs array.
        For binary TIFF responses, returns 0.0 (would need proper TIFF parsing library).
        """
        if not isinstance(payload, dict):
            logger.warning(f"Unexpected Sentinel Hub payload type: {type(payload)}")
            return 0.0

        # Handle JSON response format
        data = payload.get("outputs") or []
        if not data:
            logger.warning("No outputs in Sentinel Hub response")
            return 0.0

        first = data[0].get("data") or {}
        values = first.get("values")
        if not values or not isinstance(values, list):
            logger.warning("No values array in Sentinel Hub response")
            return 0.0

        flattened = [v for row in values for v in (row if isinstance(row, list) else [row])]
        numeric = [float(v) for v in flattened if isinstance(v, (int, float))]
        if not numeric:
            logger.warning("No numeric values in Sentinel Hub response")
            return 0.0
        
        result = sum(numeric) / len(numeric)
        logger.debug(f"Extracted NDVI value: {result} from {len(numeric)} pixels")
        return result
