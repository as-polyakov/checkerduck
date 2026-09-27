import logging

import yaml
from importlib import resources as resources

log = logging.getLogger(__name__)


class CloudFlareCategory:
    _categories = yaml.safe_load(resources.files("checkerduck.resources").joinpath("cloudflare_categories.yaml").read_text())

    _all_categories = {k: v['name'] for k, v in _categories['categories'].items()}

    for k, v in _categories['categories'].items():
        if 'subcategories' in v:
            for s, n in v['subcategories'].items():
                _all_categories[s] = n

    def __init__(self, id: int, super_category_id: int | None):
        self.id = id
        self.super_category_id = super_category_id
        self.name = self._all_categories[int(self.id)]

    @classmethod
    def get_category_name(cls, id: int):
        return cls._all_categories[int(id)]

    def full_category(self) -> str:
        if self.super_category_id is None:
            return self.name
        parent = CloudFlareCategory.get_category_name(self.super_category_id)

        if parent == self.name:
            return self.name

        return f"{parent}: {self.name}"


if __name__ == "__main__":
    c = CloudFlareCategory.get_category_name(30)
    log.debug("%s", c)
