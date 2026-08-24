"""为动态城市规划采集并校验景点、餐饮和住宿 POI 候选。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

import httpx

from app.services.city_registry_service import normalize_city_name
from app.services.map_service import AmapServiceError, search_places


logger = logging.getLogger(__name__)


class CandidateCollectionUnavailableError(RuntimeError):
    """地图服务不可用，无法完成动态候选采集。"""

    def __init__(
        self,
        message: str,
        reason: str | None = None,
        category: str | None = None,
    ) -> None:
        """记录候选采集失败的安全原因及受影响类别。

        Args:
            message: 可安全展示给调用方的错误描述。
            reason: 可选的地图错误码或内部失败分类。
            category: 采集失败的候选类别。
        """
        super().__init__(message)
        self.reason = reason
        self.category = category


class PlaceCandidateCategory(StrEnum):
    """动态规划当前支持的候选类别。"""

    SPOT = "spot"
    MEAL = "meal"
    HOTEL = "hotel"


@dataclass(frozen=True)
class PlaceCandidate:
    """可进入动态 Planner 候选池的地图实体。"""

    poi_id: str
    name: str
    category: PlaceCandidateCategory
    address: str | None
    city: str | None
    district: str | None
    type_name: str | None
    latitude: float
    longitude: float
    image_url: str | None
    source_type: str = "amap_poi"


@dataclass
class CityCandidatePool:
    """指定城市的三类候选以及覆盖校验结果。"""

    city: str
    adcode: str | None
    administrative_level: str | None = None
    candidates: dict[PlaceCandidateCategory, list[PlaceCandidate]] = field(
        default_factory=dict
    )
    minimum_counts: dict[PlaceCandidateCategory, int] = field(default_factory=dict)

    def candidates_for(
        self,
        category: PlaceCandidateCategory,
    ) -> list[PlaceCandidate]:
        """返回指定类别候选；类别尚未采集时返回空列表。

        Args:
            category: 景点、餐饮或住宿类别。

        Returns:
            list[PlaceCandidate]: 对应类别的候选实体列表。
        """
        return self.candidates.get(category, [])

    @property
    def shortages(self) -> dict[PlaceCandidateCategory, int]:
        """计算每个未达最低覆盖要求的类别还缺少多少候选。

        Returns:
            dict[PlaceCandidateCategory, int]: 未达标类别及其缺口数量。
        """
        return {
            category: minimum - len(self.candidates_for(category))
            for category, minimum in self.minimum_counts.items()
            if len(self.candidates_for(category)) < minimum
        }

    @property
    def meets_minimum(self) -> bool:
        """判断景点、餐饮和住宿候选是否均达到规划阈值。

        Returns:
            bool: 所有类别均无缺口时为 ``True``。
        """
        return not self.shortages


DEFAULT_MINIMUM_COUNTS: dict[PlaceCandidateCategory, int] = {
    PlaceCandidateCategory.SPOT: 8,
    PlaceCandidateCategory.MEAL: 12,
    PlaceCandidateCategory.HOTEL: 8,
}

_CATEGORY_SEARCHES: dict[PlaceCandidateCategory, tuple[str, str]] = {
    PlaceCandidateCategory.SPOT: ("景点", "风景名胜"),
    PlaceCandidateCategory.MEAL: ("美食", "餐饮服务"),
    PlaceCandidateCategory.HOTEL: ("酒店", "住宿服务"),
}

_CATEGORY_LABELS: dict[PlaceCandidateCategory, str] = {
    PlaceCandidateCategory.SPOT: "景点",
    PlaceCandidateCategory.MEAL: "餐饮",
    PlaceCandidateCategory.HOTEL: "住宿",
}


def _place_text(value: object) -> str:
    """把高德响应字段安全转换为去除首尾空白的文本。

    Args:
        value: 高德响应中的任意字段值。

    Returns:
        str: 清洗后的文本；空值或复杂结构返回空字符串。
    """
    if value is None or isinstance(value, (list, dict)):
        return ""
    return str(value).strip()


def _valid_adcode(value: object) -> str | None:
    """规范化六位行政区代码，无效值返回 ``None``。

    Args:
        value: 待校验的行政区代码字段。

    Returns:
        str | None: 合法六位数字代码，或 ``None``。
    """
    adcode = _place_text(value)
    return adcode if len(adcode) == 6 and adcode.isdigit() else None


def _belongs_to_administrative_area(
    place_adcode: str,
    target_adcode: str,
    administrative_level: str | None,
) -> bool:
    """按行政区层级比较 POI adcode，支持地级市和区县级目的地。"""
    level = administrative_level
    if level is None:
        if target_adcode.endswith("0000"):
            level = "province"
        elif target_adcode.endswith("00"):
            level = "city"
        else:
            level = "district"

    if level == "province":
        return place_adcode[:2] == target_adcode[:2]
    if level == "city":
        return place_adcode[:4] == target_adcode[:4]
    if level == "district":
        return place_adcode == target_adcode
    return False


def _belongs_to_city_name(place: Mapping[str, object], city: str) -> bool:
    """在 adcode 缺失时，用城市名做保守的范围校验。"""
    place_city = _place_text(place.get("cityname"))
    if not place_city:
        return True

    normalized_city = normalize_city_name(city)
    normalized_place_city = normalize_city_name(place_city)
    return (
        normalized_city == normalized_place_city
        or normalized_city in normalized_place_city
        or normalized_place_city in normalized_city
    )


def _belongs_to_target_area(
    place: Mapping[str, object],
    city: str,
    adcode: str | None,
    administrative_level: str | None,
) -> bool:
    """优先按 adcode、缺失时按城市名判断 POI 是否属于目标区域。

    Args:
        place: 高德 POI 原始记录。
        city: 目标城市名称。
        adcode: 可选的目标行政区代码。
        administrative_level: 省、市或区县层级。

    Returns:
        bool: POI 可确认属于目标区域时为 ``True``。
    """
    target_adcode = _valid_adcode(adcode)
    place_adcode = _valid_adcode(place.get("adcode"))
    if target_adcode is not None and place_adcode is not None:
        return _belongs_to_administrative_area(
            place_adcode,
            target_adcode,
            administrative_level,
        )
    return _belongs_to_city_name(place, city)


def _to_candidate(
    place: Mapping[str, object],
    city: str,
    category: PlaceCandidateCategory,
    adcode: str | None = None,
    administrative_level: str | None = None,
) -> PlaceCandidate | None:
    """把通过地域和必要字段校验的地图记录转换为候选实体。

    Args:
        place: 高德 POI 原始记录。
        city: 目标城市名称。
        category: 候选业务类别。
        adcode: 可选的目标行政区代码。
        administrative_level: 可选的目标行政区层级。

    Returns:
        PlaceCandidate | None: 合法候选；字段不足或跨区域时返回 ``None``。
    """
    poi_id = _place_text(place.get("poi_id"))
    name = _place_text(place.get("name"))
    latitude = place.get("latitude")
    longitude = place.get("longitude")

    if not poi_id or not name or not _belongs_to_target_area(
        place,
        city=city,
        adcode=adcode,
        administrative_level=administrative_level,
    ):
        return None
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None

    return PlaceCandidate(
        poi_id=poi_id,
        name=name,
        category=category,
        address=_place_text(place.get("address")) or None,
        city=_place_text(place.get("cityname")) or None,
        district=_place_text(place.get("adname")) or None,
        type_name=_place_text(place.get("type")) or None,
        latitude=float(latitude),
        longitude=float(longitude),
        image_url=_place_text(place.get("image_url")) or None,
    )


def _filter_candidates(
    places: list[dict[str, object]],
    city: str,
    category: PlaceCandidateCategory,
    adcode: str | None = None,
    administrative_level: str | None = None,
) -> list[PlaceCandidate]:
    """过滤无效或跨区域 POI，并按 ID 或坐标组合去重。

    Args:
        places: 高德地点搜索返回的原始记录列表。
        city: 目标城市名称。
        category: 当前记录对应的候选类别。
        adcode: 可选的目标行政区代码。
        administrative_level: 可选的目标行政区层级。

    Returns:
        list[PlaceCandidate]: 顺序稳定且已去重的有效候选。
    """
    candidates: list[PlaceCandidate] = []
    seen_keys: set[str] = set()

    for place in places:
        candidate = _to_candidate(
            place,
            city=city,
            category=category,
            adcode=adcode,
            administrative_level=administrative_level,
        )
        if candidate is None:
            continue

        dedupe_key = candidate.poi_id or (
            f"{candidate.name}:{candidate.longitude:.6f}:{candidate.latitude:.6f}"
        )
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        candidates.append(candidate)

    return candidates


def collect_city_candidate_pool(
    city: str,
    adcode: str | None = None,
    administrative_level: str | None = None,
    page_size: int = 25,
    minimum_counts: Mapping[PlaceCandidateCategory, int] | None = None,
) -> CityCandidatePool:
    """采集城市三类候选，并计算是否达到动态规划最低覆盖。"""
    normalized_city = normalize_city_name(city)
    resolved_minimums = dict(minimum_counts or DEFAULT_MINIMUM_COUNTS)
    candidates: dict[PlaceCandidateCategory, list[PlaceCandidate]] = {}

    for category, (keyword, type_name) in _CATEGORY_SEARCHES.items():
        try:
            places = search_places(
                keyword=keyword,
                city=adcode or normalized_city,
                page_size=page_size,
                types=type_name,
                city_limit=True,
            )
        except AmapServiceError as exc:
            logger.warning(
                "candidate collection failed: city=%s category=%s reason=%s message=%s",
                normalized_city,
                category.value,
                exc.reason or "amap_error",
                str(exc),
            )
            raise CandidateCollectionUnavailableError(
                f"暂时无法获取“{normalized_city}”的{_CATEGORY_LABELS[category]}候选，请稍后重试。",
                reason=exc.reason or "amap_error",
                category=category.value,
            ) from exc
        except (httpx.HTTPError, RuntimeError) as exc:
            logger.warning(
                "candidate collection failed: city=%s category=%s reason=map_service_unavailable",
                normalized_city,
                category.value,
            )
            raise CandidateCollectionUnavailableError(
                f"暂时无法获取“{normalized_city}”的{_CATEGORY_LABELS[category]}候选，请稍后重试。",
                reason="map_service_unavailable",
                category=category.value,
            ) from exc
        candidates[category] = _filter_candidates(
            places,
            city=normalized_city,
            category=category,
            adcode=adcode,
            administrative_level=administrative_level,
        )

    return CityCandidatePool(
        city=normalized_city,
        adcode=adcode,
        administrative_level=administrative_level,
        candidates=candidates,
        minimum_counts=resolved_minimums,
    )
