# data/enforcement_assets.py
# ─────────────────────────────────────────────────────────
# City-specific enforcement target database.
# Sources: CPCB non-attainment lists, urbanemissions.info, OSM industrial zones.
# Each record is tied to one city — never cross-city reuse.
# ─────────────────────────────────────────────────────────

from typing import List, Optional

# type maps to attribution source keys (without src_ prefix)
ENFORCEMENT_ASSETS: dict[str, list[dict]] = {
    "delhi": [
        {"id": "DEL-VEH001", "name": "Anand Vihar Interstate Bus Terminal", "type": "vehicle", "lat": 28.646, "lon": 77.316, "violations": 5, "last_check": "2025-09-20"},
        {"id": "DEL-IND001", "name": "Bharat Steel Rolling Mill Wazirpur", "type": "industrial", "lat": 28.698, "lon": 77.168, "violations": 3, "last_check": "2025-11-10"},
        {"id": "DEL-CON001", "name": "DDA Housing Project Dwarka Sector 9", "type": "construction", "lat": 28.592, "lon": 77.046, "violations": 2, "last_check": "2025-10-15"},
        {"id": "DEL-CON002", "name": "Central Vista Redevelopment Site", "type": "construction", "lat": 28.613, "lon": 77.229, "violations": 1, "last_check": "2025-12-01"},
        {"id": "DEL-BIO001", "name": "Ghazipur Landfill Open Burning Zone", "type": "biomass", "lat": 28.622, "lon": 77.318, "violations": 4, "last_check": "2025-11-28"},
    ],
    "mumbai": [
        {"id": "MUM-VEH001", "name": "BEST Depot Mazgaon Diesel Fleet", "type": "vehicle", "lat": 18.966, "lon": 72.842, "violations": 4, "last_check": "2025-10-05"},
        {"id": "MUM-IND001", "name": "Tata Power Trombay Thermal Station", "type": "industrial", "lat": 19.005, "lon": 72.915, "violations": 2, "last_check": "2025-11-15"},
        {"id": "MUM-CON001", "name": "Coastal Road Phase 2 Construction", "type": "construction", "lat": 18.978, "lon": 72.818, "violations": 1, "last_check": "2025-12-08"},
        {"id": "MUM-IND002", "name": "Dharavi Small-Scale Foundries Cluster", "type": "industrial", "lat": 19.043, "lon": 72.856, "violations": 3, "last_check": "2025-09-30"},
        {"id": "MUM-BIO001", "name": "Deonar Dumping Ground Emission Zone", "type": "biomass", "lat": 19.046, "lon": 72.919, "violations": 5, "last_check": "2025-11-01"},
    ],
    "bengaluru": [
        {"id": "BLR-IND001", "name": "Peenya Industrial Area Foundries", "type": "industrial", "lat": 13.028, "lon": 77.511, "violations": 3, "last_check": "2025-10-20"},
        {"id": "BLR-VEH001", "name": "Silk Board Junction Traffic Corridor", "type": "vehicle", "lat": 12.918, "lon": 77.622, "violations": 2, "last_check": "2025-11-12"},
        {"id": "BLR-CON001", "name": "Metro Phase 3 Whitefield Corridor", "type": "construction", "lat": 12.970, "lon": 77.749, "violations": 1, "last_check": "2025-12-05"},
        {"id": "BLR-BIO001", "name": "Bellandur Lake Surrounding Dump Sites", "type": "biomass", "lat": 12.935, "lon": 77.678, "violations": 4, "last_check": "2025-10-28"},
        {"id": "BLR-CON002", "name": "ORR Elevated Corridor Construction", "type": "construction", "lat": 12.935, "lon": 77.612, "violations": 2, "last_check": "2025-11-18"},
    ],
    "kolkata": [
        {"id": "KOL-IND001", "name": "Howrah Jute Mill Cluster", "type": "industrial", "lat": 22.585, "lon": 88.346, "violations": 3, "last_check": "2025-10-10"},
        {"id": "KOL-VEH001", "name": "Vidyasagar Setu Approach Traffic", "type": "vehicle", "lat": 22.561, "lon": 88.301, "violations": 2, "last_check": "2025-11-05"},
        {"id": "KOL-BIO001", "name": "Dhapa Dumping Ground Burning Zone", "type": "biomass", "lat": 22.548, "lon": 88.401, "violations": 5, "last_check": "2025-11-22"},
        {"id": "KOL-IND002", "name": "Kidderpore Dock Coal Handling", "type": "industrial", "lat": 22.543, "lon": 88.317, "violations": 4, "last_check": "2025-09-15"},
        {"id": "KOL-CON001", "name": "East Kolkata Wetlands Road Project", "type": "construction", "lat": 22.502, "lon": 88.452, "violations": 1, "last_check": "2025-12-02"},
    ],
    "chennai": [
        {"id": "CHE-IND001", "name": "Manali Petrochemical Industrial Estate", "type": "industrial", "lat": 13.172, "lon": 80.258, "violations": 3, "last_check": "2025-10-18"},
        {"id": "CHE-IND002", "name": "Ennore Port Coal Terminal", "type": "industrial", "lat": 13.240, "lon": 80.318, "violations": 4, "last_check": "2025-11-08"},
        {"id": "CHE-VEH001", "name": "Kathipara Junction Vehicle Corridor", "type": "vehicle", "lat": 13.010, "lon": 80.212, "violations": 2, "last_check": "2025-11-25"},
        {"id": "CHE-CON001", "name": "OMR Metro Extension Construction", "type": "construction", "lat": 12.981, "lon": 80.251, "violations": 1, "last_check": "2025-12-10"},
        {"id": "CHE-BIO001", "name": "Kodungaiyur Dump Yard Emission Zone", "type": "biomass", "lat": 13.130, "lon": 80.242, "violations": 3, "last_check": "2025-10-30"},
    ],
    "hyderabad": [
        {"id": "HYD-IND001", "name": "Patancheru Pharma Chemical Belt", "type": "industrial", "lat": 17.529, "lon": 78.264, "violations": 5, "last_check": "2025-09-25"},
        {"id": "HYD-VEH001", "name": "Uppal Ring Road Diesel Depot", "type": "vehicle", "lat": 17.401, "lon": 78.559, "violations": 3, "last_check": "2025-11-14"},
        {"id": "HYD-CON001", "name": "Regional Ring Road Phase 1 Site", "type": "construction", "lat": 17.385, "lon": 78.487, "violations": 2, "last_check": "2025-12-01"},
        {"id": "HYD-IND002", "name": "Jeedimetla Industrial Estate", "type": "industrial", "lat": 17.499, "lon": 78.458, "violations": 2, "last_check": "2025-10-22"},
        {"id": "HYD-BIO001", "name": "Jawahar Nagar Dump Burning Reports", "type": "biomass", "lat": 17.412, "lon": 78.528, "violations": 4, "last_check": "2025-11-05"},
    ],
}


def get_enforcement_assets(city: str) -> List[dict]:
    """Return enforcement targets for a city, or empty list if unknown."""
    key = city.lower().strip()
    return [dict(a) for a in ENFORCEMENT_ASSETS.get(key, [])]


def has_enforcement_assets(city: str) -> bool:
    return bool(get_enforcement_assets(city))
