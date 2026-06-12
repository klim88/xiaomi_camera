from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_ACCOUNT_ID,
    CONF_CAMERAS,
    CONF_GO2RTC_RTSP_URL,
    CONF_GO2RTC_URL,
    CONF_REGION,
    CONF_SELECTED_CAMERAS,
    DEFAULT_GO2RTC_URL,
    DOMAIN,
    REGIONS,
)
from .go2rtc import CannotConnect, Go2RTCClient, InvalidAuth, NoCamerasFound, stored_camera


class XiaomiCameraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client: Go2RTCClient | None = None
        self._go2rtc_url: str = DEFAULT_GO2RTC_URL
        self._rtsp_url: str | None = None
        self._region: str = "ru"
        self._known_users: set[str] = set()
        self._accounts: list[str] = []
        self._account_id: str | None = None
        self._sources = []
        self._captcha: str | None = None
        self._verify_hint: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return XiaomiCameraOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            self._go2rtc_url = user_input[CONF_GO2RTC_URL]
            self._rtsp_url = user_input.get(CONF_GO2RTC_RTSP_URL) or None
            self._region = user_input[CONF_REGION]
            self._client = Go2RTCClient(self.hass, self._go2rtc_url, self._rtsp_url)

            try:
                await self._client.async_check()
                self._known_users = set(await self._client.async_xiaomi_users())
                challenge = await self._client.async_xiaomi_login(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                if challenge:
                    return await self._handle_challenge(challenge)
                return await self._async_after_login()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GO2RTC_URL, default=self._go2rtc_url): str,
                    vol.Optional(CONF_GO2RTC_RTSP_URL, default=self._rtsp_url or ""): str,
                    vol.Required(CONF_REGION, default=self._region): vol.In(REGIONS),
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_captcha(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                assert self._client is not None
                challenge = await self._client.async_xiaomi_login(captcha=user_input["captcha"])
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                if challenge:
                    return await self._handle_challenge(challenge)
                return await self._async_after_login()

        return self.async_show_form(
            step_id="captcha",
            data_schema=vol.Schema({vol.Required("captcha"): str}),
            errors=errors,
            description_placeholders={"captcha": self._captcha or ""},
        )

    async def async_step_verify(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                assert self._client is not None
                challenge = await self._client.async_xiaomi_login(verify=user_input["verify"])
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                if challenge:
                    return await self._handle_challenge(challenge)
                return await self._async_after_login()

        return self.async_show_form(
            step_id="verify",
            data_schema=vol.Schema({vol.Required("verify"): str}),
            errors=errors,
            description_placeholders={"verify_hint": self._verify_hint or ""},
        )

    async def async_step_account(self, user_input=None):
        if user_input is not None:
            self._account_id = user_input[CONF_ACCOUNT_ID]
            return await self._async_load_sources()

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema({vol.Required(CONF_ACCOUNT_ID): vol.In(_choices(self._accounts))}),
        )

    async def async_step_camera(self, user_input=None):
        errors: dict[str, str] = {}
        source_by_key = {source.key: source for source in self._sources}

        if user_input is not None:
            selected = user_input.get(CONF_SELECTED_CAMERAS) or []
            if isinstance(selected, str):
                selected = [selected]
            if not selected:
                errors["base"] = "no_camera_selected"
            else:
                try:
                    cameras = await self._async_prepare_cameras(
                        [source_by_key[key] for key in selected if key in source_by_key]
                    )
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                else:
                    return await self._async_create_entry(cameras)

        options = [
            selector.SelectOptionDict(value=source.key, label=_source_label(source))
            for source in self._sources
        ]
        default = [source.key for source in self._sources]
        return self.async_show_form(
            step_id="camera",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SELECTED_CAMERAS, default=default): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, multiple=True)
                    )
                }
            ),
            errors=errors,
        )

    async def _handle_challenge(self, challenge: dict[str, Any]):
        if challenge.get("captcha"):
            self._captcha = str(challenge["captcha"])
            return await self.async_step_captcha()
        self._verify_hint = str(challenge.get("verify_email") or challenge.get("verify_phone") or "")
        return await self.async_step_verify()

    async def _async_after_login(self):
        assert self._client is not None
        users = await self._client.async_xiaomi_users()
        new_users = [user for user in users if user not in self._known_users]
        self._accounts = new_users or users
        if not self._accounts:
            return self.async_abort(reason="no_accounts")
        if len(self._accounts) == 1:
            self._account_id = self._accounts[0]
            return await self._async_load_sources()
        return await self.async_step_account()

    async def _async_load_sources(self):
        errors: dict[str, str] = {}
        try:
            assert self._client is not None
            assert self._account_id is not None
            self._sources = await self._client.async_xiaomi_sources(self._account_id, self._region)
        except NoCamerasFound:
            errors["base"] = "no_cameras"
        except CannotConnect:
            errors["base"] = "cannot_connect"

        if errors:
            return self.async_show_form(
                step_id="account",
                data_schema=vol.Schema({vol.Required(CONF_ACCOUNT_ID): vol.In(_choices(self._accounts))}),
                errors=errors,
            )

        if len(self._sources) == 1:
            try:
                cameras = await self._async_prepare_cameras(self._sources)
            except CannotConnect:
                return self.async_show_form(
                    step_id="account",
                    data_schema=vol.Schema({vol.Required(CONF_ACCOUNT_ID): vol.In(_choices(self._accounts))}),
                    errors={"base": "cannot_connect"},
                )
            return await self._async_create_entry(cameras)
        return await self.async_step_camera()

    async def _async_prepare_cameras(self, sources) -> list[dict[str, str]]:
        assert self._client is not None
        cameras = []
        used_names: set[str] = set()

        for index, source in enumerate(sources, start=1):
            stream_name = _stream_name(source.name, index, used_names)
            await self._client.async_create_stream(stream_name, source.url)
            cameras.append(stored_camera(source, stream_name))

        return cameras

    async def _async_create_entry(self, cameras: list[dict[str, str]]):
        assert self._account_id is not None
        unique_id = f"{self._account_id}_{self._region}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        title = cameras[0]["name"] if len(cameras) == 1 else "Xiaomi Cameras"
        return self.async_create_entry(
            title=title,
            data={
                CONF_GO2RTC_URL: self._go2rtc_url,
                CONF_GO2RTC_RTSP_URL: self._rtsp_url or "",
                CONF_REGION: self._region,
                CONF_ACCOUNT_ID: self._account_id,
                CONF_CAMERAS: cameras,
            },
        )


class XiaomiCameraOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client = Go2RTCClient(
                self.hass,
                user_input[CONF_GO2RTC_URL],
                user_input.get(CONF_GO2RTC_RTSP_URL) or None,
            )
            try:
                await client.async_check()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                data = dict(self._entry.data)
                data[CONF_GO2RTC_URL] = user_input[CONF_GO2RTC_URL]
                data[CONF_GO2RTC_RTSP_URL] = user_input.get(CONF_GO2RTC_RTSP_URL) or ""
                self.hass.config_entries.async_update_entry(self._entry, data=data)
                await self.hass.config_entries.async_reload(self._entry.entry_id)
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_GO2RTC_URL,
                        default=self._entry.data.get(CONF_GO2RTC_URL, DEFAULT_GO2RTC_URL),
                    ): str,
                    vol.Optional(
                        CONF_GO2RTC_RTSP_URL,
                        default=self._entry.data.get(CONF_GO2RTC_RTSP_URL, ""),
                    ): str,
                }
            ),
            errors=errors,
        )


def _choices(items: list[str]) -> dict[str, str]:
    return {item: item for item in items}


def _source_label(source) -> str:
    model = source.model
    return f"{source.name} ({model})" if model else source.name


def _stream_name(name: str, index: int, used_names: set[str]) -> str:
    base = slugify(name) or f"camera_{index}"
    stream_name = f"xiaomi_{base}"
    if stream_name not in used_names:
        used_names.add(stream_name)
        return stream_name

    suffix = 2
    while f"{stream_name}_{suffix}" in used_names:
        suffix += 1
    stream_name = f"{stream_name}_{suffix}"
    used_names.add(stream_name)
    return stream_name
