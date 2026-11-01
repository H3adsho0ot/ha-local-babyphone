"""Authenticated state/control for the bundled card; no local HTTP side channel."""
import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.auth.permissions.const import POLICY_READ,POLICY_CONTROL
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN


def _resolve(hass,connection,msg,policy):
    entity_id=msg['entity_id']
    if not connection.user.permissions.check_entity(entity_id,policy):
        connection.send_error(msg['id'],'unauthorized','No access to this camera')
        return None
    camera=hass.data[DOMAIN]['cameras'].get(entity_id)
    if camera is None:
        connection.send_error(msg['id'],'not_found','Not an Avent local camera')
        return None
    return camera.coordinator


@websocket_api.websocket_command({vol.Required('type'):'local_babyphone/subscribe',vol.Required('entity_id'):cv.entity_id})
@websocket_api.async_response
async def subscribe(hass,connection,msg):
    coordinator=_resolve(hass,connection,msg,POLICY_READ)
    if not coordinator:return
    @callback
    def update():connection.send_event(msg['id'],coordinator.data)
    connection.subscriptions[msg['id']]=coordinator.async_add_listener(update)
    connection.send_result(msg['id'])
    update()


@websocket_api.websocket_command({vol.Required('type'):'local_babyphone/control',vol.Required('entity_id'):cv.entity_id,vol.Required('kind'):str,vol.Required('values'):dict})
@websocket_api.async_response
async def control(hass,connection,msg):
    coordinator=_resolve(hass,connection,msg,POLICY_CONTROL)
    if not coordinator:return
    try:await coordinator.async_command(msg['kind'],msg['values'])
    except HomeAssistantError as exc:connection.send_error(msg['id'],'command_failed',str(exc));return
    connection.send_result(msg['id'],coordinator.data)


@websocket_api.websocket_command({vol.Required('type'):'local_babyphone/talk',vol.Required('entity_id'):cv.entity_id,vol.Required('session_id'):str,vol.Required('active'):bool})
@websocket_api.async_response
async def talk(hass,connection,msg):
    coordinator=_resolve(hass,connection,msg,POLICY_CONTROL)
    if not coordinator:return
    try:
        if msg['active']:await coordinator.media.start_talk(msg['session_id'])
        else:await coordinator.media.stop_talk(msg['session_id'])
    except (ValueError,OSError,ConnectionError,TimeoutError) as exc:connection.send_error(msg['id'],'talk_failed',str(exc));return
    connection.send_result(msg['id'])


@callback
def async_register(hass):
    for command in (subscribe,control,talk):websocket_api.async_register_command(hass,command)
