#!/usr/bin/env python3

import os
import sys
import requests
import time
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from tenacity import retry, wait_exponential, stop_after_attempt

# Early check for missing SSL module (common in stripped-down Python builds)
try:
    import ssl
except ImportError:
    print("[FATAL] The 'ssl' module is required but missing. Ensure your Python environment has OpenSSL support.", file=sys.stderr)
    sys.exit(1)

# URL to fetch metrics from the Arcadyan modem
METRICS_URL = 'http://192.168.12.1/TMI/v1/gateway?get=all'

class ArcadyanCollector:
    def __init__(self):
        # Simple in-memory cache to avoid querying the modem too frequently
        self._cache = None
        self._last_fetch = 0
        self._cache_ttl = 5  # seconds

    def collect(self):
        # Serve from cache if it's still valid
        now = time.time()
        if not self._cache or (now - self._last_fetch) > self._cache_ttl:
            self._cache = self._fetch_metrics()
            self._last_fetch = now

        # Yield all collected metrics to Prometheus
        for metric in self._cache:
            yield metric

    # Retry HTTP fetch with exponential backoff, up to 3 attempts
    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    def _get_json(self):
        # Make a GET request to the modem's metrics endpoint
        response = requests.get(METRICS_URL, timeout=3)
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()  # Parse and return JSON

    def _fetch_metrics(self):
        try:
            data = self._get_json()
        except Exception as e:
            print(f"[ERROR] Failed to fetch or parse data: {e}", file=sys.stderr)
            return []

        metrics = []

        # Define Prometheus gauge metrics for signal strength indicators
        rsrp = GaugeMetricFamily('gateway_rsrp', 'RSRP (Reference Signal Received Power)', labels=['nbid', 'cid', 'band'])
        rsrq = GaugeMetricFamily('gateway_rsrq', 'RSRQ (Reference Signal Received Quality)', labels=['nbid', 'cid', 'band'])
        rssi = GaugeMetricFamily('gateway_rssi', 'RSSI (Received Signal Strength Indicator)', labels=['nbid', 'cid', 'band'])
        sinr = GaugeMetricFamily('gateway_sinr', 'SINR (Signal to Interference plus Noise Ratio)', labels=['nbid', 'cid', 'band'])

        # Map signal keys to corresponding metric families
        json_to_metric = {
            'rsrp': rsrp,
            'rsrq': rsrq,
            'rssi': rssi,
            'sinr': sinr
        }

        signal = data.get('signal', {})

        # Iterate over both 4G and 5G signal data if present
        for gen in ['4g', '5g']:
            cell = signal.get(gen)
            if not cell:
                continue  # Skip if signal generation not available

            # Get identifying cell information (fallback to 'unknown' if missing)
            nbid = str(cell.get('eNBID', 'unknown'))
            cid = str(cell.get('cid', 'unknown'))
            bands = cell.get('bands', [])

            # Add signal values to Prometheus metrics per band
            for band in bands:
                for key, metric in json_to_metric.items():
                    value = cell.get(key)
                    if value is not None:
                        try:
                            metric.add_metric([nbid, cid, band], float(value))
                        except (ValueError, TypeError):
                            print(f"[WARN] Invalid value for {key} in {gen}: {value}", file=sys.stderr)

        # Add all signal metrics to the list to be returned
        metrics.extend([rsrp, rsrq, rssi, sinr])

        # Add basic modem network information as a labeled info metric
        status = data.get('status', {}).get('network', {}).get('status', 'unknown')
        operator = data.get('network', {}).get('operator', {}).get('name', 'unknown')

        info = GaugeMetricFamily("gateway_info", "Modem network info", labels=["operator", "status"])
        info.add_metric([operator, status], 1)
        metrics.append(info)

        return metrics

def main():
    # Register the custom collector with Prometheus registry
    REGISTRY.register(ArcadyanCollector())
    print("[INFO] Exporter started on http://localhost:9715")

    # Start HTTP server for Prometheus to scrape
    start_http_server(9715)

    # Keep the exporter running continuously
    while True:
        time.sleep(1.0)

if __name__ == '__main__':
    main()
