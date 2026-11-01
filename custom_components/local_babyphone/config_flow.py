"""UI configuration using the camera's local pairing key, never cloud credentials."""
import asyncio
import ipaddress
import re
import socket
import struct
import json
import probatio as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST,CONF_NAME
from homeassistant.helpers import selector
from homeassistant.core import callback
from .const import DOMAIN,CONF_PAIRING_KEY,CONF_CAMERA_SSID
from .protocol.crypto import DeviceCipher
from .protocol.client import IDENTITY
from .protocol.wire import ControlWire,frame
from .protocol.discovery import discover_camera,normalize_ssid

INPUT_ERRORS={'invalid_key','invalid_host','invalid_auth','invalid_camera_ssid','discovery_failed','discovery_ambiguous','host_or_ssid_required'}


def parse_key(value):
    try:key=bytes.fromhex(value[4:]) if value.startswith('hex:') else value.encode('ascii')
    except (ValueError,UnicodeError) as exc:raise ValueError('invalid_key') from exc
    if len(key)!=16:raise ValueError('invalid_key')
    return key


def normalize_host(value):
    value=value.strip().lower()
    try:return str(ipaddress.ip_address(value))
    except ValueError:
        if re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',value):return value
        raise ValueError('invalid_host') from None


def resolve_host(value,ssid):
    host=normalize_host(value) if value.strip() else None
    if ssid:
        found=discover_camera(ssid)
        if found:return found
    if host:return host
    raise ValueError('discovery_failed' if ssid else 'host_or_ssid_required')


def same_camera(entry,host,ssid):
    stored_ssid=entry.options.get(CONF_CAMERA_SSID,entry.data.get(CONF_CAMERA_SSID,''))
    return entry.data.get(CONF_HOST)==host or bool(ssid and ssid==stored_ssid)


def probe(host,key):
    import secrets
    cipher=DeviceCipher();session=secrets.token_bytes(16)
    wrapped=cipher.crypt(key,session)
    with socket.create_connection((host,6000),5) as sock:
        sock.settimeout(5);wire=ControlWire(sock)
        sock.sendall(frame(1,0,wrapped+b'0\0'))
        reply=wire.read()
        if struct.unpack_from('<H',reply,8)[0]!=0x8001:raise ValueError('invalid_auth')
        raw=json.dumps(IDENTITY,separators=(',',':')).encode()+b'\0';raw+=bytes(-len(raw)%16)
        sock.sendall(frame(2,1,cipher.crypt(session,raw)))
        for _ in range(15):
            reply=wire.read()
            if struct.unpack_from('<H',reply,8)[0]!=0x8002:continue
            try:
                info=json.loads(cipher.crypt(session,reply[11:],True).rstrip(b'\0'))
            except (ValueError,UnicodeError) as exc:raise ValueError('invalid_auth') from exc
            if not isinstance(info,dict) or 'Fw_version' not in info:raise ValueError('invalid_auth')
            return
        raise TimeoutError('No device-information response')


class LocalBabyphoneConfigFlow(config_entries.ConfigFlow,domain=DOMAIN):
    VERSION=1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LocalBabyphoneOptionsFlow()

    async def async_step_user(self,user_input=None):
        errors={}
        if user_input is not None:
            try:
                key=parse_key(user_input[CONF_PAIRING_KEY]);ssid=normalize_ssid(user_input.get(CONF_CAMERA_SSID,''))
                host=await self.hass.async_add_executor_job(resolve_host,user_input.get(CONF_HOST,''),ssid)
                if any(same_camera(entry,host,ssid) for entry in self._async_current_entries()):
                    return self.async_abort(reason='already_configured')
                await self.async_set_unique_id('ssid:'+ssid if ssid else host)
                self._abort_if_unique_id_configured()
                await self.hass.async_add_executor_job(probe,host,key)
            except (TimeoutError,OSError,EOFError):errors['base']='cannot_connect'
            except ValueError as exc:errors['base']=str(exc) if str(exc) in INPUT_ERRORS else 'invalid_auth'
            else:
                return self.async_create_entry(title=user_input.get(CONF_NAME) or 'Avent local',
                    data={CONF_HOST:host,CONF_PAIRING_KEY:user_input[CONF_PAIRING_KEY],CONF_CAMERA_SSID:ssid})
        return self.async_show_form(step_id='user',data_schema=vol.Schema({
            vol.Optional(CONF_HOST,default=''):str,vol.Required(CONF_PAIRING_KEY):selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional(CONF_CAMERA_SSID,default=''):str,
            vol.Optional(CONF_NAME,default='Avent local'):str}),errors=errors)

    async def async_step_reconfigure(self,user_input=None):
        entry=self._get_reconfigure_entry();errors={}
        if user_input is not None:
            try:
                host=normalize_host(user_input[CONF_HOST]);key_text=user_input.get(CONF_PAIRING_KEY) or entry.data[CONF_PAIRING_KEY]
                existing=self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN,host)
                if existing and existing.entry_id!=entry.entry_id:
                    return self.async_abort(reason='already_configured')
                ssid=entry.options.get(CONF_CAMERA_SSID,entry.data.get(CONF_CAMERA_SSID,''))
                if any(other.entry_id!=entry.entry_id and same_camera(other,host,ssid) for other in self._async_current_entries()):
                    return self.async_abort(reason='already_configured')
                key=parse_key(key_text)
                await self.hass.async_add_executor_job(probe,host,key)
            except (TimeoutError,OSError,EOFError):errors['base']='cannot_connect'
            except ValueError as exc:errors['base']=str(exc) if str(exc) in INPUT_ERRORS else 'invalid_auth'
            else:
                return self.async_update_reload_and_abort(entry,data_updates={CONF_HOST:host,CONF_PAIRING_KEY:key_text},unique_id=entry.unique_id or host)
        return self.async_show_form(step_id='reconfigure',data_schema=vol.Schema({
            vol.Required(CONF_HOST,default=entry.data[CONF_HOST]):str,
            vol.Optional(CONF_PAIRING_KEY):selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }),errors=errors)


class LocalBabyphoneOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self,user_input=None):
        entry=self.config_entry;errors={}
        if user_input is not None:
            try:ssid=normalize_ssid(user_input.get(CONF_CAMERA_SSID,''))
            except ValueError:errors[CONF_CAMERA_SSID]='invalid_camera_ssid'
            else:
                # No authentication/probe/reload: changing an identifier is local only.
                return self.async_create_entry(title='',data={**entry.options,CONF_CAMERA_SSID:ssid})
        return self.async_show_form(step_id='init',data_schema=vol.Schema({
            vol.Optional(CONF_CAMERA_SSID,default=entry.options.get(CONF_CAMERA_SSID,entry.data.get(CONF_CAMERA_SSID,''))):str,
        }),errors=errors)
