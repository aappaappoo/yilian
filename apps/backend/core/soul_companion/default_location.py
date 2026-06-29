"""Default location resolution for Soul companion sessions.

The weather and local-search tools intentionally do not guess a city.  This
module resolves a best-effort default location from request IP and stores an
explicit user-confirmed default per session/user.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import httpx
from loguru import logger


AMAP_IP_URL = "https://restapi.amap.com/v3/ip"
DEFAULT_SOULBOT_ROOT = "/Users/apapoo/Desktop/Github_Hub/Soulbot"
_CACHE_TTL = timedelta(minutes=30)


@dataclass(frozen=True)
class DefaultLocation:
    city: str = ""
    province: str = ""
    adcode: str = ""
    source: str = "unknown"
    status: str = "needs_confirmation"
    reason: str = ""
    confirmed: bool = False
    client_ip: str = ""

    @property
    def usable(self) -> bool:
        return bool(self.city and self.status in {"resolved", "confirmed"})

    @property
    def needs_confirmation(self) -> bool:
        return not self.usable

    def label(self) -> str:
        return self.city or self.province

    def to_prompt_context(self) -> Dict[str, str]:
        return {
            "city": self.city,
            "province": self.province,
            "adcode": self.adcode,
            "source": self.source,
            "status": self.status,
            "reason": self.reason,
            "confirmed": "true" if self.confirmed else "false",
            "client_ip": self.client_ip,
        }


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            value = next((item for item in value if str(item).strip()), "")
        text = str(value).strip()
        if text and text != "[]":
            return text
    return ""


def _amap_key() -> str:
    key = (
        os.environ.get("SOUL_AMAP_API_KEY")
        or os.environ.get("AMAP_API_KEY")
        or os.environ.get("GAODE_API_KEY")
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
        match = re.search(r"(?m)^\s*(?:SOUL_AMAP_API_KEY|AMAP_API_KEY|GAODE_API_KEY)\s*=\s*([^\n#]+)", text)
        if match:
            return match.group(1).strip().strip("\"'")
    return ""


def _is_public_ipv4(raw_ip: str) -> bool:
    try:
        parsed = ip_address(raw_ip)
    except ValueError:
        return False
    return bool(
        parsed.version == 4
        and not parsed.is_private
        and not parsed.is_loopback
        and not parsed.is_link_local
        and not parsed.is_multicast
        and not parsed.is_reserved
        and not parsed.is_unspecified
    )


def _is_mainland_location(province: str, city: str, adcode: str) -> bool:
    text = f"{province}{city}"
    if any(name in text for name in ("香港", "澳门", "台湾")):
        return False
    if not city and not province:
        return False
    if adcode.startswith(("81", "82", "71")):
        return False
    return True


class DefaultLocationService:
    def __init__(self) -> None:
        self._ip_cache: Dict[str, tuple[datetime, DefaultLocation]] = {}
        self._session_confirmed: Dict[str, DefaultLocation] = {}
        self._user_confirmed: Dict[str, DefaultLocation] = {}

    def _cache_get(self, client_ip: str) -> Optional[DefaultLocation]:
        item = self._ip_cache.get(client_ip)
        if item is None:
            return None
        created_at, location = item
        if datetime.now() - created_at > _CACHE_TTL:
            self._ip_cache.pop(client_ip, None)
            return None
        return location

    def _cache_set(self, client_ip: str, location: DefaultLocation) -> DefaultLocation:
        self._ip_cache[client_ip] = (datetime.now(), location)
        return location

    async def resolve(
        self,
        *,
        session_id: str = "",
        user_id: str = "",
        client_ip: str = "",
    ) -> DefaultLocation:
        if session_id and session_id in self._session_confirmed:
            return self._session_confirmed[session_id]
        if user_id and user_id in self._user_confirmed:
            return self._user_confirmed[user_id]

        ip = str(client_ip or "").strip()
        if not ip:
            return DefaultLocation(status="needs_confirmation", reason="missing_ip")
        if not _is_public_ipv4(ip):
            return DefaultLocation(
                status="needs_confirmation",
                reason="local_or_non_ipv4_ip",
                client_ip=ip,
            )

        cached = self._cache_get(ip)
        if cached is not None:
            return cached

        key = _amap_key()
        if not key:
            return DefaultLocation(
                status="needs_confirmation",
                reason="amap_key_missing",
                client_ip=ip,
            )

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(AMAP_IP_URL, params={"key": key, "ip": ip, "output": "JSON"})
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning(f"[default_location] IP定位失败: ip={ip}, error={type(exc).__name__}: {exc}")
            return self._cache_set(
                ip,
                DefaultLocation(status="needs_confirmation", reason="ip_lookup_failed", client_ip=ip),
            )

        if not isinstance(payload, Mapping) or str(payload.get("status", "1")) != "1":
            reason = _first_text(payload.get("info") if isinstance(payload, Mapping) else "", "ip_lookup_rejected")
            return self._cache_set(
                ip,
                DefaultLocation(status="needs_confirmation", reason=reason, client_ip=ip),
            )

        province = _first_text(payload.get("province"))
        city = _first_text(payload.get("city"), province)
        adcode = _first_text(payload.get("adcode"))
        if not _is_mainland_location(province, city, adcode):
            return self._cache_set(
                ip,
                DefaultLocation(
                    city=city,
                    province=province,
                    adcode=adcode,
                    source="amap_ip",
                    status="needs_confirmation",
                    reason="not_mainland_or_empty",
                    client_ip=ip,
                ),
            )

        return self._cache_set(
            ip,
            DefaultLocation(
                city=city,
                province=province,
                adcode=adcode,
                source="amap_ip",
                status="resolved",
                reason="",
                client_ip=ip,
            ),
        )

    def confirm(
        self,
        *,
        city: str,
        province: str = "",
        session_id: str = "",
        user_id: str = "",
        client_ip: str = "",
    ) -> DefaultLocation:
        clean_city = str(city or "").strip()
        if not clean_city:
            raise ValueError("请提供要设为默认地点的城市。")
        location = DefaultLocation(
            city=clean_city,
            province=str(province or "").strip(),
            source="user_confirmed",
            status="confirmed",
            confirmed=True,
            client_ip=str(client_ip or "").strip(),
        )
        if session_id:
            self._session_confirmed[session_id] = location
        if user_id:
            self._user_confirmed[user_id] = location
        return location


default_location_service = DefaultLocationService()
