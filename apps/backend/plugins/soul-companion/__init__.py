"""Soul companion plugin for Chinese life and travel assistance.

The plugin is intentionally self-contained: no Soul core files are changed,
and no new third-party dependencies are introduced. It uses:

* AMap Web Service for weather and POI search.
* 12306 public ticket endpoints for railway schedules and remaining seats.
"""

from __future__ import annotations

import json
import os
import re
import threading
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from datetime import date, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AMAP_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"
AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v5/place/text"
AMAP_PLACE_AROUND_URL = "https://restapi.amap.com/v5/place/around"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
BING_SEARCH_URL = "https://www.bing.com/search"
PARALLEL_SEARCH_URL = "https://api.parallel.ai/v1/search"

STATION_NAME_URL = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"
LEFT_TICKET_ENDPOINTS = (
    "https://kyfw.12306.cn/otn/leftTicket/queryG",
    "https://kyfw.12306.cn/otn/leftTicket/query",
    "https://kyfw.12306.cn/otn/leftTicket/queryA",
    "https://kyfw.12306.cn/otn/leftTicket/queryO",
)
TICKET_PRICE_URL = "https://kyfw.12306.cn/otn/leftTicket/queryTicketPrice"
YILIAN_HEALTH_BASE_URL = "https://www.agetech.cc/prod-api"

DEFAULT_SOULBOT_ROOT = "/Users/apapoo/Desktop/Github_Hub/Soulbot"
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_HTTP_ATTEMPTS = 5
WEB_SEARCH_IMAGE_PROBE_LIMIT = 4
WEB_SEARCH_IMAGE_LIMIT = 6
WEB_IMAGE_BYTES_LIMIT = 220_000
WEB_IMAGE_BAD_URL_RE = re.compile(
    r"(?:favicon|logo|icon|sprite|avatar|qrcode|qr-code|placeholder|blank|loading|default)[^/]*\.(?:svg|png|jpe?g|webp|gif|ico)",
    re.IGNORECASE,
)
WEB_IMAGE_URL_HINT_RE = re.compile(r"(?:\.(?:jpe?g|png|webp|avif)(?:[?#]|$)|(?:image|photo|pic|cover|thumb|img))", re.IGNORECASE)

CATEGORY_CONFIG = {
    "food": {
        "label": "美食",
        "types": "050000",
        "default_query": "本地特色美食 餐厅 小吃",
    },
    "hotel": {
        "label": "住宿",
        "types": "100000",
        "default_query": "酒店 住宿 民宿",
    },
    "scenic": {
        "label": "景点",
        "types": "110000",
        "default_query": "景点 风景名胜 公园 博物馆",
    },
}

COMMON_STATIONS = {
    "北京": "BJP",
    "北京南": "VNP",
    "北京西": "BXP",
    "上海": "SHH",
    "上海虹桥": "AOH",
    "广州": "GZQ",
    "广州南": "IZQ",
    "深圳": "SZQ",
    "深圳北": "IOQ",
    "福州": "FZS",
    "福州南": "FYS",
    "厦门": "XMS",
    "厦门北": "XKS",
    "泉州": "QYS",
    "莆田": "PTS",
    "平潭": "PIS",
    "武夷山北": "WBS",
    "杭州": "HZH",
    "杭州东": "HGH",
    "南京": "NJH",
    "南京南": "NKH",
    "武汉": "WHN",
    "长沙南": "CWQ",
    "成都东": "ICW",
    "重庆北": "CUW",
    "西安北": "EAY",
    "郑州东": "ZAF",
    "南昌西": "NXG",
    "合肥南": "ENH",
}

PRICE_SEAT_LABELS = {
    "A9": "商务座",
    "P": "特等座",
    "M": "一等座",
    "O": "二等座",
    "A6": "高级软卧",
    "A4": "软卧",
    "A3": "硬卧",
    "A2": "软座",
    "A1": "硬座",
    "WZ": "无座",
}

_station_cache_lock = threading.Lock()
_station_cache: Optional[Tuple[Dict[str, str], Dict[str, str]]] = None


def _json_result(data: Mapping[str, Any]) -> str:
    return json.dumps(dict(data), ensure_ascii=False)


def _tool_error(message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"success": False, "error": message}
    payload.update(extra)
    return _json_result(payload)


def _tool_ok(text: str, **data: Any) -> str:
    payload: Dict[str, Any] = {"success": True, "text": text}
    payload.update(data)
    return _json_result(payload)


def _timeout() -> float:
    try:
        return float(os.environ.get("SOUL_HTTP_TIMEOUT") or DEFAULT_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        return float(DEFAULT_TIMEOUT_SECONDS)


def _http_attempts() -> int:
    try:
        return max(1, min(int(os.environ.get("SOUL_HTTP_ATTEMPTS") or DEFAULT_HTTP_ATTEMPTS), 5))
    except (TypeError, ValueError):
        return DEFAULT_HTTP_ATTEMPTS


def _http_headers() -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
    }


def _http_get_text(
    url: str,
    params: Mapping[str, Any],
    *,
    extra_headers: Optional[Mapping[str, str]] = None,
    opener: Any = None,
    timeout: Optional[float] = None,
    attempts: Optional[int] = None,
) -> str:
    clean_params = {
        str(k): str(v)
        for k, v in params.items()
        if v not in (None, "")
    }
    query = urlencode(clean_params)
    full_url = f"{url}?{query}" if query else url
    headers = {**_http_headers(), **dict(extra_headers or {})}
    request = Request(full_url, headers=headers)
    open_fn = opener.open if opener is not None else urlopen
    last_error: Optional[BaseException] = None
    timeout_value = _timeout() if timeout is None else float(timeout)
    attempts_value = _http_attempts() if attempts is None else max(1, int(attempts))
    for _ in range(attempts_value):
        try:
            with open_fn(request, timeout=timeout_value) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("HTTP request failed")


def _http_post_json(
    url: str,
    payload: Mapping[str, Any],
    *,
    extra_headers: Optional[Mapping[str, str]] = None,
    timeout: Optional[float] = None,
    attempts: Optional[int] = None,
) -> Dict[str, Any]:
    headers = {
        **_http_headers(),
        "Content-Type": "application/json",
        "Accept": "application/json,text/plain,*/*",
        **dict(extra_headers or {}),
    }
    body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    last_error: Optional[BaseException] = None
    timeout_value = _timeout() if timeout is None else float(timeout)
    attempts_value = _http_attempts() if attempts is None else max(1, int(attempts))
    for _ in range(attempts_value):
        try:
            with urlopen(request, timeout=timeout_value) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                text = response.read().decode(charset, errors="replace").lstrip("\ufeff")
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise RuntimeError("provider returned non-object JSON")
                return data
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("HTTP request failed")


def _get_json(
    url: str,
    params: Mapping[str, Any],
    *,
    extra_headers: Optional[Mapping[str, str]] = None,
    opener: Any = None,
) -> Dict[str, Any]:
    text = _http_get_text(url, params, extra_headers=extra_headers, opener=opener)
    text = text.lstrip("\ufeff")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise RuntimeError("provider returned non-object JSON")
    return data


def _get_amap_key() -> str:
    key = (
        os.environ.get("SOUL_AMAP_API_KEY")
        or os.environ.get("AMAP_API_KEY")
        or os.environ.get("GAODE_API_KEY")
        or ""
    ).strip()
    if key:
        return key

    root = Path(os.environ.get("SOULBOT_ROOT") or DEFAULT_SOULBOT_ROOT)
    config_files = (
        root / "plugins" / "soul-companion" / "plugin.yaml",
        root / "apps" / "backend" / "audiences" / "Aini" / "persona.yaml",
    )
    for config_file in config_files:
        try:
            text = config_file.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"amap_api_key:\s*[\"']?([^\"'\s#]+)", text)
        if match:
            return match.group(1).strip()
    return ""


def _amap_json(url: str, params: Mapping[str, Any]) -> Dict[str, Any]:
    api_key = _get_amap_key()
    if not api_key:
        raise RuntimeError("AMAP_API_KEY is not configured")
    merged = {"key": api_key, "output": "JSON", **dict(params)}
    data = _get_json(url, merged)
    if str(data.get("status", "1")) != "1":
        info = data.get("info") or data.get("infocode") or "unknown amap error"
        raise RuntimeError(f"AMap request failed: {info}")
    return data


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            value = next((item for item in value if item), "")
        if isinstance(value, dict):
            continue
        text = str(value).strip()
        if text and text != "[]":
            return text
    return ""


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _web_api_key() -> str:
    key = (
        os.environ.get("SOUL_WEB_API_KEY")
        or os.environ.get("JINA_API_KEY")
        or os.environ.get("WEB_SEARCH_API_KEY")
        or ""
    ).strip()
    if key:
        return key

    root = Path(os.environ.get("SOULBOT_ROOT") or DEFAULT_SOULBOT_ROOT)
    for env_file in (root / ".env", root / "deploy" / ".env"):
        try:
            text = env_file.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"(?m)^\s*SOUL_WEB_API_KEY\s*=\s*([^\n#]+)", text)
        if match:
            return match.group(1).strip().strip("\"'")
    return ""


def _parallel_api_key() -> str:
    key = (
        os.environ.get("PARALLEL_API_KEY")
        or os.environ.get("SOUL_PARALLEL_API_KEY")
        or os.environ.get("SOUL_WEB_API_KEY")
        or ""
    ).strip()
    if key:
        return key

    root = Path(os.environ.get("SOULBOT_ROOT") or DEFAULT_SOULBOT_ROOT)
    for env_file in (root / ".env", root / "deploy" / ".env"):
        try:
            text = env_file.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(
            r"(?m)^\s*(?:PARALLEL_API_KEY|SOUL_PARALLEL_API_KEY|SOUL_WEB_API_KEY)\s*=\s*([^\n#]+)",
            text,
        )
        if match:
            return match.group(1).strip().strip("\"'")
    return ""


def _web_headers(
    *,
    accept: str = "text/html,application/xhtml+xml,text/plain,*/*",
    include_auth: bool = False,
) -> Dict[str, str]:
    headers = {**_http_headers(), "Accept": accept}
    key = _web_api_key() if include_auth else ""
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _web_search_timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("SOUL_WEB_SEARCH_TIMEOUT") or 6.0))
    except (TypeError, ValueError):
        return 6.0


def _web_search_attempts() -> int:
    try:
        return max(1, min(int(os.environ.get("SOUL_WEB_SEARCH_ATTEMPTS") or 1), 3))
    except (TypeError, ValueError):
        return 1


def _web_image_timeout() -> float:
    try:
        return max(0.5, min(float(os.environ.get("SOUL_WEB_IMAGE_TIMEOUT") or 2.5), 5.0))
    except (TypeError, ValueError):
        return 2.5


def _web_search_sources() -> Tuple[str, ...]:
    raw = os.environ.get("SOUL_WEB_SEARCH_SOURCES", "parallel,bing,jina")
    sources = []
    for item in str(raw).split(","):
        source = item.strip().lower()
        if source in {"parallel", "jina", "bing", "duckduckgo"} and source not in sources:
            sources.append(source)
    return tuple(sources or ["parallel", "bing", "jina"])


def _parallel_search_mode() -> str:
    mode = str(os.environ.get("SOUL_PARALLEL_SEARCH_MODE") or "basic").strip().lower()
    return mode if mode in {"basic", "advanced"} else "basic"


def _parallel_max_chars_total() -> int:
    try:
        return max(1000, min(int(os.environ.get("SOUL_PARALLEL_MAX_CHARS_TOTAL") or 12000), 50000))
    except (TypeError, ValueError):
        return 12000


def _parallel_search_queries(query: str, raw_queries: Any = None) -> List[str]:
    raw_items: List[Any] = []
    if isinstance(raw_queries, str):
        raw_items = [raw_queries]
    elif isinstance(raw_queries, list):
        raw_items = raw_queries

    queries: List[str] = []
    seen: set[str] = set()
    for item in raw_items:
        compact = re.sub(r"\s+", " ", str(item or "")).strip()
        if not compact:
            continue
        compact = compact[:200].rstrip()
        key = compact.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(compact)
        if len(queries) >= 5:
            break

    if queries:
        return queries

    compact = re.sub(r"\s+", " ", str(query or "")).strip()
    if not compact:
        return []
    return [compact[:200].rstrip()]


def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg|canvas|iframe).*?</\1>", " ", str(value or ""))
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|section|article|blockquote)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _compact_text(value: str, *, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else f"{text[:limit].rstrip()}..."


def _normalize_result_url(raw_url: str, base_url: str = "") -> str:
    url = unescape(str(raw_url or "")).strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = f"https:{url}"
    if base_url and not urlparse(url).scheme:
        url = urljoin(base_url, url)
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


def _normalize_image_url(raw_url: str, base_url: str = "") -> str:
    url = _normalize_result_url(raw_url, base_url)
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if WEB_IMAGE_BAD_URL_RE.search(url):
        return ""
    if not WEB_IMAGE_URL_HINT_RE.search(url):
        return ""
    return url


def _first_image_value(item: Mapping[str, Any]) -> str:
    for key in ("image", "imageUrl", "image_url", "thumbnail", "thumbnailUrl", "thumbnail_url", "og_image"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    images = item.get("images")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, str) and image.strip():
                return image
            if isinstance(image, Mapping):
                value = _first_text(image.get("url"), image.get("src"), image.get("image"))
                if value:
                    return value
    return ""


def _dedupe_web_results(results: Iterable[Mapping[str, Any]], limit: int) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    normalized: List[Dict[str, Any]] = []
    for item in results:
        url = str(item.get("url") or "").strip()
        title = _compact_text(str(item.get("title") or ""), limit=120)
        description = _compact_text(str(item.get("description") or item.get("content") or ""), limit=320)
        if not url or not title:
            continue
        key = url.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        result = {
            "title": title,
            "url": url,
            "description": description,
            "position": len(normalized) + 1,
        }
        image = _normalize_image_url(_first_image_value(item), url)
        if image:
            result["image"] = image
            result["imageAlt"] = title
        normalized.append(result)
        if len(normalized) >= limit:
            break
    return normalized


def _parse_jina_search_payload(raw: str, limit: int) -> List[Dict[str, Any]]:
    raw = raw.lstrip("\ufeff").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, Mapping):
        data = payload.get("data")
        if isinstance(data, Mapping):
            data = data.get("results") or data.get("web") or data.get("items")
        if isinstance(data, list):
            return _dedupe_web_results(
                (
                    {
                        "title": item.get("title") or item.get("name"),
                        "url": item.get("url") or item.get("link"),
                        "description": item.get("description") or item.get("content") or item.get("snippet"),
                    }
                    for item in data
                    if isinstance(item, Mapping)
                ),
                limit,
            )

    blocks = re.split(r"\n(?=Title:\s*)", raw)
    parsed: List[Dict[str, Any]] = []
    for block in blocks:
        title_match = re.search(r"(?im)^Title:\s*(.+)$", block)
        url_match = re.search(r"(?im)^(?:URL Source|URL|Source):\s*(https?://\S+)", block)
        if not title_match or not url_match:
            continue
        content = re.sub(r"(?im)^(Title|URL Source|URL|Source):\s*.+$", "", block)
        parsed.append(
            {
                "title": title_match.group(1).strip(),
                "url": url_match.group(1).strip(),
                "description": _compact_text(_strip_html(content), limit=320),
            }
        )
    return _dedupe_web_results(parsed, limit)


def _search_via_jina(query: str, limit: int) -> List[Dict[str, Any]]:
    # Jina Search accepts the query in the path. The Authorization header is
    # optional for free/public use, and SOUL_WEB_API_KEY is passed when present.
    encoded = quote(query, safe="")
    last_error: Optional[BaseException] = None
    auth_modes = (True, False) if _web_api_key() else (False,)
    for include_auth in auth_modes:
        try:
            raw = _http_get_text(
                f"https://s.jina.ai/{encoded}",
                {},
                extra_headers=_web_headers(accept="application/json,text/plain,*/*", include_auth=include_auth),
                timeout=_web_search_timeout(),
                attempts=_web_search_attempts(),
            )
            return _parse_jina_search_payload(raw, limit)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return []


def _parse_parallel_search_payload(payload: Mapping[str, Any], limit: int) -> List[Dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    parsed: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        excerpts = item.get("excerpts")
        if isinstance(excerpts, list):
            description = "\n".join(str(excerpt) for excerpt in excerpts if excerpt)
        else:
            description = str(excerpts or item.get("description") or item.get("snippet") or "")
        parsed.append(
            {
                "title": item.get("title") or item.get("url") or "",
                "url": item.get("url") or "",
                "description": description,
            }
        )
    return _dedupe_web_results(parsed, limit)


def _search_via_parallel(
    query: str,
    limit: int,
    *,
    objective: str = "",
    search_queries: Any = None,
) -> List[Dict[str, Any]]:
    api_key = _parallel_api_key()
    if not api_key:
        raise RuntimeError("PARALLEL_API_KEY is not configured")
    objective_text = re.sub(r"\s+", " ", str(objective or query or "")).strip()
    payload = {
        "objective": objective_text,
        "search_queries": _parallel_search_queries(query or objective_text, search_queries),
        "mode": _parallel_search_mode(),
        "max_chars_total": _parallel_max_chars_total(),
    }
    data = _http_post_json(
        PARALLEL_SEARCH_URL,
        payload,
        extra_headers={"x-api-key": api_key},
        timeout=_web_search_timeout(),
        attempts=_web_search_attempts(),
    )
    return _parse_parallel_search_payload(data, limit)


def _parse_duckduckgo_html(html: str, limit: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    pattern = re.compile(
        r'(?is)<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    )
    matches = list(pattern.finditer(html))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(html), start + 2500)
        chunk = html[start:end]
        snippet_match = re.search(r'(?is)<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', chunk)
        if snippet_match is None:
            snippet_match = re.search(r'(?is)<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>', chunk)
        results.append(
            {
                "title": _strip_html(match.group("title")),
                "url": _normalize_result_url(match.group("href"), "https://duckduckgo.com"),
                "description": _strip_html(snippet_match.group(1)) if snippet_match else "",
            }
        )
    return _dedupe_web_results(results, limit)


def _parse_bing_html(html: str, limit: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for block_match in re.finditer(r'(?is)<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', html):
        block = block_match.group(1)
        link_match = re.search(r'(?is)<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>', block)
        if not link_match:
            continue
        snippet_match = re.search(r'(?is)<p[^>]*>(.*?)</p>', block)
        results.append(
            {
                "title": _strip_html(link_match.group(2)),
                "url": _normalize_result_url(link_match.group(1), "https://www.bing.com"),
                "description": _strip_html(snippet_match.group(1)) if snippet_match else "",
            }
        )
    return _dedupe_web_results(results, limit)


def _parse_bing_rss(raw: str, limit: int) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(raw.lstrip("\ufeff"))
    except ET.ParseError:
        return _parse_bing_html(raw, limit)
    return _dedupe_web_results(
        (
            {
                "title": item.findtext("title") or "",
                "url": item.findtext("link") or "",
                "description": _strip_html(item.findtext("description") or ""),
            }
            for item in root.findall(".//item")
        ),
        limit,
    )


def _search_via_duckduckgo(query: str, limit: int) -> List[Dict[str, Any]]:
    html = _http_get_text(
        DUCKDUCKGO_HTML_URL,
        {"q": query},
        extra_headers=_web_headers(),
        timeout=_web_search_timeout(),
        attempts=_web_search_attempts(),
    )
    return _parse_duckduckgo_html(html, limit)


def _search_via_bing(query: str, limit: int) -> List[Dict[str, Any]]:
    raw = _http_get_text(
        BING_SEARCH_URL,
        {"q": query, "format": "rss", "setlang": "zh-CN", "mkt": "zh-CN"},
        extra_headers=_web_headers(),
        timeout=_web_search_timeout(),
        attempts=_web_search_attempts(),
    )
    return _parse_bing_rss(raw, limit)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas", "iframe"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "section", "article"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas", "iframe"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "section", "article"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title = (self.title + " " + text).strip()
        self._parts.append(text)
        self._parts.append(" ")

    def visible_text(self) -> str:
        text = "\n".join(line.strip() for line in "".join(self._parts).splitlines())
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines: List[str] = []
        seen_recent: set[str] = set()
        for line in (item.strip() for item in text.splitlines()):
            if not line or len(line) <= 1:
                continue
            key = line[:120]
            if key in seen_recent:
                continue
            seen_recent.add(key)
            if len(seen_recent) > 300:
                seen_recent.clear()
            lines.append(line)
        return "\n".join(lines).strip()


class _PageImageMetaParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.images: List[str] = []
        self.title = ""
        self._in_title = False

    def _add_image(self, raw_url: str) -> None:
        image = _normalize_image_url(raw_url, self.base_url)
        if image and image not in self.images:
            self.images.append(image)

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map = {str(name).lower(): value or "" for name, value in attrs}
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").strip().lower()
            if key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
                self._add_image(attr_map.get("content", ""))
            return
        if tag == "link":
            rel = attr_map.get("rel", "").lower()
            if "image_src" in rel:
                self._add_image(attr_map.get("href", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if not self._in_title:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.title = (self.title + " " + text).strip()


def _is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host or host in {"localhost"} or host.endswith(".local"):
        return False
    try:
        ip = ip_address(host)
    except ValueError:
        return True
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


def _extract_direct(url: str, max_chars: int) -> Dict[str, Any]:
    request = Request(url, headers=_web_headers())
    with urlopen(request, timeout=_timeout()) as response:
        content_type = response.headers.get("content-type", "")
        charset = response.headers.get_content_charset() or "utf-8"
        raw = response.read(max(max_chars * 6, 50000)).decode(charset, errors="replace")
    parser = _VisibleTextParser()
    parser.feed(raw)
    content = parser.visible_text() or _strip_html(raw)
    return {
        "url": url,
        "title": _compact_text(parser.title, limit=160),
        "content": content[:max_chars].rstrip(),
        "content_type": content_type,
    }


def _extract_page_preview_image(url: str) -> str:
    normalized_url = _normalize_result_url(url)
    if not _is_public_http_url(normalized_url):
        return ""
    request = Request(normalized_url, headers=_web_headers())
    with urlopen(request, timeout=_web_image_timeout()) as response:
        content_type = response.headers.get("content-type", "")
        if content_type and not re.search(r"(?:text/html|application/xhtml\+xml|text/plain)", content_type, re.IGNORECASE):
            return ""
        charset = response.headers.get_content_charset() or "utf-8"
        raw = response.read(WEB_IMAGE_BYTES_LIMIT).decode(charset, errors="replace")
    parser = _PageImageMetaParser(normalized_url)
    parser.feed(raw)
    return parser.images[0] if parser.images else ""


def _enrich_web_results_with_images(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not results:
        return results
    enriched = [dict(item) for item in results]
    image_count = sum(1 for item in enriched if item.get("image"))
    for item in enriched[:WEB_SEARCH_IMAGE_PROBE_LIMIT]:
        if image_count >= WEB_SEARCH_IMAGE_LIMIT:
            break
        if item.get("image"):
            continue
        try:
            image = _extract_page_preview_image(str(item.get("url") or ""))
        except Exception:
            continue
        if not image:
            continue
        item["image"] = image
        item["imageAlt"] = item.get("title") or "网页配图"
        image_count += 1
    return enriched


def _extract_via_jina(url: str, max_chars: int) -> Dict[str, Any]:
    # Reader-compatible fallback. Some deployments accept the target URL as the
    # path directly; failures simply fall back to the direct extractor error.
    hostless = re.sub(r"^https?://", "", url).lstrip("/")
    reader_urls = (
        f"https://r.jina.ai/http://r.jina.ai/http://{url}",
        f"https://r.jina.ai/http://{url}",
        f"https://r.jina.ai/http://{hostless}",
    )
    last_error: Optional[BaseException] = None
    raw = ""
    for reader_url in reader_urls:
        for include_auth in (True, False):
            try:
                raw = _http_get_text(
                    reader_url,
                    {},
                    extra_headers=_web_headers(accept="application/json,text/plain,*/*", include_auth=include_auth),
                )
                if raw.strip():
                    break
            except Exception as exc:
                last_error = exc
        if raw.strip():
            break
    if not raw and last_error is not None:
        raise last_error
    raw = raw.lstrip("\ufeff").strip()
    title = ""
    content = raw
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, Mapping):
        data = payload.get("data") if isinstance(payload.get("data"), Mapping) else payload
        title = str(data.get("title") or "")
        content = str(data.get("content") or data.get("text") or data.get("markdown") or raw)
    return {
        "url": url,
        "title": _compact_text(title, limit=160),
        "content": _strip_html(content)[:max_chars].rstrip(),
        "content_type": "reader",
    }


def _web_search_text(results: List[Dict[str, Any]], source: str) -> str:
    if not results:
        return "没有搜索到可用结果。"
    lines = [f"搜索结果（来源：{source}）："]
    for item in results:
        line = f"{item['position']}. {item['title']} — {item['url']}"
        if item.get("description"):
            line += f"\n   {item['description']}"
        lines.append(line)
    return "\n".join(lines)


def web_search(args: Mapping[str, Any], **_: Any) -> str:
    query = _first_text(args.get("query"), args.get("q"))
    objective = _first_text(args.get("objective"), query)
    parallel_queries = _parallel_search_queries(query or objective, args.get("search_queries"))
    display_query = query or (parallel_queries[0] if parallel_queries else objective)
    if not display_query and not objective and not parallel_queries:
        return _tool_error("query or objective is required")
    try:
        limit = max(1, min(int(args.get("limit") or 12), 12))
    except (TypeError, ValueError):
        limit = 12

    search_fns = {
        "parallel": _search_via_parallel,
        "jina": _search_via_jina,
        "bing": _search_via_bing,
        "duckduckgo": _search_via_duckduckgo,
    }
    attempts = tuple((source, search_fns[source]) for source in _web_search_sources())
    errors: List[str] = []
    for source, search_fn in attempts:
        try:
            if source == "parallel":
                results = search_fn(
                    display_query,
                    limit,
                    objective=objective or display_query,
                    search_queries=parallel_queries,
                )
            else:
                results = search_fn(display_query, limit)
            if results:
                results = _enrich_web_results_with_images(results)
                return _tool_ok(
                    _web_search_text(results, source),
                    web_search={
                        "query": display_query,
                        "objective": objective or display_query,
                        "search_queries": parallel_queries,
                        "results": results,
                        "source": source,
                    },
                    source=source,
                )
            errors.append(f"{source}: no results")
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    return _tool_error("联网搜索失败：" + "；".join(errors[-3:]))


def web_extract(args: Mapping[str, Any], **_: Any) -> str:
    raw_urls = args.get("urls") or args.get("url") or []
    if isinstance(raw_urls, str):
        urls = [raw_urls]
    elif isinstance(raw_urls, list):
        urls = [str(item) for item in raw_urls if item]
    else:
        urls = []
    urls = urls[:5]
    if not urls:
        return _tool_error("urls is required")
    try:
        max_chars = max(1000, min(int(args.get("max_chars") or 8000), 20000))
    except (TypeError, ValueError):
        max_chars = 8000

    results: List[Dict[str, Any]] = []
    for raw_url in urls:
        url = _normalize_result_url(raw_url)
        if not _is_public_http_url(url):
            results.append({"url": raw_url, "title": "", "content": "", "error": "Blocked non-public or invalid URL"})
            continue
        try:
            results.append(_extract_direct(url, max_chars))
            continue
        except Exception as direct_exc:
            try:
                results.append(_extract_via_jina(url, max_chars))
            except Exception as reader_exc:
                results.append(
                    {
                        "url": url,
                        "title": "",
                        "content": "",
                        "error": f"direct: {direct_exc}; reader: {reader_exc}",
                    }
                )

    ok_results = [item for item in results if item.get("content")]
    if not ok_results:
        return _tool_error("网页内容提取失败", web_extract={"results": results})

    lines = ["网页内容提取结果："]
    for index, item in enumerate(results, 1):
        if item.get("error"):
            lines.append(f"{index}. {item.get('url', '')}\n   提取失败：{item['error']}")
            continue
        title = item.get("title") or item.get("url") or f"网页 {index}"
        content = str(item.get("content") or "")
        lines.append(f"{index}. {title}\n来源：{item.get('url', '')}\n{content[:1200]}")
    return _tool_ok(
        "\n\n".join(lines),
        web_extract={"results": results},
        source="web_extract",
    )


def _resolve_date(value: Any = None) -> str:
    raw = str(value or "").strip()
    today = date.today()
    if not raw or raw in {"今天", "今日"}:
        return today.isoformat()
    if raw in {"明天", "明日"}:
        return (today + timedelta(days=1)).isoformat()
    if raw == "后天":
        return (today + timedelta(days=2)).isoformat()
    if raw in {"大后天"}:
        return (today + timedelta(days=3)).isoformat()
    if raw in {"周末", "本周末"}:
        days_until_sat = (5 - today.weekday()) % 7
        if days_until_sat == 0 and datetime.now().hour >= 18:
            days_until_sat = 7
        return (today + timedelta(days=days_until_sat)).isoformat()

    normalized = raw.replace("/", "-").replace(".", "-")
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", normalized)
    if match:
        y, m, d = (int(part) for part in match.groups())
        return date(y, m, d).isoformat()
    match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", normalized)
    if match:
        m, d = (int(part) for part in match.groups())
        candidate = date(today.year, m, d)
        if candidate < today:
            candidate = date(today.year + 1, m, d)
        return candidate.isoformat()
    return raw


def _place_text_location(query: str, city: str = "") -> Optional[Dict[str, Any]]:
    text_data = _amap_json(
        AMAP_PLACE_TEXT_URL,
        {
            "keywords": query,
            "city": city,
            "city_limit": "true" if city else "",
            "show_fields": "business",
        },
    )
    pois = text_data.get("pois")
    if not isinstance(pois, list):
        return None

    for poi in pois:
        if not isinstance(poi, dict):
            continue
        name = _first_text(poi.get("name"))
        location = _first_text(poi.get("location"))
        if not name or not location:
            continue
        if name != query and query not in name:
            continue
        poi_type = _first_text(poi.get("type"))
        if "公交车站" in poi_type:
            continue
        return {
            "name": name,
            "province": _first_text(poi.get("pname")),
            "city": _first_text(poi.get("cityname"), city),
            "district": _first_text(poi.get("adname")),
            "adcode": _first_text(poi.get("adcode")),
            "location": location,
            "level": poi_type,
            "source": "amap_place_text",
        }
    return None


def _geocode(place: str, city: str = "") -> Dict[str, Any]:
    query = str(place or "").strip()
    if not query:
        raise ValueError("地点不能为空")
    params: Dict[str, Any] = {"address": query}
    if city:
        params["city"] = city
    data = _amap_json(AMAP_GEOCODE_URL, params)
    geocodes = data.get("geocodes")
    if isinstance(geocodes, list) and geocodes:
        first = geocodes[0]
        if isinstance(first, dict):
            level = _first_text(first.get("level"))
            if not city and level in {"道路", "门址"}:
                resolved = _place_text_location(query)
                if resolved:
                    return resolved
            return {
                "name": _first_text(first.get("formatted_address"), query),
                "province": _first_text(first.get("province")),
                "city": _first_text(first.get("city"), city),
                "district": _first_text(first.get("district")),
                "adcode": _first_text(first.get("adcode")),
                "location": _first_text(first.get("location")),
                "level": level,
                "source": "amap_geocode",
            }

    resolved = _place_text_location(query, city=city)
    if resolved:
        return resolved
    raise RuntimeError(f"高德没有找到「{query}」的位置")


def _location_label(location: Mapping[str, Any], fallback: str) -> str:
    parts = [
        _first_text(location.get("province")),
        _first_text(location.get("city")),
        _first_text(location.get("district")),
    ]
    label = "".join(part for part in parts if part and part != "[]")
    return label or _first_text(location.get("name"), fallback)


def _weather_payload(city: str, date_ref: str = "", days: int = 4) -> Dict[str, Any]:
    resolved = _geocode(city)
    adcode = _first_text(resolved.get("adcode"))
    if not adcode:
        raise RuntimeError(f"没有找到「{city}」对应的行政区划编码")
    want_forecast = bool(date_ref and _resolve_date(date_ref) != date.today().isoformat()) or days > 1
    mode = "all" if want_forecast else "base"
    data = _amap_json(AMAP_WEATHER_URL, {"city": adcode, "extensions": mode})
    label = _location_label(resolved, city)
    result: Dict[str, Any] = {
        "provider": "amap",
        "requested_location": city,
        "resolved_location": resolved,
        "label": label,
        "mode": "forecast" if mode == "all" else "live",
    }
    if mode == "base":
        lives = data.get("lives") if isinstance(data, dict) else None
        live = lives[0] if isinstance(lives, list) and lives else {}
        result["live"] = live if isinstance(live, dict) else {}
        return result

    forecasts = data.get("forecasts") if isinstance(data, dict) else None
    forecast = forecasts[0] if isinstance(forecasts, list) and forecasts else {}
    casts = forecast.get("casts") if isinstance(forecast, dict) else []
    parsed: List[Dict[str, Any]] = []
    for item in casts if isinstance(casts, list) else []:
        if not isinstance(item, dict):
            continue
        parsed.append(
            {
                "date": _first_text(item.get("date")),
                "week": _first_text(item.get("week")),
                "dayweather": _first_text(item.get("dayweather")),
                "nightweather": _first_text(item.get("nightweather")),
                "daytemp": _first_text(item.get("daytemp")),
                "nighttemp": _first_text(item.get("nighttemp")),
                "daywind": _first_text(item.get("daywind")),
                "daypower": _first_text(item.get("daypower")),
            }
        )
    target = _resolve_date(date_ref) if date_ref else ""
    if target:
        selected = [item for item in parsed if item.get("date") == target]
    else:
        selected = parsed[: max(1, min(int(days or 4), 4))]
    result.update(
        {
            "forecast": selected or parsed[: max(1, min(int(days or 4), 4))],
            "available_forecast": parsed,
            "forecast_meta": {
                "city": forecast.get("city") if isinstance(forecast, dict) else "",
                "adcode": forecast.get("adcode") if isinstance(forecast, dict) else "",
                "reporttime": forecast.get("reporttime") if isinstance(forecast, dict) else "",
            },
        }
    )
    return result


def _weather_text(payload: Mapping[str, Any]) -> str:
    label = str(payload.get("label") or payload.get("requested_location") or "")
    if payload.get("mode") == "live":
        live = payload.get("live") if isinstance(payload.get("live"), dict) else {}
        weather = _first_text(live.get("weather"), "暂无天气")
        temp = _first_text(live.get("temperature"))
        humidity = _first_text(live.get("humidity"))
        wind = "".join(
            part for part in (_first_text(live.get("winddirection")), _first_text(live.get("windpower"))) if part
        )
        report = _first_text(live.get("reporttime"))
        bits = [f"{label}现在{weather}"]
        if temp:
            bits.append(f"{temp}℃")
        if humidity:
            bits.append(f"湿度{humidity}%")
        if wind:
            bits.append(f"{wind}风")
        text = "，".join(bits) + "。"
        if report:
            text += f" 数据更新时间：{report}。"
        text += " 出门前建议再看一眼实时变化，老人出行请带好水和常用药。"
        return text
    rows = payload.get("forecast") if isinstance(payload.get("forecast"), list) else []
    if not rows:
        return f"暂时没有查到{label}的天气预报。"
    lines = [f"{label}天气预报如下："]
    for item in rows:
        if not isinstance(item, dict):
            continue
        day = _first_text(item.get("date"))
        weather = _first_text(item.get("dayweather"))
        night = _first_text(item.get("nightweather"))
        low = _first_text(item.get("nighttemp"))
        high = _first_text(item.get("daytemp"))
        wind = _first_text(item.get("daywind"))
        power = _first_text(item.get("daypower"))
        line = f"- {day}：白天{weather or '暂无'}，夜间{night or '暂无'}"
        if low or high:
            line += f"，{low}~{high}℃"
        if wind or power:
            line += f"，{wind}{power}风"
        lines.append(line)
    lines.append("建议按最冷时段多带一件薄外套；如有雨，优先安排室内或少步行行程。")
    lines.append("来源：高德地图天气 API。")
    return "\n".join(lines)


def weather(args: Mapping[str, Any], **_: Any) -> str:
    city = _first_text(args.get("city"), args.get("location"))
    if not city:
        return _tool_error("请提供要查询的城市、区县或地标。")
    try:
        payload = _weather_payload(
            city,
            date_ref=_first_text(args.get("date"), args.get("date_ref")),
            days=int(args.get("days") or 4),
        )
        return _tool_ok(_weather_text(payload), weather=payload, source="amap")
    except Exception as exc:
        return _tool_error(f"天气查询失败：{exc}", source="amap")


HEALTH_METRIC_CONFIG = {
    "heart_rate": {
        "label": "心率",
        "unit": "bpm",
        "endpoint": "/companion/caregiver/list/humanId/hr",
        "value_keys": ("value",),
        "summary_label": "心率",
    },
    "blood_pressure": {
        "label": "血压",
        "unit": "mmHg",
        "endpoint": "/companion/caregiver/list/humanId/bp",
        "value_keys": ("systolic", "diastolic"),
        "summary_label": "血压",
    },
    "blood_oxygen": {
        "label": "血氧",
        "unit": "%",
        "endpoint": "/companion/caregiver/list/humanId/bloodOxygen",
        "value_keys": ("value",),
        "summary_label": "血氧",
    },
    "temperature": {
        "label": "体温",
        "unit": "℃",
        "endpoint": "/companion/caregiver/list/humanId/temp",
        "value_keys": ("value",),
        "summary_label": "体温",
    },
}


def _yilian_base_url() -> str:
    return (os.environ.get("YILIAN_HEALTH_BASE_URL") or _env_file_value("YILIAN_HEALTH_BASE_URL") or YILIAN_HEALTH_BASE_URL).rstrip("/")


def _yilian_human_id() -> str:
    return str(os.environ.get("YILIAN_HEALTH_HUMAN_ID") or _env_file_value("YILIAN_HEALTH_HUMAN_ID") or "").strip()


def _yilian_headers() -> Dict[str, str]:
    token = (
        os.environ.get("YILIAN_HEALTH_BEARER_TOKEN")
        or os.environ.get("YILIAN_HEALTH_TOKEN")
        or _env_file_value("YILIAN_HEALTH_BEARER_TOKEN")
        or _env_file_value("YILIAN_HEALTH_TOKEN")
        or ""
    ).strip()
    if not token:
        return {}
    if token.lower().startswith("bearer "):
        return {"Authorization": token}
    return {"Authorization": f"Bearer {token}"}


def _env_file_value(name: str) -> str:
    root = Path(os.environ.get("SOULBOT_ROOT") or DEFAULT_SOULBOT_ROOT)
    for env_file in (root / ".env", root / "deploy" / ".env"):
        try:
            text = env_file.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^\n#]+)", text)
        if match:
            return match.group(1).strip().strip("\"'")
    return ""


def _resolve_health_date(value: Any = None) -> str:
    raw = str(value or "").strip()
    if raw in {"昨天", "昨日"}:
        return (date.today() - timedelta(days=1)).isoformat()
    return _resolve_date(raw)


def _number_value(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _display_number(value: float) -> int | float:
    return int(value) if value == int(value) else round(value, 1)


def _time_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"(\d{1,2}:\d{2})(?::\d{2})?", text)
    if match:
        return match.group(1)
    return text[-5:] if len(text) >= 5 else text


def _health_exception_label(value: Any) -> str:
    raw = _first_text(value)
    normalized = raw.strip().lower()
    if not normalized or normalized in {"0", "normal", "none", "null", "正常", "无异常"}:
        return ""
    labels = {
        "hrhigh": "心率偏高",
        "hrlow": "心率偏低",
        "bphigh": "血压偏高",
        "bplow": "血压偏低",
        "bloodoxygenlow": "血氧偏低",
        "spo2low": "血氧偏低",
        "temphigh": "体温偏高",
        "templow": "体温偏低",
    }
    return labels.get(normalized, raw)


def _health_rows(metric: str, day: str, page_size: int) -> Dict[str, Any]:
    human_id = _yilian_human_id()
    if not human_id:
        raise RuntimeError("缺少 YILIAN_HEALTH_HUMAN_ID 配置")
    config = HEALTH_METRIC_CONFIG[metric]
    return _get_json(
        _yilian_base_url() + str(config["endpoint"]),
        {
            "humanId": human_id,
            "dayTime": day,
            "pageNum": 1,
            "pageSize": max(1, min(int(page_size or 30), 100)),
        },
        extra_headers=_yilian_headers(),
    )


def _health_series(metric: str, rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    series: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        data_time = _first_text(row.get("dataTime"))
        exception_type = _health_exception_label(row.get("exceptionType"))
        item: Dict[str, Any] = {
            "time": _time_label(data_time),
            "dataTime": data_time,
            "exceptionType": exception_type,
        }
        if metric == "blood_pressure":
            systolic = _number_value(row.get("data1"))
            diastolic = _number_value(row.get("data2"))
            if systolic is None or diastolic is None:
                continue
            item["systolic"] = _display_number(systolic)
            item["diastolic"] = _display_number(diastolic)
        else:
            value = _number_value(row.get("data1"))
            if value is None:
                continue
            item["value"] = _display_number(value)
        series.append(item)
    return sorted(series, key=lambda item: str(item.get("dataTime") or item.get("time") or ""))


def _metric_values(metric: str, series: List[Mapping[str, Any]]) -> List[float]:
    values: List[float] = []
    for item in series:
        keys = ("systolic", "diastolic") if metric == "blood_pressure" else ("value",)
        for key in keys:
            value = _number_value(item.get(key))
            if value is not None:
                values.append(value)
    return values


def _health_summary(metric: str, series: List[Mapping[str, Any]]) -> Dict[str, Any]:
    if not series:
        return {"count": 0}
    latest = series[-1]
    if metric == "blood_pressure":
        systolic_values = [_number_value(item.get("systolic")) for item in series]
        diastolic_values = [_number_value(item.get("diastolic")) for item in series]
        systolic = [value for value in systolic_values if value is not None]
        diastolic = [value for value in diastolic_values if value is not None]
        return {
            "count": len(series),
            "latest": {
                "systolic": latest.get("systolic"),
                "diastolic": latest.get("diastolic"),
            },
            "systolic": {
                "min": _display_number(min(systolic)) if systolic else None,
                "max": _display_number(max(systolic)) if systolic else None,
                "avg": _display_number(sum(systolic) / len(systolic)) if systolic else None,
            },
            "diastolic": {
                "min": _display_number(min(diastolic)) if diastolic else None,
                "max": _display_number(max(diastolic)) if diastolic else None,
                "avg": _display_number(sum(diastolic) / len(diastolic)) if diastolic else None,
            },
        }
    values = _metric_values(metric, series)
    return {
        "count": len(series),
        "latest": latest.get("value"),
        "min": _display_number(min(values)) if values else None,
        "max": _display_number(max(values)) if values else None,
        "avg": _display_number(sum(values) / len(values)) if values else None,
    }


def _health_text(payload: Mapping[str, Any]) -> str:
    label = _first_text(payload.get("label"), "健康数据")
    unit = _first_text(payload.get("unit"))
    day = _first_text(payload.get("date"))
    series = payload.get("series") if isinstance(payload.get("series"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    if not series:
        return f"{day}没有查到{label}记录。来源：易联健康。"

    latest = summary.get("latest")
    if isinstance(latest, Mapping):
        latest_text = f"{latest.get('systolic')}/{latest.get('diastolic')} {unit}".strip()
    else:
        latest_text = f"{latest} {unit}".strip()
    lines = [f"{day}{label}记录已查到，最近一次是 {latest_text}。"]
    if payload.get("metric") == "blood_pressure":
        systolic = summary.get("systolic") if isinstance(summary.get("systolic"), Mapping) else {}
        diastolic = summary.get("diastolic") if isinstance(summary.get("diastolic"), Mapping) else {}
        lines.append(
            f"共 {summary.get('count', len(series))} 条记录，收缩压范围 {systolic.get('min')}~{systolic.get('max')}，"
            f"舒张压范围 {diastolic.get('min')}~{diastolic.get('max')}。"
        )
    else:
        lines.append(
            f"共 {summary.get('count', len(series))} 条记录，范围 {summary.get('min')}~{summary.get('max')} {unit}，"
            f"平均约 {summary.get('avg')} {unit}。"
        )
    exception_count = sum(1 for item in series if _first_text(item.get("exceptionType")))
    if exception_count:
        lines.append(f"其中有 {exception_count} 条记录带异常标记，建议结合身体感受，必要时联系家人或医生。")
    else:
        lines.append("记录没有明显异常标记；如有胸闷、头晕、发热或持续不适，请及时联系家人或医生。")
    lines.append("来源：易联健康。")
    return "\n".join(lines)


def health_query(args: Mapping[str, Any], **_: Any) -> str:
    metric = _first_text(args.get("metric")).lower()
    alias_map = {
        "hr": "heart_rate",
        "heart": "heart_rate",
        "心率": "heart_rate",
        "bp": "blood_pressure",
        "血压": "blood_pressure",
        "spo2": "blood_oxygen",
        "oxygen": "blood_oxygen",
        "血氧": "blood_oxygen",
        "temp": "temperature",
        "体温": "temperature",
    }
    metric = alias_map.get(metric, metric)
    if metric not in HEALTH_METRIC_CONFIG:
        return _tool_error("请指定要查询的健康指标：心率、血压、血氧或体温。")
    day = _resolve_health_date(args.get("date") or args.get("dayTime"))
    try:
        page_size = int(args.get("page_size") or args.get("pageSize") or 30)
    except (TypeError, ValueError):
        page_size = 30
    config = HEALTH_METRIC_CONFIG[metric]
    try:
        data = _health_rows(metric, day, page_size)
        if int(data.get("code") or 0) not in {0, 200}:
            return _tool_error(f"健康数据查询失败：{data.get('msg') or '接口返回异常'}", source="yilian_health")
        series = _health_series(metric, data.get("rows"))
        payload = {
            "metric": metric,
            "label": config["label"],
            "unit": config["unit"],
            "date": day,
            "summary": _health_summary(metric, series),
            "series": series,
            "source": "易联健康",
        }
        return _tool_ok(_health_text(payload), health_metric=payload, source="yilian_health")
    except Exception as exc:
        return _tool_error(f"健康数据查询失败：{exc}", source="yilian_health")


def _parse_business(poi: Mapping[str, Any]) -> Mapping[str, Any]:
    business = poi.get("business")
    return business if isinstance(business, dict) else {}


def _parse_poi(poi: Mapping[str, Any]) -> Dict[str, Any]:
    business = _parse_business(poi)
    photos = poi.get("photos")
    photo_url = ""
    if isinstance(photos, list) and photos:
        first = photos[0]
        if isinstance(first, dict):
            photo_url = _first_text(first.get("url"))
    return {
        "id": _first_text(poi.get("id")),
        "name": _first_text(poi.get("name"), "未命名地点"),
        "type": _first_text(poi.get("type")),
        "typecode": _first_text(poi.get("typecode")),
        "address": _first_text(poi.get("address")),
        "province": _first_text(poi.get("pname")),
        "city": _first_text(poi.get("cityname")),
        "district": _first_text(poi.get("adname")),
        "location": _first_text(poi.get("location")),
        "distance": _first_text(poi.get("distance")),
        "rating": _first_text(business.get("rating"), poi.get("biz_ext", {}).get("rating") if isinstance(poi.get("biz_ext"), dict) else ""),
        "cost": _first_text(business.get("cost"), poi.get("biz_ext", {}).get("cost") if isinstance(poi.get("biz_ext"), dict) else ""),
        "opentime_today": _first_text(business.get("opentime_today"), business.get("opentime")),
        "tag": _first_text(business.get("tag"), business.get("keytag"), business.get("rectag")),
        "tel": _first_text(poi.get("tel")),
        "photo": photo_url,
    }


def _dedupe_pois(pois: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result: List[Dict[str, Any]] = []
    for poi in pois:
        item = dict(poi)
        key = (item.get("name"), item.get("address"), item.get("location"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _sort_pois(pois: List[Dict[str, Any]], sort: str = "balanced") -> List[Dict[str, Any]]:
    mode = (sort or "balanced").strip().lower()
    if mode in {"rating", "评分", "score"}:
        return sorted(pois, key=lambda p: (_to_float(p.get("rating")) or 0.0, -(_to_int(p.get("distance")) or 999999)), reverse=True)
    if mode in {"distance", "near", "附近", "近"}:
        return sorted(pois, key=lambda p: (_to_int(p.get("distance")) or 999999, -(_to_float(p.get("rating")) or 0.0)))
    if mode in {"price", "cheap", "便宜"}:
        return sorted(pois, key=lambda p: (_to_float(p.get("cost")) if _to_float(p.get("cost")) is not None else 999999, _to_int(p.get("distance")) or 999999))
    return sorted(
        pois,
        key=lambda p: (
            -(_to_float(p.get("rating")) or 0.0),
            _to_int(p.get("distance")) or 999999,
            _to_float(p.get("cost")) if _to_float(p.get("cost")) is not None else 999999,
        ),
    )


def _search_pois(
    *,
    place: str,
    category: str,
    keyword: str = "",
    city: str = "",
    radius_meters: int = 5000,
    max_results: int = 8,
    sort: str = "balanced",
) -> Dict[str, Any]:
    if category not in CATEGORY_CONFIG:
        raise ValueError("category 只能是 food、hotel 或 scenic")
    config = CATEGORY_CONFIG[category]
    anchor = _geocode(place, city=city)
    query = _first_text(keyword, config["default_query"])
    types = str(config["types"])

    collected: List[Dict[str, Any]] = []
    attempts: List[Dict[str, Any]] = []
    if anchor.get("location"):
        data = _amap_json(
            AMAP_PLACE_AROUND_URL,
            {
                "keywords": query,
                "location": anchor.get("location"),
                "radius": str(radius_meters),
                "sort": "distance",
                "types": types,
                "show_fields": "business,photos",
            },
        )
        pois = data.get("pois") if isinstance(data, dict) else []
        around_items = [_parse_poi(poi) for poi in pois if isinstance(poi, dict)]
        collected.extend(around_items)
        attempts.append({"method": "around", "query": query, "count": len(around_items)})

    text_city = _first_text(city, anchor.get("city"), anchor.get("district"))
    if len(collected) < max(3, min(max_results, 5)):
        text_query = f"{place} {query}".strip()
        data = _amap_json(
            AMAP_PLACE_TEXT_URL,
            {
                "keywords": text_query,
                "city": text_city,
                "city_limit": "true" if text_city else "",
                "types": types,
                "show_fields": "business,photos",
            },
        )
        pois = data.get("pois") if isinstance(data, dict) else []
        text_items = [_parse_poi(poi) for poi in pois if isinstance(poi, dict)]
        collected.extend(text_items)
        attempts.append({"method": "text", "query": text_query, "city": text_city, "count": len(text_items)})

    items = _sort_pois(_dedupe_pois(collected), sort=sort)[: max(1, min(int(max_results or 8), 15))]
    return {
        "provider": "amap",
        "category": category,
        "category_label": config["label"],
        "place": place,
        "anchor": anchor,
        "query": query,
        "pois": items,
        "attempts": attempts,
    }


def _poi_line(poi: Mapping[str, Any], index: int) -> str:
    name = _first_text(poi.get("name"), f"地点{index}")
    pieces = [f"{index}. {name}"]
    rating = _first_text(poi.get("rating"))
    cost = _first_text(poi.get("cost"))
    distance = _first_text(poi.get("distance"))
    address = _first_text(poi.get("address"))
    opentime = _first_text(poi.get("opentime_today"))
    tag = _first_text(poi.get("tag"), poi.get("type"))
    if rating:
        pieces.append(f"评分{rating}")
    if cost:
        pieces.append(f"人均/参考价约{cost}元")
    if distance:
        pieces.append(f"距离约{distance}米")
    if tag:
        pieces.append(tag)
    if address:
        pieces.append(address)
    if opentime:
        pieces.append(f"营业/开放：{opentime}")
    return "；".join(pieces)


def _pois_text(payload: Mapping[str, Any]) -> str:
    label = _first_text(payload.get("category_label"), "地点")
    place = _first_text(payload.get("place"))
    pois = payload.get("pois") if isinstance(payload.get("pois"), list) else []
    if not pois:
        return f"高德地图暂时没有查到{place}附近合适的{label}。建议换一个地标或放宽范围。"
    lines = [f"我为您查到{place}附近这些{label}，按老人出行优先考虑评分、距离和信息完整度："]
    for index, poi in enumerate(pois[:8], start=1):
        if isinstance(poi, dict):
            lines.append(_poi_line(poi, index))
    lines.append("建议出发前电话确认营业时间；老人出行尽量选离住处近、步行少、可打车直达的地点。")
    lines.append("来源：高德地图 POI 查询。")
    return "\n".join(lines)


def local_search(args: Mapping[str, Any], **_: Any) -> str:
    place = _first_text(args.get("place"), args.get("location"), args.get("city"))
    if not place:
        return _tool_error("请提供城市、区县或地标。")
    category = _first_text(args.get("category"), "food").lower()
    alias = {"美食": "food", "餐厅": "food", "住宿": "hotel", "酒店": "hotel", "景点": "scenic", "游玩": "scenic"}
    category = alias.get(category, category)
    try:
        payload = _search_pois(
            place=place,
            category=category,
            keyword=_first_text(args.get("keyword"), args.get("query")),
            city=_first_text(args.get("city")),
            radius_meters=int(args.get("radius_meters") or 5000),
            max_results=int(args.get("max_results") or 8),
            sort=_first_text(args.get("sort"), "balanced"),
        )
        return _tool_ok(_pois_text(payload), local_search=payload, source="amap")
    except Exception as exc:
        return _tool_error(f"本地查询失败：{exc}", source="amap")


def _parse_station_js(text: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    name_to_code: Dict[str, str] = dict(COMMON_STATIONS)
    code_to_name: Dict[str, str] = {code: name for name, code in COMMON_STATIONS.items()}
    for chunk in text.split("@"):
        parts = chunk.split("|")
        if len(parts) < 3:
            continue
        name = parts[1].strip()
        code = parts[2].strip()
        pinyin = parts[3].strip() if len(parts) > 3 else ""
        short = parts[4].strip() if len(parts) > 4 else ""
        if not name or not code:
            continue
        name_to_code[name] = code
        code_to_name[code] = name
        if pinyin:
            name_to_code[pinyin.lower()] = code
        if short:
            name_to_code[short.lower()] = code
        if name.endswith(("站", "东", "西", "南", "北")) and len(name) > 2:
            base = re.sub(r"(站|东|西|南|北)$", "", name)
            name_to_code.setdefault(base, code)
    return name_to_code, code_to_name


def _load_stations() -> Tuple[Dict[str, str], Dict[str, str]]:
    global _station_cache
    with _station_cache_lock:
        if _station_cache is not None:
            return _station_cache
        name_to_code = dict(COMMON_STATIONS)
        code_to_name = {code: name for name, code in COMMON_STATIONS.items()}
        try:
            text = _http_get_text(STATION_NAME_URL, {})
            name_to_code, code_to_name = _parse_station_js(text)
        except Exception:
            pass
        _station_cache = (name_to_code, code_to_name)
        return _station_cache


def _station_code(name: str) -> Tuple[str, str]:
    query = str(name or "").strip().replace("市", "")
    if not query:
        raise ValueError("站点名称不能为空")
    name_to_code, code_to_name = _load_stations()
    candidates = [query, query.replace("站", ""), f"{query}站"]
    for candidate in candidates:
        code = name_to_code.get(candidate) or name_to_code.get(candidate.lower())
        if code:
            return code, code_to_name.get(code, candidate)
    for station_name, code in name_to_code.items():
        if station_name.startswith(query) and re.search(r"[\u4e00-\u9fff]", station_name):
            return code, code_to_name.get(code, station_name)
    raise RuntimeError(f"没有找到 12306 站点：{name}")


def _seat_value(value: str) -> str:
    value = str(value or "").strip()
    if not value or value in {"--", "无", "*"}:
        return ""
    if value == "有":
        return "有票"
    return value


def _normalize_train_number(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def _seat_type_matches(label: str, query: str) -> bool:
    if not query:
        return True
    normalized_label = re.sub(r"[\s座席]", "", str(label or ""))
    normalized_query = re.sub(r"[\s座席]", "", str(query or ""))
    return bool(
        normalized_label
        and normalized_query
        and (normalized_query in normalized_label or normalized_label in normalized_query)
    )


def _ticket_price_items(prices: Mapping[str, Any], seat_type: str = "") -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for key, value in prices.items():
        code = str(key or "").strip()
        price = _first_text(value)
        if not code or not price or not re.search(r"\d", price):
            continue
        label = PRICE_SEAT_LABELS.get(code, code)
        if not _seat_type_matches(label, seat_type):
            continue
        items.append({"seat_type": label, "code": code, "price": price})
    return items


def _parse_left_ticket_row(row: str, station_map: Mapping[str, str]) -> Dict[str, Any]:
    fields = row.split("|")
    def f(index: int) -> str:
        return fields[index] if len(fields) > index else ""

    from_code = f(6)
    to_code = f(7)
    train = {
        "train_number": f(3),
        "train_no": f(2),
        "departure_station": station_map.get(from_code, from_code),
        "arrival_station": station_map.get(to_code, to_code),
        "departure_time": f(8),
        "arrival_time": f(9),
        "duration": f(10),
        "can_buy": f(11) == "Y",
        "start_train_date": f(13),
        "from_station_no": f(16),
        "to_station_no": f(17),
        "seat_types": f(35),
        "seats": [],
    }
    seat_indexes = [
        ("商务座/特等座", 32),
        ("一等座", 31),
        ("二等座", 30),
        ("高级软卧", 21),
        ("软卧", 23),
        ("硬卧", 28),
        ("软座", 24),
        ("硬座", 29),
        ("无座", 26),
    ]
    seats = []
    for seat_type, index in seat_indexes:
        available = _seat_value(f(index))
        if available:
            seats.append({"seat_type": seat_type, "available": available})
    train["seats"] = seats
    return train


def _query_ticket_price(train: Mapping[str, Any], train_date: str) -> Dict[str, Any]:
    params = {
        "train_no": train.get("train_no"),
        "from_station_no": train.get("from_station_no"),
        "to_station_no": train.get("to_station_no"),
        "seat_types": train.get("seat_types"),
        "train_date": train_date,
    }
    if not all(params.values()):
        return {}
    try:
        data = _get_json(TICKET_PRICE_URL, params)
        result = data.get("data") if isinstance(data, dict) else {}
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _query_trains(
    *,
    departure: str,
    destination: str,
    train_date: str,
    preference: str = "earliest",
    highspeed_only: bool = False,
    max_results: int = 8,
    train_number: str = "",
) -> Dict[str, Any]:
    from_code, from_name = _station_code(departure)
    to_code, to_name = _station_code(destination)
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    ticket_headers = {"Referer": "https://kyfw.12306.cn/otn/leftTicket/init"}
    try:
        _http_get_text(
            "https://kyfw.12306.cn/otn/leftTicket/init",
            {},
            extra_headers=ticket_headers,
            opener=opener,
        )
    except Exception:
        pass
    last_error = ""
    data: Dict[str, Any] = {}
    for endpoint in LEFT_TICKET_ENDPOINTS:
        try:
            candidate = _get_json(
                endpoint,
                {
                    "leftTicketDTO.train_date": train_date,
                    "leftTicketDTO.from_station": from_code,
                    "leftTicketDTO.to_station": to_code,
                    "purpose_codes": "ADULT",
                },
                extra_headers=ticket_headers,
                opener=opener,
            )
            if isinstance(candidate, dict) and candidate.get("data"):
                data = candidate
                break
        except Exception as exc:
            last_error = str(exc)
    if not data:
        raise RuntimeError(last_error or "12306 没有返回车次数据")

    payload = data.get("data") if isinstance(data.get("data"), dict) else {}
    results = payload.get("result") if isinstance(payload, dict) else []
    station_map = payload.get("map") if isinstance(payload, dict) and isinstance(payload.get("map"), dict) else {}
    trains = [_parse_left_ticket_row(row, station_map) for row in results if isinstance(row, str)]
    if highspeed_only:
        trains = [
            train for train in trains
            if str(train.get("train_number", "")).startswith(("G", "D", "C"))
        ]
    trains = [train for train in trains if train.get("train_number")]
    target_train_number = _normalize_train_number(train_number)
    if target_train_number:
        trains = [
            train for train in trains
            if _normalize_train_number(train.get("train_number")) == target_train_number
        ]

    pref = (preference or "earliest").lower()
    if pref in {"latest", "最晚"}:
        trains.sort(key=lambda t: str(t.get("departure_time") or ""), reverse=True)
    elif pref in {"fastest", "shortest", "最快"}:
        trains.sort(key=lambda t: _duration_minutes(str(t.get("duration") or "")) or 999999)
    else:
        trains.sort(key=lambda t: str(t.get("departure_time") or "99:99"))

    selected = trains[: max(1, min(int(max_results or 8), 15))]

    return {
        "provider": "12306",
        "date": train_date,
        "departure": {"input": departure, "station": from_name, "code": from_code},
        "destination": {"input": destination, "station": to_name, "code": to_code},
        "preference": preference,
        "highspeed_only": highspeed_only,
        "trains": selected,
        "total_count": len(trains),
    }


def _train_price_text(payload: Mapping[str, Any]) -> str:
    departure = payload.get("departure", {}) if isinstance(payload.get("departure"), dict) else {}
    destination = payload.get("destination", {}) if isinstance(payload.get("destination"), dict) else {}
    train = payload.get("train") if isinstance(payload.get("train"), dict) else {}
    prices = payload.get("prices") if isinstance(payload.get("prices"), list) else []
    date_text = _first_text(payload.get("date"))
    route = f"{departure.get('station') or departure.get('input')} → {destination.get('station') or destination.get('input')}"
    train_number = _first_text(train.get("train_number"), "该车次")
    time_text = ""
    if train.get("departure_time") or train.get("arrival_time"):
        time_text = f"，{train.get('departure_time')}发，{train.get('arrival_time')}到"
    if not prices:
        return (
            f"{date_text} {route} {train_number}{time_text}。12306 当前没有返回明确票价明细，"
            "票价请以 12306 或车站实时显示为准。"
        )
    price_text = "、".join(
        f"{item.get('seat_type')} {item.get('price')}"
        for item in prices
        if isinstance(item, dict) and item.get("seat_type") and item.get("price")
    )
    return (
        f"{date_text} {route} {train_number}{time_text} 的票价参考：{price_text}。"
        "余票、价格和是否可购买会实时变化，请以 12306 最终显示为准。"
    )


def _duration_minutes(value: str) -> Optional[int]:
    text = str(value or "")
    hour = 0
    minute = 0
    match = re.search(r"(\d+):(\d+)", text)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    match = re.search(r"(\d+)\s*小时", text)
    if match:
        hour = int(match.group(1))
    match = re.search(r"(\d+)\s*分", text)
    if match:
        minute = int(match.group(1))
    return hour * 60 + minute if hour or minute else None


def _train_text(payload: Mapping[str, Any]) -> str:
    departure = payload.get("departure", {}) if isinstance(payload.get("departure"), dict) else {}
    destination = payload.get("destination", {}) if isinstance(payload.get("destination"), dict) else {}
    trains = payload.get("trains") if isinstance(payload.get("trains"), list) else []
    date_text = _first_text(payload.get("date"))
    route = f"{departure.get('station') or departure.get('input')} → {destination.get('station') or destination.get('input')}"
    if not trains:
        return f"{date_text} {route} 暂时没有查到车次。建议改查相邻车站、汽车或飞机等替代方案。"
    lines = [f"我查到 {date_text} {route} 的车次，先列最适合参考的几趟："]
    first = trains[0] if isinstance(trains[0], dict) else {}
    if first:
        lines.append(
            f"首选：{first.get('train_number')}，{first.get('departure_time')} 从{first.get('departure_station')}出发，"
            f"{first.get('arrival_time')} 到{first.get('arrival_station')}，历时{first.get('duration')}。"
        )
    for index, train in enumerate(trains[:8], start=1):
        if not isinstance(train, dict):
            continue
        seats = train.get("seats") if isinstance(train.get("seats"), list) else []
        seat_text = "、".join(
            f"{seat.get('seat_type')}{seat.get('available')}"
            for seat in seats[:4]
            if isinstance(seat, dict) and seat.get("available")
        ) or "余票以 12306 为准"
        lines.append(
            f"{index}. {train.get('train_number')}：{train.get('departure_time')}发，"
            f"{train.get('arrival_time')}到，{train.get('duration')}，"
            f"{train.get('departure_station')} → {train.get('arrival_station')}，{seat_text}"
        )
    lines.append("余票、价格和是否可购买会实时变化，请以 12306 最终显示为准；老人出行建议预留进站和换乘时间。")
    lines.append("来源：12306 公开车次/余票查询。")
    return "\n".join(lines)


def train_tickets(args: Mapping[str, Any], **_: Any) -> str:
    departure = _first_text(args.get("departure"), args.get("from"), args.get("from_city"))
    destination = _first_text(args.get("destination"), args.get("to"), args.get("to_city"))
    if not departure or not destination:
        return _tool_error("请提供出发地和目的地，例如：福州到厦门。")
    try:
        train_date = _resolve_date(_first_text(args.get("date"), args.get("date_ref"), "明天"))
        payload = _query_trains(
            departure=departure,
            destination=destination,
            train_date=train_date,
            preference=_first_text(args.get("preference"), "earliest"),
            highspeed_only=bool(args.get("highspeed_only", False)),
            max_results=int(args.get("max_results") or 8),
        )
        return _tool_ok(_train_text(payload), train_tickets=payload, source="12306")
    except Exception as exc:
        return _tool_error(f"车票查询失败：{exc}", source="12306")


def train_ticket_price(args: Mapping[str, Any], **_: Any) -> str:
    departure = _first_text(args.get("departure"), args.get("from"), args.get("from_city"))
    destination = _first_text(args.get("destination"), args.get("to"), args.get("to_city"))
    if not departure or not destination:
        return _tool_error("请提供出发地和目的地，例如：福州到厦门。", source="12306")
    try:
        train_date = _resolve_date(_first_text(args.get("date"), args.get("date_ref"), "明天"))
        train_number = _first_text(args.get("train_number"), args.get("train_no"), args.get("train"))
        payload = _query_trains(
            departure=departure,
            destination=destination,
            train_date=train_date,
            preference=_first_text(args.get("preference"), "earliest"),
            highspeed_only=bool(args.get("highspeed_only", False)),
            max_results=15,
            train_number=train_number,
        )
        trains = payload.get("trains") if isinstance(payload.get("trains"), list) else []
        if not trains:
            target = f" {train_number}" if train_number else ""
            return _tool_error(f"没有查到{train_date} {departure}到{destination}{target} 的车次。", source="12306")
        train = trains[0] if isinstance(trains[0], dict) else {}
        prices = _query_ticket_price(train, train_date)
        seat_type = _first_text(args.get("seat_type"), args.get("seat"))
        price_items = _ticket_price_items(prices, seat_type=seat_type)
        result = {
            "provider": "12306",
            "date": train_date,
            "departure": payload.get("departure"),
            "destination": payload.get("destination"),
            "train": train,
            "seat_type": seat_type,
            "prices": price_items,
            "price_raw": prices,
        }
        return _tool_ok(_train_price_text(result), train_ticket_price=result, source="12306")
    except Exception as exc:
        return _tool_error(f"票价查询失败：{exc}", source="12306")


WEB_SEARCH_SCHEMA = {
    "description": "通用联网搜索工具。适合查询实时信息、新闻、政策介绍、体育赛程、百科类公开资料和泛攻略参考；返回标题、链接和摘要。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词，尽量包含日期、地点或主题，例如：2026-06-16 世界杯赛程"},
            "objective": {
                "type": "string",
                "description": "可选。搜索目标，用自然语言说明希望一次汇总什么信息；Parallel 搜索会优先使用。",
            },
            "search_queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选。给 Parallel 搜索的多个关键词查询，最多 5 个；普通搜索源会退化使用 query。",
            },
            "limit": {"type": "integer", "description": "最多返回结果数，1-12，默认 12", "default": 12},
        },
    },
}

WEB_EXTRACT_SCHEMA = {
    "description": "通用网页正文提取工具。适合在 web_search 返回可靠链接后读取页面正文，用于整理更准确的中文答复。",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要读取的单个 http/https 网页 URL"},
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要读取的多个 http/https 网页 URL，最多 5 个",
            },
            "max_chars": {"type": "integer", "description": "每个网页最多提取字符数，默认 8000", "default": 8000},
        },
    },
}

SOUL_WEATHER_SCHEMA = {
    "description": "查询中国城市、区县或地标的实时天气/未来天气，适合回答老人出门穿衣、是否下雨、旅行天气。",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市、区县或地标，例如：福州、闽江大学、厦门鼓浪屿"},
            "date": {"type": "string", "description": "日期，可填 YYYY-MM-DD、今天、明天、后天、周末"},
            "days": {"type": "integer", "description": "预报天数，1-4 天", "default": 4},
        },
        "required": ["city"],
    },
}

TRAIN_TICKETS_SCHEMA = {
    "description": "查询中国铁路 12306 车次、时刻和余票参考，不查询票价。适合用户查火车票、高铁票、动车票有哪些、几点发车、是否有票；旅游规划流程由 travel-planner skill 编排多个原子工具。",
    "parameters": {
        "type": "object",
        "properties": {
            "departure": {"type": "string", "description": "出发城市或火车站，例如：福州、北京南"},
            "destination": {"type": "string", "description": "到达城市或火车站，例如：厦门、上海虹桥"},
            "date": {"type": "string", "description": "乘车日期，可填 YYYY-MM-DD、明天、后天、周末"},
            "preference": {
                "type": "string",
                "enum": ["earliest", "latest", "fastest"],
                "description": "排序偏好：earliest 最早发车，latest 最晚发车，fastest 历时最短",
                "default": "earliest",
            },
            "highspeed_only": {"type": "boolean", "description": "是否只看 G/D/C 高铁动车", "default": False},
            "max_results": {"type": "integer", "description": "最多返回车次数", "default": 8},
        },
        "required": ["departure", "destination"],
    },
}

TRAIN_TICKET_PRICE_SCHEMA = {
    "description": "查询某趟中国铁路车次的票价。仅当用户明确询问多少钱、票价、价格、一等座/二等座价格时使用；普通车次和旅游规划不要调用本工具。",
    "parameters": {
        "type": "object",
        "properties": {
            "departure": {"type": "string", "description": "出发城市或火车站，例如：福州、北京南"},
            "destination": {"type": "string", "description": "到达城市或火车站，例如：厦门、上海虹桥"},
            "date": {"type": "string", "description": "乘车日期，可填 YYYY-MM-DD、明天、后天、周末"},
            "train_number": {"type": "string", "description": "可选，指定车次，例如：G5103、D3333；用户问某趟车多少钱时必须填写"},
            "seat_type": {"type": "string", "description": "可选，席别，例如：二等座、一等座、商务座、硬座"},
            "preference": {
                "type": "string",
                "enum": ["earliest", "latest", "fastest"],
                "description": "未指定车次时用于选择首选车次：earliest 最早发车，latest 最晚发车，fastest 历时最短",
                "default": "earliest",
            },
            "highspeed_only": {"type": "boolean", "description": "是否只看 G/D/C 高铁动车", "default": False},
        },
        "required": ["departure", "destination"],
    },
}

SOUL_LOCAL_SEARCH_SCHEMA = {
    "description": "查询指定地点附近美食、住宿或景点，来源高德地图，适合推荐餐厅、酒店、景区和老人友好地点。",
    "parameters": {
        "type": "object",
        "properties": {
            "place": {"type": "string", "description": "城市、区县或地标，例如：福州仓山、厦门中山路、莆田"},
            "category": {"type": "string", "enum": ["food", "hotel", "scenic"], "description": "food 美食，hotel 住宿，scenic 景点"},
            "keyword": {"type": "string", "description": "偏好关键词，例如：小龙虾、海边、便宜、博物馆、清淡"},
            "city": {"type": "string", "description": "可选城市名，用于提高定位精度"},
            "radius_meters": {"type": "integer", "description": "周边搜索半径，默认 5000 米", "default": 5000},
            "max_results": {"type": "integer", "description": "最多返回结果数", "default": 8},
            "sort": {"type": "string", "enum": ["balanced", "rating", "distance", "price"], "description": "排序方式"},
        },
        "required": ["place", "category"],
    },
}

SOUL_HEALTH_SCHEMA = {
    "description": "查询易联手表健康记录，适合用户查看心率、血压、血氧、体温等历史记录；只做数据查看和温和提醒，不做医疗诊断。",
    "parameters": {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "enum": ["heart_rate", "blood_pressure", "blood_oxygen", "temperature"],
                "description": "健康指标：heart_rate 心率，blood_pressure 血压，blood_oxygen 血氧，temperature 体温",
            },
            "date": {"type": "string", "description": "查询日期，可填 YYYY-MM-DD、今天、昨天"},
            "page_size": {"type": "integer", "description": "最多返回记录数，默认 30", "default": 30},
        },
        "required": ["metric"],
    },
}

def register(ctx) -> None:
    tools = [
        ("weather", SOUL_WEATHER_SCHEMA, weather, "☁️"),
        ("train_tickets", TRAIN_TICKETS_SCHEMA, train_tickets, "🚄"),
        ("train_ticket_price", TRAIN_TICKET_PRICE_SCHEMA, train_ticket_price, "🎫"),
        ("local_search", SOUL_LOCAL_SEARCH_SCHEMA, local_search, "📍"),
        ("health_query", SOUL_HEALTH_SCHEMA, health_query, "♡"),
        ("web_search", WEB_SEARCH_SCHEMA, web_search, "🔍"),
        ("web_extract", WEB_EXTRACT_SCHEMA, web_extract, "📄"),
    ]
    for name, schema, handler, emoji in tools:
        ctx.register_tool(
            name=name,
            toolset="soul_companion",
            schema=schema,
            handler=handler,
            emoji=emoji,
        )
