from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Any
from urllib.parse import quote, urlparse

from aiohttp import ClientError, ClientResponse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_GO2RTC_RTSP_URL,
    CONF_GO2RTC_URL,
    CONF_STREAM_NAME,
    CONF_STREAM_URL,
)


class Go2RTCError(Exception):
    """Base go2rtc client error."""


class CannotConnect(Go2RTCError):
    """go2rtc cannot be reached or returned an unexpected response."""


class InvalidAuth(Go2RTCError):
    """Xiaomi credentials were rejected."""


class NoCamerasFound(Go2RTCError):
    """No Xiaomi cameras were returned by go2rtc."""


@dataclass(slots=True)
class XiaomiSource:
    key: str
    name: str
    url: str
    info: str | None = None

    @property
    def unique_hash(self) -> str:
        return sha1(self.url.encode("utf-8")).hexdigest()[:12]

    @property
    def model(self) -> str | None:
        query = urlparse(self.url).query
        for part in query.split("&"):
            if part.startswith("model="):
                return part.split("=", 1)[1] or None
        return None


class Go2RTCClient:
    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        rtsp_base_url: str | None = None,
    ) -> None:
        self.hass = hass
        self.base_url = _normalize_http_url(base_url)
        self.rtsp_base_url = _normalize_optional_url(rtsp_base_url)
        self._session = async_get_clientsession(hass)

    @classmethod
    def from_entry(cls, hass: HomeAssistant, entry: ConfigEntry) -> Go2RTCClient:
        return cls(
            hass,
            entry.data[CONF_GO2RTC_URL],
            entry.data.get(CONF_GO2RTC_RTSP_URL),
        )

    async def async_check(self) -> dict[str, Any]:
        data = await self._request_json("GET", "/api")
        if not isinstance(data, dict):
            raise CannotConnect("go2rtc API returned an unexpected response")
        return data

    async def async_xiaomi_login(
        self,
        username: str | None = None,
        password: str | None = None,
        captcha: str | None = None,
        verify: str | None = None,
    ) -> dict[str, Any] | None:
        form: dict[str, str] = {}
        if username is not None or password is not None:
            form["username"] = username or ""
            form["password"] = password or ""
        if captcha:
            form["captcha"] = captcha
        if verify:
            form["verify"] = verify

        response = await self._request("POST", "/api/xiaomi", data=form, allow_unauthorized=True)
        if response.status == 401:
            try:
                data = await response.json()
            except Exception as exc:  # noqa: BLE001
                raise InvalidAuth("Xiaomi login failed") from exc
            if isinstance(data, dict):
                return data
            raise InvalidAuth("Xiaomi login failed")

        if response.status >= 400:
            text = await response.text()
            raise InvalidAuth(text.strip() or "Xiaomi login failed")

        response.release()
        return None

    async def async_xiaomi_users(self) -> list[str]:
        data = await self._request_json("GET", "/api/xiaomi")
        if isinstance(data, list):
            return [str(item) for item in data]
        raise CannotConnect("go2rtc Xiaomi API returned an unexpected users response")

    async def async_xiaomi_sources(self, account_id: str, region: str) -> list[XiaomiSource]:
        try:
            data = await self._request_json(
                "GET",
                "/api/xiaomi",
                params={"id": account_id, "region": region},
            )
        except CannotConnect as exc:
            if "no sources" in str(exc).lower():
                raise NoCamerasFound("No Xiaomi cameras found") from exc
            raise

        raw_sources = data.get("sources") if isinstance(data, dict) else None
        if not raw_sources:
            raise NoCamerasFound("No Xiaomi cameras found")

        sources: list[XiaomiSource] = []
        for index, item in enumerate(raw_sources):
            if not isinstance(item, dict) or not item.get("url"):
                continue
            name = str(item.get("name") or f"Xiaomi Camera {index + 1}")
            sources.append(
                XiaomiSource(
                    key=str(index),
                    name=name,
                    info=str(item.get("info") or ""),
                    url=str(item["url"]),
                )
            )

        if not sources:
            raise NoCamerasFound("No Xiaomi cameras found")
        return sources

    async def async_create_stream(self, stream_name: str, stream_url: str) -> None:
        response = await self._request(
            "PUT",
            "/api/streams",
            params={"name": stream_name, "src": stream_url},
        )
        if response.status >= 400:
            text = await response.text()
            raise CannotConnect(text.strip() or "Could not create go2rtc stream")
        response.release()

    async def async_camera_image(self, stream_name: str) -> bytes | None:
        response = await self._request(
            "GET",
            "/api/frame.jpeg",
            params={"src": stream_name},
        )
        if response.status >= 400:
            response.release()
            return None
        return await response.read()

    def rtsp_stream_url(self, stream_name: str) -> str:
        stream_path = quote(stream_name, safe="")
        if self.rtsp_base_url:
            return f"{self.rtsp_base_url.rstrip('/')}/{stream_path}"

        parsed = urlparse(self.base_url)
        hostname = parsed.hostname or "127.0.0.1"
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        return f"rtsp://{hostname}:8554/{stream_path}"

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._request(method, path, **kwargs)
        if response.status >= 400:
            text = await response.text()
            raise CannotConnect(text.strip() or f"go2rtc HTTP {response.status}")
        try:
            return await response.json()
        except Exception as exc:  # noqa: BLE001
            raise CannotConnect("go2rtc returned invalid JSON") from exc

    async def _request(
        self,
        method: str,
        path: str,
        allow_unauthorized: bool = False,
        **kwargs: Any,
    ) -> ClientResponse:
        url = f"{self.base_url}{path}"
        try:
            response = await self._session.request(method, url, timeout=30, **kwargs)
        except ClientError as exc:
            raise CannotConnect(f"Cannot connect to go2rtc at {self.base_url}") from exc

        if response.status == 401 and allow_unauthorized:
            return response
        return response


def camera_hash(camera: dict[str, Any]) -> str:
    return sha1(str(camera.get(CONF_STREAM_URL, "")).encode("utf-8")).hexdigest()[:12]


def _normalize_http_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        raise CannotConnect("go2rtc URL is empty")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CannotConnect("go2rtc URL must start with http:// or https://")
    return value


def _normalize_optional_url(value: str | None) -> str | None:
    value = (value or "").strip().rstrip("/")
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.netloc:
        raise CannotConnect("RTSP URL must start with rtsp:// or rtsps://")
    return value


def stored_camera(source: XiaomiSource, stream_name: str) -> dict[str, str]:
    return {
        "key": source.key,
        "name": source.name,
        "model": source.model or "",
        CONF_STREAM_NAME: stream_name,
        CONF_STREAM_URL: source.url,
    }
