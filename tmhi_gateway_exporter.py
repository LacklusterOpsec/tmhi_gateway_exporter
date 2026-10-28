import requests
from time import sleep
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY
import json  # For optional debugging/logging

class ArcadyanCollector:
    def collect(self):
        metrics_url = 'http://192.168.12.1/TMI/v1/gateway?get=all'

        try:
            response = requests.get(metrics_url, timeout=3)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[ERROR] Failed to fetch or parse data: {e}")
            return  # Do not yield anything on error

        rsrp = GaugeMetricFamily('gateway_rsrp', 'RSRP', labels=['nbid', 'cid', 'band'])
        rsrq = GaugeMetricFamily('gateway_rsrq', 'RSRQ', labels=['nbid', 'cid', 'band'])
        rssi = GaugeMetricFamily('gateway_rssi', 'RSSI', labels=['nbid', 'cid', 'band'])
        sinr = GaugeMetricFamily('gateway_sinr', 'SINR', labels=['nbid', 'cid', 'band'])

        json_to_metric = {
            'rsrp': rsrp,
            'rsrq': rsrq,
            'rssi': rssi,
            'sinr': sinr
        }

        signal = data.get('signal', {})
        for gen in ['4g', '5g']:
            cell = signal.get(gen)
            if not cell:
                continue

            nbid = str(cell.get('eNBID', 'unknown'))
            cid = str(cell.get('cid', 'unknown'))
            bands = cell.get('bands', [])

            for band in bands:
                for key, metric in json_to_metric.items():
                    value = cell.get(key)
                    if value is not None:
                        try:
                            metric.add_metric([nbid, cid, band], float(value))
                        except (ValueError, TypeError):
                            print(f"[WARN] Invalid value for {key}: {value}")

        yield rsrp
        yield rsrq
        yield rssi
        yield sinr

def main():
    REGISTRY.register(ArcadyanCollector())
    print("[INFO] Exporter started on http://localhost:9715")
    start_http_server(9715)
    while True:
        sleep(1.0)

if __name__ == '__main__':
    main()
