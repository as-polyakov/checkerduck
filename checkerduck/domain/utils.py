from typing import Optional
from urllib.parse import urlparse

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def url_to_domain(url: str) -> str:
    url = url.strip().strip("'\"")  # remove stray quotes
    if "://" not in url:
        url = "https://" + url  # add dummy scheme so urlparse works
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    return domain.rstrip('/')


def safe_int(value) -> Optional[int]:
    return int(value) if value else None


def safe_float(value) -> Optional[float]:
    return float(value) if value else None