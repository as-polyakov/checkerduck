from importlib import resources as resources

import yaml

with resources.files("checkerduck.resources").joinpath("langs.yaml").open("r") as f:
    lang_by_country = yaml.safe_load(f)


def get_lang_by_country(country: str) -> str:
    return lang_by_country[country.lower()]
