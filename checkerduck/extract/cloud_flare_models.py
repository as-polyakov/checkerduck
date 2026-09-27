import msgspec


class RadarCategory(msgspec.Struct, frozen=True):
    id: int
    name: str
    super_category_id: int | None = None



class RadarDomain(msgspec.Struct, frozen=True):
    domain: str
    content_categories: list[RadarCategory] = []
    inherited_content_categories: list[RadarCategory] = []
    def all_content_categories(self) -> list[RadarCategory]:
        return self.content_categories + self.inherited_content_categories


class RadarDomainResponse(msgspec.Struct, frozen=True):
    result: list[RadarDomain]
