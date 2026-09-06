import datetime
import json
import os
import time
from typing import Dict, Any

import requests


def cache(cache_name, results: Dict[str, Any], cache_dir: str = "cache") -> str:
    print("\nSaving results to cache...")
    os.makedirs(cache_dir, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cache_filename = f"{cache_name}_{timestamp}.json"
    cache_filepath = os.path.join(cache_dir, cache_filename)

    with open(cache_filepath, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results saved to cache file: {cache_filepath}")

    return cache_filepath

def query(session: requests.Session, url: str, timeout, method: str, endpoint, data: Dict[str, Any],
          save_to_cache=True) -> Dict[
    str, Any]:
    response = None
    if method == "get":
        response = session.get(url, params=data, timeout=timeout)
    elif method == "post":
        response = session.post(url, json=data, timeout=timeout)
    response.raise_for_status()
    resp_json = response.json()
    if save_to_cache:
        cache(endpoint.replace("/", "_"), resp_json, "cache")
    return resp_json

class SimilarWebClient:
    def __init__(self, api_token: str, timeout: int = 90,
                 db_path: str = None):
        self.api_token = api_token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json, application/xml',
            'api-key': f'{api_token}',
            'Content-Type': 'application/json'
        })
        self.BASE_URLv4 = "https://api.similarweb.com/batch/v4"
        self.BASE_URLv3 = "https://api.similarweb.com/v3/batch/"

    def submit_request_report(self, domains):
        payload = {
            "report_name": "domain categories",
            "delivery_information": {
                "response_format": "json"
            },
            "report_query": {
                "tables": [
                    {
                        "vtable": "website",
                        "granularity": "monthly",
                        "latest": True,
                        "filters": {
                            "domains": domains,
                            "include_subdomains": True
                        },
                        "metrics": [
                            "main_category"
                        ]
                    }
                ]
            }
        }
        return query(self.session, f"{self.BASE_URLv4}/request-report", self.timeout, "post", "request-report", payload)

    def download_report_as_domain_categories(self, report_id) -> Dict[str, str]:
        counter = 0;

        def _query():
            return query(self.session, f"{self.BASE_URLv3}/request-status/{report_id}", self.timeout, "get",
                         "request-status", {})

        status = _query()
        while counter < 10 and (status is None or status["status"] != "completed"):
            time.sleep(10)
            status = _query()
            counter += 1

        if status is None or status["status"] != "completed":
            raise RuntimeError(
                f"Couldn't get report from Similar Web afte {counter} attempts. What I got was: {status}")

        download_url = status["download_url"]
        response = requests.get(download_url)
        response.raise_for_status()  # raises error if the request failed
        domain_categories = {}
        for line in response.text.splitlines():
            if line.strip():  # skip empty lines
                obj = json.loads(line)
                domain_categories[obj["domain"]] = obj["main_category"]
        return domain_categories
