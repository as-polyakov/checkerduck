import msgspec


class RadarCategory(msgspec.Struct, frozen=True):
    id: int
    name: str
    super_category_id: int | None = None



class RadarDomain(msgspec.Struct, frozen=True):
    domain: str
    content_categories: list[RadarCategory]


class RadarDomainResponse(msgspec.Struct, frozen=True):
    result: list[RadarDomain]
