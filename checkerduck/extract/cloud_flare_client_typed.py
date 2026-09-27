import logging
import os
from typing import Sequence, Mapping


from checkerduck.db.db import get_thread_connection, init_database
from checkerduck.db.store import Store
from checkerduck.extract.client_typed import TypedHTTPJSONClient, new_endpoint, Outcome, Fetched
from checkerduck.extract.cloud_flare_models import RadarDomainResponse, RadarCategory
from checkerduck.model.models import TargetQueryableDomain


log = logging.getLogger(__name__)


def extract_categories(response: RadarDomainResponse) -> Mapping[str, list[RadarCategory]]:
    return {d.domain: d.all_content_categories() for d in response.result}


class TypedCloudFlareClient(TypedHTTPJSONClient):

    def __init__(self, api_token: str, account_id: str, timeout: int = 90):
        super().__init__(f"https://api.cloudflare.com/client/v4",
                         api_token, timeout)
        self.INTEL_CATEGORY_ENDPOINT = new_endpoint(f"/accounts/{account_id}/intel/domain/bulk", RadarDomainResponse, RadarCategory,
                                           extract_categories)

    def query_domain_categories(
            self, targets: Sequence[TargetQueryableDomain]) -> Mapping[TargetQueryableDomain, Outcome]:
        chunk_size = 100
        chunks = [targets[i:i + chunk_size] for i in range(0, len(targets), chunk_size)]
        res = {}
        for chunk in chunks:
            res.update(self._fetch_bulk_domain_rows(chunk, self.INTEL_CATEGORY_ENDPOINT, {"domain": [d.domain for d in chunk]}))

        return res


if __name__ == "__main__":
    init_database()
    client = TypedCloudFlareClient(api_token=os.environ["CF_TOKEN"], account_id=os.environ["CF_ACCOUNT_ID"])
    domain = TargetQueryableDomain(domain="microsoft.com")
    res = client.query_domain_categories(targets=[TargetQueryableDomain(domain="microsoft.com"),
                                                  TargetQueryableDomain(domain="nvidia.com")])
    store = Store(get_thread_connection)

    match res[domain]:
        case Fetched(val) as f:
            log.info("%s", f.rows)
    store.persist_domain_categories_cloudflare("---", res)
