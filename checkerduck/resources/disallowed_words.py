from __future__ import annotations

import logging
from enum import Enum
from importlib import resources as resources
from typing import Dict, Any, Sequence

import yaml

from checkerduck.model.models import TargetQueryableDomain

log = logging.getLogger(__name__)


class ForbiddenWordCategory(str, Enum):
    FORBIDDEN = "forbidden"
    SPAM = "spam"

def get_disallowed_words() -> Dict[str, Dict[str, Any]]:
    with resources.files("checkerduck.resources").joinpath("disallowed_words.yaml").open("r") as f:
        disallowed_words_data = yaml.safe_load(f)

    return disallowed_words_data


def get_category_forbidden_words_by_lang(targets_with_lang: Sequence[TargetQueryableDomain]) -> Dict[str, Dict[str, str]]:
    category_forbidden_words_by_lang = {tgt.lang: {word: cat for cat in ["forbidden", "spam"] for word in
                                                   get_disallowed_words_by_lang_fallback(get_disallowed_words(),
                                                                                         tgt.lang).get(cat, [])}
                                        for tgt in targets_with_lang}
    return category_forbidden_words_by_lang


def get_disallowed_words_by_lang_fallback(disallowed_words_by_lang: Dict[str, Dict[str, str]], lang: str) -> Dict[str, str]:
    fallback_language = "en"
    l = lang
    if lang not in disallowed_words_by_lang:
        log.warning("no disallowed words for lang %s, falling back to %s", lang, fallback_language)
        l = fallback_language
    return disallowed_words_by_lang[l]
