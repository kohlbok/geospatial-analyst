import math
import numpy as np


EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def haversine_m(lat1, lon1, lat2, lon2):
    return haversine_km(lat1, lon1, lat2, lon2) * 1000


def haversine_vectorized(lats1, lons1, lats2, lons2):
    lats1, lons1 = np.radians(lats1), np.radians(lons1)
    lats2, lons2 = np.radians(lats2), np.radians(lons2)
    dlat = lats2 - lats1
    dlon = lons2 - lons1
    a = np.sin(dlat / 2) ** 2 + np.cos(lats1) * np.cos(lats2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def interpolate_points(lat1, lon1, lat2, lon2, num_points):
    lats = np.linspace(lat1, lat2, num_points)
    lons = np.linspace(lon1, lon2, num_points)
    return lats, lons


def in_bbox(lat, lon, lat_min, lat_max, lon_min, lon_max):
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
