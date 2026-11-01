"""Validate commands shared by HA entities and the dashboard card."""
import asyncio
from .const import TIMERS
from .protocol.client import IDENTITY


def _choice(value, values):
    if type(value) is not int or value not in values:raise ValueError('Invalid setting value')
    return value


async def execute(client,kind,values):
    if not isinstance(values,dict) or not values:raise ValueError('Setting values are missing')
    if kind=='detection':
        allowed={'noise','noise_threshold'}
        if set(values)-allowed:raise ValueError('Unknown setting')
        for key,value in values.items():
            if key=='noise':
                if type(value) is not bool:raise ValueError('Expected a boolean value')
            else:_choice(value,range(1,101))
        for key,value in values.items():setattr(client,key+'_enabled' if key=='noise' else key,value)
        return
    if kind=='privacy':
        if set(values)!={'Privacy_switch'}:raise ValueError('Unknown privacy setting')
        value=_choice(values['Privacy_switch'],(0,1))
        # The native setter sends the entire stream-mode structure. Read it
        # first so a privacy toggle cannot overwrite another controller's mode.
        current=await asyncio.to_thread(client.request,2,IDENTITY)
        fields={'Stream_mode':range(3),'Stream_sensitive0':range(1,5),
            'Stream_sensitive1':range(1,5),'Stream_sensitive2':range(1,5),'Privacy_switch':(0,1)}
        if any(type(current.get(k)) is not int or current[k] not in allowed for k,allowed in fields.items()):
            raise ConnectionError('Camera did not report a complete privacy state')
        payload={k:current[k] for k in fields};payload['Privacy_switch']=value
        await asyncio.to_thread(client.request,3,payload)
        confirmed=await asyncio.to_thread(client.request,2,IDENTITY)
        if any(type(confirmed.get(k)) is not int or confirmed[k]!=v for k,v in payload.items()):
            raise ConnectionError('Camera did not confirm the complete privacy state')
        return
    if kind=='sensitivity':
        if set(values)!={'Stream_sensitive0'}:raise ValueError('Unknown sensitivity setting')
        value=_choice(values['Stream_sensitive0'],(1,2,3,4))
        payload={k:client.info[k] for k in ('Stream_mode','Stream_sensitive0','Stream_sensitive1','Stream_sensitive2','Privacy_switch')}
        payload['Stream_sensitive0']=value
        reply=await asyncio.to_thread(client.request,3,payload)
        if reply.get('Stream_sensitive0')!=value:raise ConnectionError('Not confirmed by camera')
        return
    schema={
        'light':(9,8,{'Nightlight_switch':(0,1),'Nightlight_bright':(35,70,100),'Nightlight_timer':tuple(TIMERS.values())}),
        'lullaby':(7,6,{'Lullaby_play':(0,1),'Lullaby_volume':tuple(range(30,101,10)),
            'Lullaby_timer':tuple(TIMERS.values()),'Lullaby_mode':(0,1),
            'Lullaby_select_num':range(int(client.info.get('Lullaby_Total',client.info.get('Lullaby_total',17))))}),
        'temperature':(11,10,{'Temp_alert':(0,1),'Temp_high':range(500,4001,100),'Temp_low':range(500,4001,100)}),
    }
    if kind not in schema:raise ValueError('Unknown command')
    opcode,query,fields=schema[kind]
    if set(values)-set(fields):raise ValueError('Unknown field')
    cleaned={k:_choice(v,fields[k]) for k,v in values.items()}
    if kind=='temperature':
        updated={**client.info,**cleaned}
        if updated.get('Temp_low',1600)>=updated.get('Temp_high',2000):raise ValueError('Lower limit must be below upper limit')
    await asyncio.to_thread(client.request,opcode,cleaned)
    await asyncio.to_thread(client.request,query)
