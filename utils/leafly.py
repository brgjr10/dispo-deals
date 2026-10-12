"""Leafly strain importer.

Leafly has no public self-serve strain API. The consumer site does expose two
usable surfaces, and both are used here:

1. ``consumer-api.leafly.com/api/search/v1`` - a JSON search endpoint the site
   itself calls, keyed by a query string. It resolves a name to Leafly's
   canonical strain record and carries phenotype, cannabinoid percentiles,
   effects, terpenes and rating. It is the authoritative resolver: it maps
   aliases ("GSC") and misspellings onto the right strain.
2. ``leafly.com/strains/<slug>`` - the strain page. Its Next.js payload carries
   the fields the search endpoint omits, most importantly flavours, the full
   description and the parent/child genetics. It is only fetched when the
   caller asks for full detail.

Percentiles need care: Leafly emits ``percentile25/50/75`` per cannabinoid but
the values are not guaranteed to be ordered (a 50 above the 75 has been
observed), so low/high are derived as the min/max of whatever is present.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import requests

from models import Strain

logger = logging.getLogger(__name__)

NEXT_DATA_RE = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

# Only these effects/flavours/terpenes are worth showing; Leafly returns the
# full vocabulary for every strain, most of it scoring at or below zero.
CANNABINOIDS_OF_INTEREST = ("thc", "cbd")
MAX_EFFECTS = 6
MAX_FLAVORS = 6
MAX_TERPENES = 6


class LeaflyClient:
    """Reads strain profiles from Leafly's public surfaces."""

    def __init__(
        self,
        search_endpoint: str = "https://consumer-api.leafly.com/api/search/v1",
        site_url: str = "https://www.leafly.com",
        timeout: int = 15,
        max_retries: int = 3,
        request_delay_seconds: float = 0.4,
        session: Optional[requests.Session] = None,
    ):
        self.search_endpoint = search_endpoint
        self.site_url = site_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.request_delay_seconds = max(0.0, request_delay_seconds)
        self.session = session or requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            # The search endpoint is the site's own API and rejects calls that
            # do not look like they came from the web app.
            "X-App": "web-web",
            "X-Country-Code": "US",
        })
        self._last_request_at = 0.0

    # ---- public API ----

    def search_strain(self, name: str) -> Optional[Strain]:
        """Resolve a name to a Leafly strain, or None when nothing matches."""
        hits = self._search_hits(name, take=1)
        if not hits:
            return None
        return self._strain_from_hit(hits[0])

    def get_strain(self, name: str, full: bool = False) -> Optional[Strain]:
        """Resolve a name to a strain, optionally enriching with detail-page data."""
        hits = self._search_hits(name, take=1)
        if not hits:
            return None

        strain = self._strain_from_hit(hits[0])
        if not strain:
            return None

        if full and strain.slug:
            detail = self._detail_strain(strain.slug)
            if detail:
                strain = self._merge_strain(strain, detail)
        return strain

    def get_strain_by_slug(self, slug: str) -> Optional[Strain]:
        """Fetch a strain's full profile straight from its Leafly page."""
        return self._detail_strain(slug)

    def search_hits(self, name: str, take: int = 10) -> List[Dict[str, Any]]:
        """Return raw strain search hits for a name, best first.

        Callers that need to score competing candidates should use this rather
        than ``search_strain``, which commits to the first hit.
        """
        return self._search_hits(name, take=take) or []

    def strain_from_hit(self, hit: Dict[str, Any]) -> Optional[Strain]:
        """Build a ``Strain`` from a raw search hit.

        Exposed so callers that score hits themselves (see ``strain_match``)
        can pick a specific hit and reuse this conversion.
        """
        return self._strain_from_hit(hit)

    @staticmethod
    def merge_strain(primary: Strain, detail: Strain) -> Strain:
        """Overlay detail-page data onto a search record, keeping what is known."""
        return LeaflyClient._merge_strain(primary, detail)

    # ---- search endpoint ----

    def _search_hits(self, name: str, take: int = 10) -> List[Dict[str, Any]]:
        query = (name or "").strip()
        if not query:
            return None

        params = {
            "q": query,
            # all_strains is required: without it the search defaults to menu
            # items near the caller's location, which returns dispensary
            # products instead of strain records.
            "filter[all_strains]": "true",
            "skip": 0,
            # Aggregations add a large irrelevant payload block.
            "skip_aggs": "true",
            "take": take,
        }

        payload = self._get_json(self.search_endpoint, params)
        if not payload:
            return []

        hits = (payload.get("hits") or {}).get("strain") or []
        return hits if isinstance(hits, list) else []

    def _strain_from_hit(self, hit: Dict[str, Any]) -> Optional[Strain]:
        name = (hit.get("name") or "").strip()
        if not name:
            return None

        cannabinoids = hit.get("cannabinoids") or {}
        return Strain(
            name=name,
            slug=hit.get("slug") or "",
            leafly_id=str(hit["id"]) if hit.get("id") is not None else None,
            category=hit.get("category") or hit.get("phenotype") or "",
            thc_pct=_midpoint(cannabinoids.get("thc")),
            thc_low=_low_percentile(cannabinoids.get("thc")),
            thc_high=_high_percentile(cannabinoids.get("thc")),
            cbd_pct=_midpoint(cannabinoids.get("cbd")),
            cbd_low=_low_percentile(cannabinoids.get("cbd")),
            cbd_high=_high_percentile(cannabinoids.get("cbd")),
            effects=_ranked_names(hit.get("effects"), MAX_EFFECTS),
            flavors=_ranked_names(hit.get("flavors"), MAX_FLAVORS),
            terpenes=_ranked_names(hit.get("terps"), MAX_TERPENES),
            rating=_as_float(hit.get("averageRating")),
            review_count=_as_int(hit.get("reviewCount")),
            description=_plain(hit.get("shortDescriptionPlain") or hit.get("description") or ""),
            image_url=hit.get("nugImage") or hit.get("flowerImageSvg") or "",
            source="leafly-search",
            fetched_at=None,
        )

    # ---- strain detail page ----

    def _detail_strain(self, slug: str) -> Optional[Strain]:
        html = self._get_text(f"{self.site_url}/strains/{slug}")
        if not html:
            return None

        match = NEXT_DATA_RE.search(html)
        if not match:
            logger.debug("Leafly page for %s has no __NEXT_DATA__", slug)
            return None

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.debug("Leafly page for %s has malformed __NEXT_DATA__: %s", slug, e)
            return None

        strain = (data.get("props", {}).get("pageProps", {}) or {}).get("strain")
        if not isinstance(strain, dict) or not strain.get("name"):
            return None

        cannabinoids = strain.get("cannabinoids") or {}
        return Strain(
            name=strain["name"].strip(),
            slug=strain.get("slug") or slug,
            leafly_id=str(strain["id"]) if strain.get("id") is not None else None,
            category=strain.get("category") or strain.get("phenotype") or "",
            thc_pct=_midpoint(cannabinoids.get("thc")),
            thc_low=_low_percentile(cannabinoids.get("thc")),
            thc_high=_high_percentile(cannabinoids.get("thc")),
            cbd_pct=_midpoint(cannabinoids.get("cbd")),
            cbd_low=_low_percentile(cannabinoids.get("cbd")),
            cbd_high=_high_percentile(cannabinoids.get("cbd")),
            effects=_ranked_names(strain.get("effects"), MAX_EFFECTS),
            flavors=_ranked_names(strain.get("flavors"), MAX_FLAVORS),
            terpenes=_ranked_names(strain.get("terps"), MAX_TERPENES),
            helps_with=_ranked_names(strain.get("conditions"), 8),
            rating=_as_float(strain.get("averageRating") or strain.get("rating")),
            review_count=_as_int(strain.get("reviewCount") or strain.get("effectReviewCount")),
            description=_plain(strain.get("descriptionPlain") or ""),
            image_url=strain.get("nugImage") or strain.get("flowerImageSvg") or "",
            parents=_related_names(strain.get("parents")),
            children=_related_names(strain.get("children")),
            source="leafly-detail",
            fetched_at=None,
        )

    @staticmethod
    def _merge_strain(primary: Strain, detail: Strain) -> Strain:
        """Overlay detail-page data onto the search record, keeping what is known.

        The two sources disagree on some strains (the search payload can have no
        cannabinoid percentiles at all). The detail page is the richer source, so
        it wins where it actually has a value.
        """
        for field_name in (
            "thc_pct", "thc_low", "thc_high", "cbd_pct", "cbd_low", "cbd_high",
        ):
            detail_value = getattr(detail, field_name)
            if detail_value is not None:
                setattr(primary, field_name, detail_value)

        # Flavours only exist on the detail page, so an empty detail list means
        # "not reported" rather than "this strain has no flavour".
        for field_name in ("effects", "flavors", "terpenes", "helps_with", "parents", "children"):
            detail_value = getattr(detail, field_name)
            if detail_value:
                setattr(primary, field_name, detail_value)

        if detail.description:
            primary.description = detail.description
        if detail.image_url:
            primary.image_url = detail.image_url
        if detail.rating is not None:
            primary.rating = detail.rating
        if detail.review_count is not None:
            primary.review_count = detail.review_count
        if detail.category:
            primary.category = detail.category
        if detail.leafly_id:
            primary.leafly_id = detail.leafly_id
        if detail.slug:
            primary.slug = detail.slug

        primary.source = "leafly-detail"
        return primary

    # ---- HTTP plumbing ----

    def _throttle(self):
        """Space requests out so the importer is not a hammer on Leafly."""
        if self.request_delay_seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.request_delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def _get_json(self, url: str, params: Dict[str, Any]) -> Optional[Any]:
        response = self._request("GET", url, params=params)
        if response is None:
            return None
        try:
            return response.json()
        except ValueError as e:
            logger.debug("Leafly returned non-JSON from %s: %s", url, e)
            return None

    def _get_text(self, url: str) -> Optional[str]:
        response = self._request("GET", url)
        if response is None:
            return None
        return response.text

    def _request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
                if response.status_code == 200:
                    return response
                # A 404 on a strain page means the slug is wrong, not that
                # Leafly is having a moment, so retrying only wastes time.
                if response.status_code == 404:
                    logger.debug("Leafly 404 for %s", url)
                    return None
                logger.debug(
                    "Leafly request to %s returned HTTP %s (attempt %s/%s)",
                    url, response.status_code, attempt + 1, self.max_retries,
                )
            except requests.RequestException as e:
                logger.debug(
                    "Leafly request to %s failed: %s (attempt %s/%s)",
                    url, e, attempt + 1, self.max_retries,
                )

            if attempt < self.max_retries - 1:
                time.sleep(min(2 ** attempt, 8))

        logger.warning("Leafly request failed after %s attempts: %s", self.max_retries, url)
        return None


# ---- value coercion helpers ----


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    result = _as_float(value)
    return int(result) if result is not None else None


def _percentile_values(entry: Any) -> List[float]:
    """Collect the numeric percentiles from a cannabinoid entry.

    Leafly sends ``percentile25``/``percentile50``/``percentile75`` where most
    values are null, so only the populated ones are collected.
    """
    if not isinstance(entry, dict):
        return []
    values: List[float] = []
    for key in ("percentile25", "percentile50", "percentile75"):
        number = _as_float(entry.get(key))
        if number is not None and number > 0:
            values.append(number)
    return values


def _midpoint(entry: Any) -> Optional[float]:
    """The representative potency: the median percentile when it exists."""
    if not isinstance(entry, dict):
        return None
    median = _as_float(entry.get("percentile50"))
    if median is not None and median > 0:
        return round(median, 1)
    values = _percentile_values(entry)
    return round(sum(values) / len(values), 1) if values else None


def _low_percentile(entry: Any) -> Optional[float]:
    values = _percentile_values(entry)
    return round(min(values), 1) if values else None


def _high_percentile(entry: Any) -> Optional[float]:
    values = _percentile_values(entry)
    return round(max(values), 1) if values else None


def _ranked_names(mapping: Any, limit: int) -> List[str]:
    """Return display names of a score-ranked map, strongest first.

    Effects, flavours and terpenes all arrive as ``{key: {name, score, votes}}``
    with a long tail of neutral or negative entries, so anything at or below
    zero is dropped instead of shown as a flat list.
    """
    if not isinstance(mapping, dict):
        return []

    scored: List[tuple] = []
    for entry in mapping.values():
        if not isinstance(entry, dict):
            continue
        name = _display_name(entry.get("name"))
        if not name:
            continue
        score = _as_float(entry.get("score")) or 0.0
        scored.append((score, name))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [name for score, name in scored[:limit] if score > 0]


def _display_name(value: Any) -> str:
    """Title-case the lowercase names Leafly's detail page returns.

    The search API returns "Relaxed" while the strain page returns "relaxed";
    normalising on the way in keeps stored records consistent.
    """
    name = value if isinstance(value, str) else ""
    name = name.strip()
    if not name:
        return ""
    if name == name.lower():
        return name.title()
    return name


def _related_names(entries: Any) -> List[str]:
    """Parent/child genetics are dictionaries under a ``name`` key."""
    if not isinstance(entries, list):
        return []
    names: List[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            name = (entry.get("name") or "").strip()
        elif isinstance(entry, str):
            name = entry.strip()
        else:
            name = ""
        if name and name not in names:
            names.append(name)
    return names


def _plain(value: Any) -> str:
    """Flatten Leafly's HTML-ish descriptions to plain text."""
    text = value if isinstance(value, str) else ""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&apos;", "'").replace("&#39;", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text
