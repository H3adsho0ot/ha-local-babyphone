// Entirely synthetic: no camera, audio output, browser microphone or HA access.

import {readFile} from 'node:fs/promises';

import vm from 'node:vm';

import test from 'node:test';

import assert from 'node:assert/strict';



const bundle=await readFile(new URL('../custom_components/local_babyphone/frontend/local-babyphone-card.js',import.meta.url),'utf8');

const template=await readFile(new URL('../frontend-src/template.html',import.meta.url),'utf8');

const controlIds=[...template.matchAll(/<(?:button|input|select)\b[^>]*\bid="([^"]+)"/g)].map(match=>match[1]);

class Element extends EventTarget{

  constructor(){super();this.attrs={};this.classes=new Set();this.style={};this.img={src:''};this.options=[];this.disabled=false;this.muted=false;this.lastElementChild={};}

  getBoundingClientRect(){return {width:960,height:540};}

  focus(){}

  setPointerCapture(){}

  classList={add:name=>this.classes.add(name),remove:name=>this.classes.delete(name),toggle:(name,on)=>{if(on)this.classes.add(name);else this.classes.delete(name);}};

  setAttribute(k,v){this.attrs[k]=v;}

  getAttribute(k){return this.attrs[k];}

  removeAttribute(k){delete this.attrs[k];if(k==='href')delete this.href;}

  querySelector(){return this.img;}

  querySelectorAll(){return [];}

  replaceChildren(){this.options=[];}

  add(option){this.options.push(option);}

  append(){}

}

function environment(storage=new Map()){

  const registry=new Map(),window=new EventTarget(),document=new EventTarget();window.customCards=[];

  const media={getUserMedia:async()=>{throw Error('Unexpected microphone request');}};

  const context=vm.createContext({HTMLElement:class{},customElements:{get:n=>registry.get(n),define:(n,c)=>registry.set(n,c)},

    localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)},ResizeObserver:class{observe(){}disconnect(){}},localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)},ResizeObserver:class{observe(){}disconnect(){}},window,document,navigator:{mediaDevices:media},setTimeout,clearTimeout,Option:class{constructor(text,value){this.textContent=text;this.value=String(value);this.dataset={};}},console});

  vm.runInContext(bundle+'\nthis.pressAction=bindPressAction;',context);

  const card=Object.create(registry.get('local-babyphone-card').prototype),elements=new Map();

  Object.assign(card,{_generation:0,_press:0,_timers:new Set(),_releases:[],_talking:false,_talkStarting:false,

    _zoom:1,_zoomCenter:{x:.5,y:.5},_zoom:1,_zoomCenter:{x:.5,y:.5},_pending:false,_config:{entity:'camera.synthetic'},_state:{connected:true,settings:{},detection:{}},

    _session:'synthetic',_pc:{connectionState:'connected'},shadowRoot:{querySelectorAll:()=>[]}});

  card.$=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};

  const calls=[],tracks=[],notices=[];

  card._hass={language:'de',callWS:async value=>{calls.push(value);}};

  card._audio={sender:{replaceTrack:async track=>{tracks.push(track);}}};

  card._notice=(...args)=>notices.push(args);card._wireZoom=()=>{};

  return {context,card,elements,media,calls,tracks,notices,window,document};

}

function renderEnvironment(){

  const e=environment();

  e.document.createElement=()=>new Element();

  for(const id of controlIds)e.card.$(id).id=id;

  e.card.shadowRoot.querySelectorAll=selector=>selector==='button,input,select'?controlIds.map(id=>e.card.$(id)):[];

  e.card._hass.states={'camera.synthetic':{attributes:{entity_picture:'/synthetic.jpg'}}};

  e.card._hass.hassUrl=path=>path;e.card.$('video').readyState=3;

  const render=state=>{e.card._state=state;e.card._render(state);};

  return {...e,render};

}

function assertOffline(e){

  assert.ok(controlIds.length>15,'cover the actual template controls');

  for(const id of controlIds)assert.equal(e.card.$(id).disabled,id!=='dialog-close',id);

  assert.equal(e.card.$('snapshot').attrs['aria-disabled'],'true');

  assert.equal(e.card.$('snapshot').href,undefined);

  assert.equal(e.card.$('snapshot').tabIndex,-1);

}

const event=(type,properties={})=>Object.assign(new Event(type,{cancelable:true}),properties);

const tick=()=>new Promise(resolve=>setImmediate(resolve));



test('zoom and panning survive a new card; camera and HA user have separate preferences',()=>{

  const storage=new Map(),first=environment(storage);delete first.card._wireZoom;

  first.card._wireZoom();first.card.$('zoom-4').dispatchEvent(event('click'));

  first.card.$('video-stage').dispatchEvent(event('keydown',{key:'ArrowRight'}));

  const saved={...first.card._zoomCenter},second=environment(storage);

  second.card._restoreZoom();assert.equal(second.card._zoom,4);assert.deepEqual({...second.card._zoomCenter},saved);

  second.card._config.entity='camera.other';second.card._restoreZoom();assert.equal(second.card._zoom,1);

  second.card._config.entity='camera.synthetic';second.card._hass.user={id:'different'};second.card._restoreZoom();assert.equal(second.card._zoom,1);

  assert.deepEqual(first.calls,[]);assert.deepEqual(second.calls,[]);

});



test('drag completion persists the chosen image position and 1x resets it',()=>{

  const storage=new Map(),e=environment(storage);delete e.card._wireZoom;e.card._wireZoom();

  e.card.$('zoom-2').dispatchEvent(event('click'));

  const stage=e.card.$('video-stage');stage.dispatchEvent(event('pointerdown',{button:0,pointerId:1,clientX:400,clientY:200}));

  stage.dispatchEvent(event('pointermove',{pointerId:1,clientX:300,clientY:160}));stage.dispatchEvent(event('pointerup'));

  const restored=environment(storage);restored.card._restoreZoom();assert.equal(restored.card._zoom,2);assert.ok(restored.card._zoomCenter.x>.5);

  e.card.$('zoom-1').dispatchEvent(event('click'));restored.card._zoomLoadedKey=null;restored.card._restoreZoom();

  assert.equal(restored.card._zoom,1);assert.equal(restored.card._zoomCenter.x,.5);

});



test('corrupt, unsupported and inaccessible saved preferences leave zoom usable',()=>{

  for(const value of ['invalid',JSON.stringify({version:1,zoom:3,x:.5,y:.5}),JSON.stringify({version:1,zoom:4,x:2,y:.5})]){

    const storage=new Map(),e=environment(storage);storage.set(e.card._zoomStorageKey(),value);e.card._restoreZoom();assert.equal(e.card._zoom,1);

  }

  const e=environment();e.context.localStorage={getItem(){throw Error('blocked');},setItem(){throw Error('full');}};

  assert.doesNotThrow(()=>{e.card._restoreZoom();e.card._saveZoom();});

});



test('the card exposes no motion controls, meter or motion commands',()=>{

  assert.doesNotMatch(template,/motion-enabled|motion-threshold|video-activity/);

  const e=environment();e.card._wire();

  // The production command is noise-only (async render is stubbed in this fixture).

  assert.doesNotMatch(bundle,/motion:enabled|s\.motion_level/);

});



test('HA language controls text and numbers; missing and unsupported languages fall back to English',()=>{

  const {card}=environment();

  for(const [hass,label,number]of [[{},'Night light','20.1'],[{language:'fr'},'Night light','20.1'],[{language:'de-DE'},'Nachtlicht','20,1'],[{language:'en',locale:{language:'de'}},'Nachtlicht','20,1']]){

    card._hass=hass;assert.equal(card._t('light_settings'),label);assert.equal(card._formatTemperature(20.1),number);

  }

});



test('changing the language updates all native sound labels without changing the selected track',()=>{

  const e=renderEnvironment(),state={connected:true,settings:{Lullaby_mode:1,Lullaby_select_num:6,Lullaby_Total:17},events:[]};

  e.render(state);assert.equal(e.card.$('song').options[7].textContent,'Beruhigender Fluss');

  e.card.shadowRoot.activeElement=e.card.$('song');const selected=e.card.$('song').value;

  e.card._hass.language='en';e.render(state);

  assert.equal(e.card.$('song').options[7].textContent,'Calming River');

  assert.equal(e.card.$('song').options[6].textContent,'Mother’s shh');

  assert.equal(e.card.$('song').options[0].textContent,'All lullabies');

  assert.equal(e.card.$('song').value,selected);assert.deepEqual(e.calls,[]);

});



test('events and WebSocket errors follow the viewer language, including legacy German errors',()=>{

  const {card}=environment();

  assert.equal(card._eventText({kind:'sound',text:'legacy'}),'Geräusch erkannt · lokal');

  assert.equal(card._error({message:'Lower limit must be below upper limit'}),'Untergrenze muss unter der Obergrenze liegen');

  card._hass.language='en';

  assert.equal(card._eventText({kind:'sound',text:'legacy'}),'Sound detected · local');

  assert.equal(card._error({message:'Untergrenze muss unter der Obergrenze liegen'}),'Lower limit must be below upper limit');

  assert.equal(card._error({message:'Unknown browser diagnostic'}),'Unknown browser diagnostic');

});



test('all card translations and interpolations have matching English/German keys',async()=>{

  const catalogs=JSON.parse(await readFile(new URL('../frontend-src/translations.json',import.meta.url),'utf8'));

  assert.deepEqual(Object.keys(catalogs.en).sort(),Object.keys(catalogs.de).sort());

  for(const key of Object.keys(catalogs.en))assert.deepEqual([...catalogs.en[key].matchAll(/\{\w+\}/g)].map(m=>m[0]).sort(),[...catalogs.de[key].matchAll(/\{\w+\}/g)].map(m=>m[0]).sort(),key);

  for(const match of template.matchAll(/data-i18n(?:-[\w-]+)?="([^"]+)"/g))assert.ok(catalogs.en[match[1]],match[1]);

});



function gesture(){

  const env=environment(),target=new Element(),timers=new Map(),actions=[];let id=0;

  env.context.pressAction({target,listen:(t,type,fn)=>t.addEventListener(type,fn),

    schedule:fn=>{timers.set(++id,fn);return id;},cancel:key=>timers.delete(key),

    onTap:()=>actions.push('toggle'),onHold:()=>actions.push('settings')});

  const dispatch=(type,extra={})=>target.dispatchEvent(event(type,{button:0,pointerId:1,clientX:0,clientY:0,...extra}));

  return {actions,dispatch,hold:()=>{for(const fn of [...timers.values()])fn();timers.clear();},target};

}

test('short press toggles exactly once',()=>{

  const g=gesture();g.dispatch('pointerdown');g.dispatch('pointerup');g.dispatch('click');g.hold();

  assert.deepEqual(g.actions,['toggle']);

});

test('hold opens settings and suppresses the following click',()=>{

  const g=gesture();g.dispatch('pointerdown');g.hold();g.dispatch('pointerup');g.dispatch('click');

  assert.deepEqual(g.actions,['settings']);

  g.dispatch('pointerdown');g.dispatch('pointerup');g.dispatch('click');

  assert.deepEqual(g.actions,['settings','toggle']);

});

test('scrolling or pointer cancellation cannot toggle',()=>{

  for(const kind of ['pointermove','pointercancel']){

    const g=gesture();g.dispatch('pointerdown');g.dispatch(kind,{clientX:25});g.dispatch('pointerup');g.dispatch('click');g.hold();

    assert.deepEqual(g.actions,[]);

  }

});

test('keyboard settings shortcut and context menu never toggle',()=>{

  for(const [kind,extra]of [['keydown',{key:'Enter',shiftKey:true}],['contextmenu',{}]]){

    const g=gesture();g.dispatch(kind,extra);g.dispatch('click');assert.deepEqual(g.actions,['settings']);

  }

});

test('disabled feature cannot toggle or open settings',()=>{

  const g=gesture();g.target.disabled=true;g.dispatch('pointerdown');g.hold();g.dispatch('click');assert.deepEqual(g.actions,[]);

});

test('passive icon rendering never opens a microphone or sends commands',()=>{

  const e=environment();e.card._updateTalk();e.card._updateListen();assert.deepEqual(e.calls,[]);

  assert.equal(e.card.$('talk').attrs['aria-pressed'],'false');

});

test('a release after opening a held-press dialog cannot immediately dismiss it',()=>{

  const e=environment();e.card._wire();let closed=0;const dialog=e.card.$('settings-dialog');dialog.close=()=>closed++;

  dialog.dispatchEvent(event('click'));assert.equal(closed,0);

  dialog.dispatchEvent(event('pointerdown'));dialog.dispatchEvent(event('click'));assert.equal(closed,1);

  assert.deepEqual(e.calls,[]);

});

test('microphone is a click toggle; releasing a pointer does not stop it',async()=>{

  const e=environment();let stopped=0;const track={stop:()=>stopped++};

  e.media.getUserMedia=async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]});e.card._wire();

  e.card.$('talk').dispatchEvent(event('click'));await tick();assert.equal(e.card._talking,true);

  e.window.dispatchEvent(event('pointerup'));await tick();assert.equal(e.card._talking,true);

  assert.equal(e.card.$('talk').attrs['aria-pressed'],'true');assert.equal(e.card.$('video').muted,false);

  e.card.$('talk').dispatchEvent(event('click'));await tick();assert.equal(e.card._talking,false);

  assert.equal(e.card.$('video').muted,false);assert.ok(stopped>0);assert.deepEqual(e.calls.map(c=>c.active),[true,false]);

  assert.equal(e.tracks.at(-1),null);

});

test('leaving the page stops a toggled microphone',async()=>{

  const e=environment();const track={stop(){}};

  e.media.getUserMedia=async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]});e.card._wire();

  e.card.$('talk').dispatchEvent(event('click'));await tick();

  e.document.hidden=true;e.document.dispatchEvent(event('visibilitychange'));await tick();

  assert.equal(e.card._talking,false);assert.deepEqual(e.calls.map(c=>c.active),[true,false]);

});

test('cancelling a pending permission cannot start transmission later',async()=>{

  const e=environment();let grant,stopped=0;const track={stop:()=>stopped++};

  e.media.getUserMedia=()=>new Promise(resolve=>grant=resolve);

  const pending=e.card._startTalk(event('click'));assert.equal(e.card._talkStarting,true);

  await e.card._stopTalk();grant({getTracks:()=>[track],getAudioTracks:()=>[track]});await pending;

  assert.equal(stopped,1);assert.equal(e.card._talking,false);assert.deepEqual(e.calls,[]);assert.deepEqual(e.tracks,[]);

});

test('failed talk activation leaves microphone off and no track attached',async()=>{

  const e=environment();let stopped=0;const track={stop:()=>stopped++};

  e.media.getUserMedia=async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]});

  e.card._hass.callWS=async call=>{e.calls.push(call);if(call.active)throw Error('Synthetic failure');};

  await e.card._startTalk(event('click'));assert.equal(e.card._talking,false);assert.ok(stopped>0);

  assert.ok(e.tracks.every(track=>track===null));assert.equal(e.card.$('talk').attrs['aria-pressed'],'false');

});



test('hiding the page releases WebRTC but keeps the status subscription passive',async()=>{

  const e=environment();let closed=0,released=0,statusReleased=0;

  e.card._pc.close=()=>closed++;

  e.card._offerSubscription=()=>released++;

  e.card._subscription=()=>statusReleased++;

  e.card.$('video').srcObject={};e.card._wire();

  e.document.hidden=true;e.document.dispatchEvent(event('visibilitychange'));await tick();

  assert.equal(closed,1);assert.equal(released,1);assert.equal(statusReleased,0);

  assert.equal(e.card._pc,null);assert.equal(e.card.$('video').srcObject,null);

  assert.equal(e.card._mediaPaused,true);assert.deepEqual(e.calls,[]);

});



test('returning to a visible page requests media again without camera controls',()=>{

  const e=environment();e.card._subscription=()=>{};e.card._mediaPaused=true;

  const retries=[];e.card._retryMedia=(...args)=>retries.push(args);

  e.document.hidden=false;e.card._visibilityChanged();

  assert.equal(e.card._mediaPaused,false);assert.equal(retries.length,1);

  assert.equal(retries[0][1],0);assert.deepEqual(e.calls,[]);

});



test('a hidden page cannot begin or retry a camera offer',async()=>{

  const e=environment();e.document.hidden=true;

  e.card.isConnected=true;

  await e.card._begin();await e.card._connectMedia();e.card._retryMedia();

  assert.equal(e.card._timers.size,0);assert.deepEqual(e.calls,[]);

});



test('all camera controls start disabled before the first camera state',()=>{

  const e=renderEnvironment();e.card._state=null;e.card._wire();assertOffline(e);

  assert.deepEqual(e.calls,[]);

});



test('offline state disables every toolbar, zoom and settings control including snapshot',()=>{

  const e=renderEnvironment();

  e.render({connected:false,video_live:false,settings:{},detection:{noise:true,motion:true}});

  assertOffline(e);assert.deepEqual(e.calls,[]);

});



test('connection loss cannot re-enable stale controls or request microphone capture',async()=>{

  const e=renderEnvironment();let captures=0;

  e.media.getUserMedia=async()=>{captures++;throw Error('must not capture');};

  e.render({...e.card._state,video_live:true});

  assert.equal(e.card.$('snapshot').attrs['aria-disabled'],'false');

  e.card._unavailable('synthetic disconnect');

  e.card._updateTalk();e.card._updateListen();e.card._render(e.card._state);

  assertOffline(e);

  await e.card._control('light',{Nightlight_switch:1});

  await e.card._startTalk(event('click'));

  assert.equal(captures,0);assert.deepEqual(e.calls,[]);

});



test('fresh connected status restores normal controls while microphone requirements still apply',async()=>{

  const e=renderEnvironment();e.card._unavailable('synthetic disconnect');

  e.media.getUserMedia=undefined;

  e.card._hass.connection={subscribeMessage:async callback=>{

    callback({connected:true,video_live:true,settings:{},detection:{}});return()=>{};

  }};

  e.card._connectMedia=async()=>{};

  await e.card._begin();

  for(const id of ['quick-light','quick-detection','quick-events','fullscreen','zoom-2','noise-threshold'])assert.equal(e.card.$(id).disabled,false,id);

  assert.equal(e.card.$('talk').disabled,true,'no microphone API');

  assert.equal(e.card.$('snapshot').attrs['aria-disabled'],'false');

  assert.equal(e.card.$('snapshot').tabIndex,0);assert.deepEqual(e.calls,[]);

});



test('unknown, stale and disconnected temperatures show a dash; fresh zero is a real value',()=>{

  const e=renderEnvironment();

  for(const [connected,value,fresh,expected]of [

    [true,20.1,true,'20,1 °C'],[true,0,true,'0,0 °C'],

    [true,null,false,'– °C'],[true,20.1,false,'– °C'],[false,20.1,true,'– °C'],

  ]){

    e.render({connected,temperature:{fresh},settings:{temperature:value},detection:{}});

    assert.equal(e.card.$('handheld-temperature').textContent,expected);

    if(expected==='– °C')assert.equal(e.card.$('temperature-status').textContent,'Temperatur nicht verfügbar');

  }

  e.render({connected:true,temperature:{fresh:true},settings:{temperature:20.1},detection:{}});

  e.card._unavailable('synthetic disconnect');

  assert.equal(e.card.$('handheld-temperature').textContent,'– °C');

});



test('listening first and then starting the microphone preserves camera audio',async()=>{

  const e=environment();const track={stop(){}};

  e.card.$('video').muted=true;e.card.$('video').play=async()=>{};

  e.media.getUserMedia=async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]});

  e.card._wire();e.card._updateListen();

  e.card.$('listen').dispatchEvent(event('click'));await tick();

  assert.equal(e.card.$('video').muted,false);

  e.card.$('talk').dispatchEvent(event('click'));await tick();

  assert.equal(e.card._talking,true);assert.equal(e.card.$('video').muted,false);

  assert.equal(e.card.$('listen').disabled,false);

  assert.equal(e.card.$('listen').attrs['aria-pressed'],'true');

  assert.deepEqual(e.notices,[]);assert.equal(e.tracks.at(-1),track);

  await e.card._stopTalk();assert.equal(e.card.$('video').muted,false);

});



test('listening can be toggled during speech and its setting survives stopping',async()=>{

  const e=environment();const track={stop(){}};

  e.card.$('video').muted=true;e.card.$('video').play=async()=>{};

  e.media.getUserMedia=async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]});e.card._wire();

  await e.card._startTalk(event('click'));

  assert.equal(e.card.$('video').muted,true,'speech must not enable listening');

  assert.equal(e.card.$('listen').disabled,false);

  e.card.$('listen').dispatchEvent(event('click'));await tick();

  assert.equal(e.card.$('video').muted,false);

  await e.card._stopTalk();assert.equal(e.card.$('video').muted,false);

});



test('permission rejection preserves listening and reports the actual browser error',async()=>{

  const e=environment();e.card.$('video').muted=false;

  e.media.getUserMedia=async()=>{const error=Error('Permission denied');error.name='NotAllowedError';throw error;};

  await e.card._startTalk(event('click'));

  assert.equal(e.card.$('video').muted,false);assert.equal(e.card._talking,false);

  assert.ok(e.notices.at(-1)[0].includes('NotAllowedError'));

  assert.ok(e.calls.every(call=>!call.active));

});



test('missing sender cannot activate talkback or mask the useful error during cleanup',async()=>{

  const e=environment();e.card._audio={};e.card.$('video').muted=false;

  await e.card._startTalk(event('click'));

  assert.equal(e.card.$('video').muted,false);assert.equal(e.card._talking,false);

  assert.ok(e.notices.at(-1)[0].includes('Sprechkanal nicht bereit'));

  assert.ok(e.calls.every(call=>!call.active));

});



test('sender failure stops microphone and talkback without changing listening',async()=>{

  const e=environment();let stopped=0;const track={stop(){stopped++;}};

  e.card.$('video').muted=false;

  e.media.getUserMedia=async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]});

  e.card._audio.sender.replaceTrack=()=>{const error=Error('Synthetic sender failed');error.name='InvalidStateError';throw error;};

  await e.card._startTalk(event('click'));

  assert.equal(e.card.$('video').muted,false);assert.ok(stopped>0);

  assert.equal(e.card._talking,false);assert.deepEqual(e.calls.map(call=>call.active),[true,false]);

  assert.ok(e.notices.at(-1)[0].includes('InvalidStateError'));

});



test('another start cannot overtake pending microphone cleanup',async()=>{

  const e=environment();let release,captures=0;const track={stop(){}};

  e.media.getUserMedia=async()=>{captures++;return {getTracks:()=>[track],getAudioTracks:()=>[track]};};

  await e.card._startTalk(event('click'));

  e.card._audio.sender.replaceTrack=async()=>new Promise(resolve=>release=resolve);

  const stopping=e.card._stopTalk();

  await e.card._startTalk(event('click'));assert.equal(captures,1);

  release();await stopping;

  assert.equal(e.card._talking,false);assert.equal(e.card._talkStopPromise,null);

});

