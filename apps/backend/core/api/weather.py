"""Current weather endpoint for chat chrome."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel

from core.soul_companion.default_location import default_location_service
from core.soul_companion.runtime import _load_plugin

router = APIRouter(prefix="/api/weather", tags=["weather"])


class CurrentWeatherResponse(BaseModel):
    city: str
    temp: str
    condition: str
    quality: str


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _parse_weather_payload(payload: dict[str, Any], fallback_city: str) -> CurrentWeatherResponse:
    weather = payload.get("weather") if isinstance(payload.get("weather"), dict) else {}
    label = _first_text(weather.get("label"), weather.get("requested_location"), fallback_city)
    live = weather.get("live") if isinstance(weather.get("live"), dict) else {}
    forecast = weather.get("forecast") if isinstance(weather.get("forecast"), list) else []
    first_forecast = forecast[0] if forecast and isinstance(forecast[0], dict) else {}

    temp = _first_text(live.get("temperature"), first_forecast.get("daytemp"))
    condition = _first_text(live.get("weather"), first_forecast.get("dayweather"), "天气更新中")
    humidity = _first_text(live.get("humidity"))
    quality = f"湿度{humidity}%" if humidity else "稍后刷新"
    return CurrentWeatherResponse(
        city=label,
        temp=f"{temp}°C" if temp else "--°C",
        condition=condition,
        quality=quality,
    )


def _extract_client_ip(request: Request) -> str:
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        value = request.headers.get(header, "")
        if value:
            return value.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def _call_weather_tool(city: str) -> dict[str, Any]:
    plugin = _load_plugin()
    result = str(plugin.weather({"city": city, "days": 1}))
    payload = json.loads(result)
    if not isinstance(payload, dict):
        raise RuntimeError("weather tool returned non-object JSON")
    if not payload.get("success", True):
        raise RuntimeError(str(payload.get("error") or "weather tool failed"))
    return payload


@router.get("/current", response_model=CurrentWeatherResponse)
async def current_weather(request: Request) -> CurrentWeatherResponse:
    city = str(request.query_params.get("city") or request.query_params.get("location") or "").strip()
    default_location_context: dict[str, str] = {}
    if not city:
        default_location = await default_location_service.resolve(
            client_ip=_extract_client_ip(request),
        )
        default_location_context = default_location.to_prompt_context()
        city = default_location.city if default_location.usable else ""
    if not city:
        return CurrentWeatherResponse(
            city="选择城市",
            temp="--°C",
            condition="请确认城市",
            quality="无法通过 IP 定位",
        )
    try:
        del default_location_context
        payload = await asyncio.to_thread(_call_weather_tool, city)
        return _parse_weather_payload(payload, city)
    except Exception as exc:
        logger.warning(f"[天气] | Task=Chat天气刷新 | Soul天气查询失败: city={city}, error={type(exc).__name__}: {exc}")
        return CurrentWeatherResponse(
            city=city,
            temp="--°C",
            condition="天气更新中",
            quality="稍后刷新",
        )
