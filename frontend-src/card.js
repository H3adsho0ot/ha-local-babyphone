const TIMERS=[0,300,600,1200,1800,3600,5400];
class LocalBabyphoneCard extends HTMLElement {
  static getConfigElement(){return document.createElement('local-babyphone-card-editor');}
  static getStubConfig(hass){return {entity:Object.entries(hass.states).find(([id,s])=>id.startsWith('camera.')&&s.attributes.local_babyphone)?.[0]||''};}
  getCardSize(){return 10;}
  getGridOptions(){return {columns:12,min_columns:6,rows:'auto'};}
  constructor(){super();this.attachShadow({mode:'open'});this._generation=0;this._press=0;this._renderedAt=0;this._talking=false;this._talkStarting=false;this._pending=false;this._timers=new Set();this._releases=[];this._zoom=1;this._zoomCenter={x:.5,y:.5};}
  setConfig(config){
    if(!config.entity?.startsWith('camera.'))throw new Error(this._t('invalid_camera'));
    if(this._config?.entity===config.entity){this._config={...config};return;}
    this._cleanup();this._zoom=1;this._zoomCenter={x:.5,y:.5};this._config={...config};this.shadowRoot.innerHTML=`<style>${CARD_CSS}</style><ha-card>${CARD_HTML}<div id="notice" role="status" aria-live="polite" hidden></div></ha-card>`;
    this._restoreZoom();this._wire();this._localize();if(this.isConnected&&this._hass)this._begin();
  }
  set hass(hass){this._hass=hass;if(this._config)this._restoreZoom();if(this._renderedLanguage!==this._language()&&this._config)this._localize();if(this.isConnected&&this._config&&!this._subscription&&!this._starting)this._begin();}
  connectedCallback(){if(this._config&&!this._wired)this._wire();if(this._hass&&this._config)this._begin();}
  disconnectedCallback(){this._cleanup();}
  _language(){return cardLanguage(this._hass);}
  _locale(){return cardLocale(this._hass);}
  _error(error,fallback='connection_failed'){return cardError(this._hass,error,fallback);}
  _t(key,values){return cardText(this._hass,key,values);}
  _formatTemperature(value){return value.toLocaleString(this._locale(),{minimumFractionDigits:1,maximumFractionDigits:1});}
  _eventText(event){return CARD_TRANSLATIONS.en['event_'+event.kind]?this._t('event_'+event.kind):event.text;}
  _localize(){
    if(!this.$('video'))return;
    this._renderedLanguage=this._language();
    this.setAttribute('lang',this._language());
    for(const element of this.shadowRoot.querySelectorAll('[data-i18n]'))element.textContent=this._t(element.dataset.i18n);
    for(const attr of ['aria-label','title','aria-valuetext'])for(const element of this.shadowRoot.querySelectorAll('[data-i18n-'+attr+']'))element.setAttribute(attr,this._t(element.getAttribute('data-i18n-'+attr)));
    for(const id of ['light-timer','song-timer'])for(const option of this.$(id).options)if(!option.dataset?.remaining)option.textContent=Number(option.value)?this._t('minutes',{minutes:Number(option.value)/60}):this._t('no_timer');
    if(this._settingsPanel)this.$('settings-title').textContent=this._t(this._settingsPanel+'_settings');
    this._applyZoom();
    if(this._state)this._render(this._state);else {this._updateTalk();this._updateListen();this._disableControls();}
  }
  $(id){return this.shadowRoot.getElementById(id);}
  _timer(fn,ms){const timer=setTimeout(()=>{this._timers.delete(timer);fn();},ms);this._timers.add(timer);return timer;}
  _notice(text,error=false){const n=this.$('notice');if(!n)return;n.textContent=text;n.classList.toggle('error',error);n.hidden=false;this._timer(()=>{if(n.isConnected)n.hidden=true;},6500);}
  _listen(target,type,handler,options){target.addEventListener(type,handler,options);this._releases.push(()=>target.removeEventListener(type,handler,options));}
  _cancelTimer(timer){clearTimeout(timer);this._timers.delete(timer);}
  _canControl(){return Boolean(this._state?.connected&&!this._connectionLost&&!this._mediaPaused);}
  _disableControls(){
    for(const el of this.shadowRoot.querySelectorAll('button,input,select'))el.disabled=el.id!=='dialog-close';
    const snapshot=this.$('snapshot');snapshot.setAttribute('aria-disabled','true');snapshot.removeAttribute('href');snapshot.tabIndex=-1;
    this.$('handheld-temperature').textContent='– °C';this.$('temperature-status').textContent=this._t('temperature_unavailable');
  }
  _openSettings(name){
    if(!this._canControl())return;
    const titles={audio:this._t('audio_settings'),light:this._t('light_settings'),lullaby:this._t('lullaby_settings'),temperature:this._t('temperature_settings'),detection:this._t('detection_settings'),events:this._t('events_settings')};
    if(!titles[name])return;
    for(const panel of this.shadowRoot.querySelectorAll('.dialog-body > section'))panel.hidden=panel.id!=='panel-'+name;
    this._settingsPanel=name;this.$('settings-title').textContent=titles[name];
    if(!this.$('settings-dialog').open){this._dialogBackdropPress=false;this.$('settings-dialog').showModal();}
  }
  _pressAction(id,onTap,panel){
    this._releases.push(bindPressAction({target:this.$(id),listen:(...args)=>this._listen(...args),
      schedule:(fn,ms)=>this._timer(fn,ms),cancel:timer=>this._cancelTimer(timer),onTap,onHold:()=>this._openSettings(panel)}));
  }
  _featureState(name,enabled,label){
    const button=this.$('quick-'+name);button.classList.toggle('active',enabled);button.setAttribute('aria-pressed',String(enabled));
    button.setAttribute('aria-label',label);button.title=label+this._t('hold_settings');
  }
  _wire(){
    this._wired=true;
    this._wireZoom();
    for(const img of this.shadowRoot.querySelectorAll('img[data-icon]'))img.src=ICONS[img.dataset.icon];
    this._listen(this.$('dialog-close'),'click',()=>this.$('settings-dialog').close());
    this._listen(this.$('settings-dialog'),'pointerdown',event=>{this._dialogBackdropPress=event.target===this.$('settings-dialog');});
    this._listen(this.$('settings-dialog'),'click',event=>{
      if(event.target===this.$('settings-dialog')&&this._dialogBackdropPress)this.$('settings-dialog').close();
      this._dialogBackdropPress=false;
    });
    for(const id of ['light-timer','song-timer']){this.$(id).replaceChildren();for(const value of TIMERS)this.$(id).add(new Option(value?this._t('minutes',{minutes:value/60}):this._t('no_timer'),value));}
    const bind=(id,type,fn)=>this._listen(this.$(id),type,fn);
    this._pressAction('listen',async()=>{const video=this.$('video');video.muted=!video.muted;try{await video.play();}catch(e){this._notice(this._error(e),true);}this._updateListen();},'audio');
    this._pressAction('quick-light',()=>this._control('light',{Nightlight_switch:this._state.settings.Nightlight_switch?0:1}),'light');
    this._pressAction('quick-lullaby',()=>this._control('lullaby',{Lullaby_play:this._state.settings.Lullaby_play?0:1}),'lullaby');
    this._pressAction('quick-temperature',()=>this._control('temperature',{Temp_alert:this._state.settings.Temp_alert?0:1}),'temperature');
    this._pressAction('quick-detection',()=>{const enabled=!this._state.detection?.noise;this._control('detection',{noise:enabled});},'detection');
    this._pressAction('quick-events',()=>this._openSettings('events'),'events');
    bind('talk','click',event=>this._talking?this._stopTalk():this._startTalk(event));
    this._listen(window,'blur',()=>this._stopTalk());

    bind('brightness','change',e=>this._control('light',{Nightlight_bright:[35,70,100][Number(e.target.value)]}));
    bind('light-timer','change',e=>this._control('light',{Nightlight_timer:Number(e.target.value)}));
    bind('camera-sensitivity','change',e=>this._control('sensitivity',{Stream_sensitive0:Number(e.target.value)}));
    bind('song-play','click',()=>this._control('lullaby',{Lullaby_play:this._state.settings.Lullaby_play?0:1}));
    bind('song','change',e=>this._control('lullaby',e.target.value==='all'?{Lullaby_mode:0}:{Lullaby_mode:1,Lullaby_select_num:Number(e.target.value)}));
    bind('song-volume','change',e=>this._control('lullaby',{Lullaby_volume:Number(e.target.value)}));
    bind('song-timer','change',e=>this._control('lullaby',{Lullaby_timer:Number(e.target.value)}));
    for(const [id,key]of [['temp-low','Temp_low'],['temp-high','Temp_high']])bind(id,'change',e=>this._control('temperature',{[key]:Number(e.target.value)*100}));
    for(const kind of ['noise']){bind(kind+'-enabled','change',e=>this._control('detection',{[kind]:e.target.checked}));bind(kind+'-threshold','input',e=>this.$(kind+'-threshold-value').textContent=e.target.value+' %');bind(kind+'-threshold','change',e=>this._control('detection',{[kind+'_threshold']:Number(e.target.value)}));}
    this._listen(document,'visibilitychange',()=>this._visibilityChanged());
    this._listen(window,'pagehide',()=>this._pauseMedia());
    this._listen(window,'pageshow',()=>this._visibilityChanged());
    bind('fullscreen','click',()=>{const wrap=this.$('video-stage').closest('.viewfinder');if(wrap.requestFullscreen)wrap.requestFullscreen().catch(e=>this._notice(this._error(e),true));else this.$('video').webkitEnterFullscreen?.();});
    bind('snapshot','click',e=>{if(!this.$('snapshot').href||this.$('snapshot').getAttribute('aria-disabled')==='true')e.preventDefault();});
    const v=this.$('video');
    if(v.requestVideoFrameCallback){const rendered=()=>{this._renderedAt=Date.now();if(v.isConnected)this._frameCallback=v.requestVideoFrameCallback(rendered);};this._frameCallback=v.requestVideoFrameCallback(rendered);}
    this._disableControls();
  }
  _wireZoom(){
    const stage=this.$('video-stage');
    for(const z of [1,2,4])this._listen(this.$('zoom-'+z),'click',()=>{this._zoom=z;if(z===1)this._zoomCenter={x:.5,y:.5};this._applyZoom();this._saveZoom();});
    this._listen(stage,'pointerdown',e=>{if(this._zoom===1||e.button!==0)return;e.preventDefault();stage.focus({preventScroll:true});stage.setPointerCapture(e.pointerId);this._zoomDrag={id:e.pointerId,x:e.clientX,y:e.clientY,center:{...this._zoomCenter}};stage.classList.add('dragging');});
    this._listen(stage,'pointermove',e=>{const drag=this._zoomDrag;if(!drag||e.pointerId!==drag.id)return;const g=this._zoomGeometry();this._zoomCenter={x:drag.center.x-(e.clientX-drag.x)/(g.imageWidth*this._zoom),y:drag.center.y-(e.clientY-drag.y)/(g.imageHeight*this._zoom)};this._applyZoom();});
    const end=()=>{if(this._zoomDrag)this._saveZoom();this._zoomDrag=null;stage.classList.remove('dragging');};
    for(const kind of ['pointerup','pointercancel','lostpointercapture'])this._listen(stage,kind,end);
    this._listen(stage,'keydown',e=>{if(this._zoom===1||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(e.key))return;e.preventDefault();const g=this._zoomGeometry();if(e.key==='Home')this._zoomCenter={x:.5,y:.5};else{const axis=['ArrowLeft','ArrowRight'].includes(e.key)?'x':'y';const direction=['ArrowRight','ArrowDown'].includes(e.key)?1:-1;this._zoomCenter[axis]+=direction*.1*(axis==='x'?g.width/g.imageWidth:g.height/g.imageHeight)/this._zoom;}this._applyZoom();this._saveZoom();});
    this._listen(this.$('video'),'loadedmetadata',()=>this._applyZoom());
    const resize=new ResizeObserver(()=>this._applyZoom());resize.observe(stage);this._releases.push(()=>resize.disconnect());
    this._applyZoom();
  }
  _zoomStorageKey(){return this._config&&this._hass?`avent-local:view:v1:${this._hass.user?.id||'default'}:${this._config.entity}`:null;}
  _restoreZoom(){
    const key=this._zoomStorageKey();if(!key||key===this._zoomLoadedKey)return;
    this._zoomLoadedKey=key;this._zoom=1;this._zoomCenter={x:.5,y:.5};
    try{const saved=JSON.parse(localStorage.getItem(key));
      if(saved?.version===1&&[1,2,4].includes(saved.zoom)&&Number.isFinite(saved.x)&&Number.isFinite(saved.y)&&saved.x>=0&&saved.x<=1&&saved.y>=0&&saved.y<=1){this._zoom=saved.zoom;this._zoomCenter=saved.zoom===1?{x:.5,y:.5}:{x:saved.x,y:saved.y};}
    }catch(_e){}this._applyZoom();
  }
  _saveZoom(){
    const key=this._zoomStorageKey();if(!key)return;
    try{localStorage.setItem(key,JSON.stringify({version:1,zoom:this._zoom,...this._zoomCenter}));}catch(_e){}
  }
  _zoomGeometry(){const rect=this.$('video-stage').getBoundingClientRect(),video=this.$('video');const ratio=video.videoWidth&&video.videoHeight?video.videoWidth/video.videoHeight:16/9;const imageWidth=Math.min(rect.width,rect.height*ratio)||1;return {width:rect.width,height:rect.height,imageWidth,imageHeight:imageWidth/ratio};}
  _applyZoom(){
    if(!this.$('video-stage'))return;const g=this._zoomGeometry(),z=this._zoom;
    for(const [axis,viewport,image]of [['x',g.width,g.imageWidth],['y',g.height,g.imageHeight]]){const margin=Math.min(.5,viewport/(2*image*z));this._zoomCenter[axis]=Math.max(margin,Math.min(1-margin,this._zoomCenter[axis]));}
    const x=(.5-this._zoomCenter.x)*g.imageWidth*z,y=(.5-this._zoomCenter.y)*g.imageHeight*z;
    this.$('video').style.transform=`translate(${x}px,${y}px) scale(${z})`;
    this.$('video-stage').classList.toggle('zoomed',z>1);this.$('video-stage').setAttribute('aria-label',z===1?this._t('camera_view'):this._t('zoomed_view',{zoom:z}));
    for(const n of [1,2,4])this.$('zoom-'+n).setAttribute('aria-pressed',String(z===n));
    this.$('zoom-hint').hidden=z===1;
  }
  _activity(kind,value,available){
    const meter=this.$(kind+'-activity'),known=Boolean(available)&&Number.isFinite(value);
    const level=known?Math.ceil(Math.max(0,Math.min(100,value))/20):0;
    const label=this._t('audio');
    for(const led of meter.querySelectorAll('.activity-led'))led.classList.toggle('on',known&&Number(led.dataset.level)<=level);
    meter.classList.toggle('unavailable',!known);meter.setAttribute('aria-valuenow',String(level));
    const text=known?this._t('activity_level',{label,level}):this._t('activity_stale',{label});
    meter.setAttribute('aria-valuetext',text);meter.title=text;
  }
  _remaining(id,timer,connected){
    const el=this.$(id);el.classList.toggle('running',Boolean(timer?.active&&timer?.configured));
    if(!connected)el.textContent=this._t('remaining_unavailable');
    else if(!timer?.active)el.textContent=id==='light-remaining'?this._t('night_light_off'):this._t('playback_stopped');
    else if(!timer.configured)el.textContent=this._t('no_timer');
    else if(Number.isFinite(timer.remaining)&&timer.fresh){const seconds=Math.max(0,timer.remaining);el.textContent=this._t('remaining',{time:`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`});}
    else el.textContent=timer?.age===null||timer?.age===undefined?this._t('remaining_loading'):this._t('remaining_stale');
  }
  async _begin(){
    if(document.hidden||this._starting||this._subscription||!this._config||!this._hass)return;
    this._starting=true;const generation=this._generation;
    const connection=this._hass.connection;
    if(connection.addEventListener&&this._listenedConnection!==connection){
      this._listenedConnection=connection;
      this._listen(connection,'disconnected',()=>{this._stopTalk();this._unavailable(this._t('ha_disconnected'));});
      this._listen(connection,'ready',()=>{if(this._subscription&&this.isConnected)this._retryMedia(this._generation,0);});
    }
    try{
      const unsubscribe=await this._hass.connection.subscribeMessage(s=>{if(generation===this._generation){this._connectionLost=false;this._state=s;this._render(s);}}, {type:'local_babyphone/subscribe',entity_id:this._config.entity});
      if(generation!==this._generation){unsubscribe();return;}this._subscription=unsubscribe;
      await this._connectMedia(generation);
    }catch(e){this._unavailable(this._error(e,'not_configured'));this._notice(this._error(e,'connection_failed'),true);if(this._subscription)this._retryMedia(generation,5000);else this._timer(()=>{if(generation===this._generation){this._starting=false;this._begin();}},5000);}
    finally{if(generation===this._generation)this._starting=false;}
  }
  _retryMedia(generation=this._generation,delay=3000){
    if(document.hidden||this._mediaPaused||this._mediaRetry||generation!==this._generation||!this.isConnected)return;
    this._mediaRetry=this._timer(async()=>{this._mediaRetry=null;if(generation!==this._generation)return;try{await this._connectMedia(generation);}catch(e){this._unavailable(this._error(e,'connection_failed'));this._retryMedia(generation,5000);}},delay);
  }
  async _connectMedia(generation=this._generation){
    if(document.hidden||this._mediaPaused||generation!==this._generation||!this.isConnected)return;
    if(this._talking||this._talkStarting||this._mic)await this._stopTalk();
    const old=this._offerSubscription;this._offerSubscription=null;if(old)try{await old();}catch(_e){}
    if(this._pc){this._pc.onconnectionstatechange=null;this._pc.close();}
    this._session=null;this._renderedAt=0;
    const pc=new RTCPeerConnection({iceServers:[]});this._pc=pc;
    pc.addTransceiver('video',{direction:'recvonly'});this._audio=pc.addTransceiver('audio',{direction:'sendrecv'});
    const stream=new MediaStream();const video=this.$('video');video.srcObject=stream;
    pc.ontrack=e=>{stream.addTrack(e.track);video.play().catch(()=>{});};
    pc.onconnectionstatechange=()=>{if(pc!==this._pc)return;if(this._state)this._render(this._state);if(['failed','disconnected'].includes(pc.connectionState)){this._stopTalk();this._retryMedia(generation);}};
    await pc.setLocalDescription(await pc.createOffer());
    if(pc.iceGatheringState!=='complete')await new Promise(resolve=>{const t=setTimeout(resolve,3000);pc.addEventListener('icegatheringstatechange',()=>{if(pc.iceGatheringState==='complete'){clearTimeout(t);resolve();}});});
    if(document.hidden||this._mediaPaused||generation!==this._generation||pc!==this._pc)return;
    const unsubscribe=await this._hass.connection.subscribeMessage(event=>{
      if(generation!==this._generation||pc!==this._pc)return;
      if(event.type==='session')this._session=event.session_id;
      else if(event.type==='answer')pc.setRemoteDescription({type:'answer',sdp:event.answer}).catch(e=>{this._unavailable(this._error(e));this._retryMedia(generation);});
      else if(event.type==='candidate')pc.addIceCandidate(event.candidate).catch(e=>this._notice(this._error(e),true));
      else if(event.type==='error'){this._unavailable(this._error(event,'webrtc_failed'));this._retryMedia(generation,5000);}
    },{type:'camera/webrtc/offer',entity_id:this._config.entity,offer:pc.localDescription.sdp});
    if(document.hidden||this._mediaPaused||generation!==this._generation||pc!==this._pc){unsubscribe();return;}this._offerSubscription=unsubscribe;
  }
  _visibilityChanged(){
    if(document.hidden){this._pauseMedia();return;}
    this._mediaPaused=false;
    if(this._subscription)this._retryMedia(this._generation,0);else this._begin();
  }
  _pauseMedia(){
    if(this._zoomDrag)this._saveZoom();
    this._mediaPaused=true;this._stopTalk();
    if(this._mediaRetry){this._cancelTimer(this._mediaRetry);this._mediaRetry=null;}
    if(this._pc){this._pc.onconnectionstatechange=null;this._pc.close?.();this._pc=null;}
    const unsubscribe=this._offerSubscription;this._offerSubscription=null;
    if(unsubscribe)Promise.resolve(unsubscribe()).catch(()=>{});
    this._session=null;this._renderedAt=0;
    const video=this.$('video');if(video)video.srcObject=null;
    this._disableControls();
  }
  async _control(kind,values){if(this._pending||!this._canControl())return;this._pending=true;if(this._state)this._render(this._state);try{const state=await this._hass.callWS({type:'local_babyphone/control',entity_id:this._config.entity,kind,values});if(state){this._state=state;this._render(state);}}catch(e){this._notice(this._error(e,'command_failed'),true);}finally{this._pending=false;if(this._state)this._render(this._state);}}
  _setValue(id,value){const el=this.$(id);if(value!==undefined&&value!==null&&this.shadowRoot.activeElement!==el)el.value=value;}
  _timerValue(id,value){const select=this.$(id);if(value===undefined||this.shadowRoot.activeElement===select)return;for(const o of select.querySelectorAll('[data-remaining]'))o.remove();if(!TIMERS.includes(value)){const o=new Option(this._t('timer_remaining',{time:`${Math.floor(value/60)}:${String(value%60).padStart(2,'0')}`}),value);o.disabled=true;o.dataset.remaining='true';select.add(o);}select.value=value;}
  _wifi(state){
    const rssi=state.wifi?.rssi,age=state.wifi?.age;
    const known=Number.isFinite(rssi)&&rssi<0,fresh=state.connected&&Number.isFinite(age)&&age<30&&known;
    const bars=fresh?(rssi>=-60?4:rssi>=-65?3:rssi>=-70?2:rssi>=-80?1:0):0;
    const detail=!state.connected?this._t('wifi_disconnected'):fresh?this._t('wifi_bars',{bars}):this._t('wifi_stale');
    this.$('wifi-reception').src=RECEPTION[bars];this.$('wifi-status').classList.toggle('stale',!fresh);
    this.$('wifi-status').title=detail;this.$('wifi-status').setAttribute('aria-label',detail);
  }
  _render(s){
    if(!this._config)return;const x=s.settings||{};const video=this.$('video');
    const live=s.video_live&&this._pc?.connectionState==='connected'&&(video.requestVideoFrameCallback?Date.now()-this._renderedAt<5000:video.readyState>=2);
    this.$('video-placeholder').style.display=live?'none':'flex';
    if(!live)this.$('video-placeholder').lastElementChild.textContent=this._mediaPaused?this._t('view_paused'):s.demand?.mode==='idle'?this._t('requesting_view'):s.connected?this._t('connecting_view'):this._t('camera_retry');
    const temperature=this._canControl()&&s.temperature?.fresh!==false&&Number.isFinite(x.temperature)?x.temperature:null;
    this.$('handheld-temperature').textContent=temperature!==null?this._formatTemperature(temperature)+' °C':'– °C';
    this._wifi(s);
    for(const id of ['quick-light','quick-lullaby','quick-temperature','brightness','light-timer','song','song-play','song-volume','song-timer','temp-low','temp-high','camera-sensitivity'])this.$(id).disabled=!s.connected||this._pending;
    const connected=this._pc?.connectionState==='connected'&&s.connected;
    this._updateListen();this._updateTalk();
    this._featureState('light',Boolean(x.Nightlight_switch),x.Nightlight_switch?this._t('light_off'):this._t('light_on'));
    this._featureState('lullaby',Boolean(x.Lullaby_play),x.Lullaby_play?this._t('sounds_stop'):this._t('sounds_play'));
    this._featureState('temperature',Boolean(x.Temp_alert),x.Temp_alert?this._t('temperature_off'):this._t('temperature_on'));
    const detection=Boolean(s.detection?.noise);
    this._featureState('detection',detection,detection?this._t('detection_off'):this._t('detection_on'));
    for(const id of ['quick-detection','noise-enabled','noise-threshold'])this.$(id).disabled=this._pending;
    for(const id of ['zoom-1','zoom-2','zoom-4','fullscreen'])this.$(id).disabled=!live;
    this.$('quick-events').disabled=false;this.$('dialog-close').disabled=false;
    this._setValue('camera-sensitivity',x.Stream_sensitive0);
    this._setValue('brightness',[35,70,100].indexOf(x.Nightlight_bright));this.$('brightness-value').textContent=(x.Nightlight_bright??'–')+' %';this._timerValue('light-timer',x.Nightlight_timer);
    this._remaining('light-remaining',s.timers?.light,s.connected);this._remaining('song-remaining',s.timers?.lullaby,s.connected);
    const count=x.Lullaby_Total||x.Lullaby_total||17;
    if(this._songLanguage!==this._language()||this.$('song').options.length!==count+1||this.$('song').options[0]?.value!=='all'){const selected=this.$('song').value;this._songLanguage=this._language();this.$('song').replaceChildren();this.$('song').add(new Option(this._t('all_lullabies'),'all'));for(let i=0;i<count;i++)this.$('song').add(new Option(SOUND_TITLES[this._language()][i]||this._t('sound_number',{number:i+1}),i));this.$('song').value=selected;}
    this._setValue('song',x.Lullaby_mode===0?'all':x.Lullaby_select_num);this._setValue('song-volume',x.Lullaby_volume);this.$('volume-value').textContent=(x.Lullaby_volume??'–')+' %';this._timerValue('song-timer',x.Lullaby_timer);this.$('song-play').textContent='';this.$('song-play').style.backgroundImage=`url("${ICONS[x.Lullaby_play?'stop':'play']}")`;this.$('song-play').setAttribute('aria-label',x.Lullaby_play?this._t('sound_stop'):this._t('sound_play'));
    this._setValue('temp-low',x.Temp_low/100);this._setValue('temp-high',x.Temp_high/100);this.$('temperature-status').textContent=x.Temp_alert_flag?this._t('event_temperature'):temperature!==null?this._t('current_temperature',{temperature:this._formatTemperature(temperature)}):this._t('temperature_unavailable');
    this._activity('audio',s.audio_level,s.connected&&s.audio_live&&s.audio_active);
    this.$('noise-enabled').checked=Boolean(s.detection?.noise);for(const kind of ['noise']){this._setValue(kind+'-threshold',s.detection?.[kind+'_threshold']);this.$(kind+'-threshold-value').textContent=(s.detection?.[kind+'_threshold']??'–')+' %';}
    this.$('events').replaceChildren();for(const event of(s.events||[]).slice(0,6)){const li=document.createElement('li'),text=document.createElement('span'),time=document.createElement('time');text.textContent=this._eventText(event);time.textContent=new Date(event.time*1000).toLocaleTimeString(this._locale(),{hour:'2-digit',minute:'2-digit',second:'2-digit'});li.append(text,time);this.$('events').append(li);}if(!s.events?.length){const li=document.createElement('li');li.textContent=this._t('no_events');this.$('events').append(li);}this.$('event-count').textContent=this._t('event_count',{count:s.events?.length||0});
    const picture=this._hass.states[this._config.entity]?.attributes.entity_picture;
    const snapshot=this.$('snapshot'),canSnapshot=this._canControl()&&live&&Boolean(picture);
    snapshot.setAttribute('aria-disabled',String(!canSnapshot));snapshot.tabIndex=canSnapshot?0:-1;
    if(canSnapshot)snapshot.href=this._hass.hassUrl(picture);else snapshot.removeAttribute('href');
    if(this._talking&&Date.now()-this._talkStarted>4000&&!s.talking){this._stopTalk();this._notice(this._t('talk_ended'),true);}
    if(!this._canControl())this._disableControls();
  }
  _updateListen(){
    const muted=this.$('video').muted,button=this.$('listen');
    button.querySelector('img').src=ICONS[muted?'mute':'volume'];
    button.classList.toggle('active',!muted);button.setAttribute('aria-pressed',String(!muted));
    const label=muted?this._t('listen_on'):this._t('listen_off');button.setAttribute('aria-label',label);button.title=label+this._t('hold_settings');
    button.disabled=this._pc?.connectionState!=='connected'||!this._canControl();
  }
  _updateTalk(){
    const button=this.$('talk');if(!button)return;
    button.querySelector('img').src=ICONS[this._talking?'microphone':'microphoneOff'];
    button.classList.toggle('active',this._talking);button.classList.toggle('pending',this._talkStarting);
    button.setAttribute('aria-pressed',String(this._talking));button.setAttribute('aria-busy',String(this._talkStarting));
    const label=this._talkStarting?this._t('mic_connecting'):this._talking?this._t('mic_off'):this._t('mic_on');
    button.setAttribute('aria-label',label);button.title=navigator.mediaDevices?.getUserMedia?label:this._t('mic_https');
    button.disabled=Boolean(this._talkStarting||this._talkRequestPending||this._talkStopPromise)||this._pc?.connectionState!=='connected'||!this._canControl()||!navigator.mediaDevices?.getUserMedia;
    this.$('media-help').textContent=this._talking?this._t('mic_active'):this._t('mic_inactive');
  }
  async _startTalk(event){
    if(!this._canControl()||event.button!==undefined&&event.button!==0||this._talking||this._talkStarting||this._talkRequestPending||this._talkStopPromise)return;
    event.preventDefault();const press=++this._press,generation=this._generation,request={};let stream;
    this._talkRequestPending=request;
    this._talkStarting=true;this._updateTalk();
    try{
      if(!this._session||!navigator.mediaDevices?.getUserMedia)throw new Error(this._t('talk_requires_live'));
      const sender=this._audio?.sender,peer=this._pc,session=this._session;
      if(!sender||typeof sender.replaceTrack!=='function')throw new Error(this._t('talk_not_ready'));
      stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
      if(press!==this._press||generation!==this._generation||peer!==this._pc||session!==this._session){stream.getTracks().forEach(t=>t.stop());return;}
      const track=stream.getAudioTracks()[0];
      if(!track)throw new Error(this._t('mic_no_track'));
      this._mic=stream;await this._hass.callWS({type:'local_babyphone/talk',entity_id:this._config.entity,session_id:this._session,active:true});
      if(press!==this._press||generation!==this._generation){stream.getTracks().forEach(t=>t.stop());await this._stopTalk(true);return;}
      await sender.replaceTrack(track);
      if(press!==this._press||generation!==this._generation){await this._stopTalk(true);return;}
      this._talking=true;this._talkStarting=false;this._talkStarted=Date.now();
      this._updateListen();this._updateTalk();
    }catch(e){stream?.getTracks().forEach(t=>t.stop());await this._stopTalk(true);const message=this._error(e,'talk_failed');this._notice(e.name&&e.name!=='Error'?`${e.name}: ${message}`:message,true);}
    finally{if(this._talkRequestPending===request)this._talkRequestPending=null;if(press===this._press)this._talkStarting=false;this._updateTalk();}
  }
  async _stopTalk(force=false){
    this._press++;const starting=this._talkStarting;this._talkStarting=false;
    if(this._talkStopPromise)return this._talkStopPromise;
    if(!this._talking&&!this._mic&&!force){if(starting)this._updateTalk();return;}
    const session=this._session,entity=this._config?.entity,hass=this._hass,sender=this._audio?.sender;
    this._talking=false;this._mic?.getTracks().forEach(t=>t.stop());this._mic=null;
    const stop=(async()=>{
      try{if(sender?.replaceTrack)await sender.replaceTrack(null);}catch(_e){}
      if(session&&hass&&entity)await hass.callWS({type:'local_babyphone/talk',entity_id:entity,session_id:session,active:false}).catch(()=>{});
    })();
    this._talkStopPromise=stop;
    if(this.$('video')){this._updateListen();this._updateTalk();}
    try{await stop;}finally{if(this._talkStopPromise===stop)this._talkStopPromise=null;this._updateTalk();}
  }
  _unavailable(message){this._connectionLost=true;if(!this.$('video-placeholder'))return;this.$('video-placeholder').style.display='flex';this.$('video-placeholder').lastElementChild.textContent=message;this._wifi({connected:false});this._activity('audio',0,false);this._disableControls();}
  _cleanup(){
    if(this._zoomDrag)this._saveZoom();
    this._mediaPaused=false;
    this._zoomDrag=null;this.$('settings-dialog')?.close();
    this._generation++;this._starting=false;this._stopTalk();this._mic?.getTracks().forEach(t=>t.stop());
    if(this._pc){this._pc.onconnectionstatechange=null;this._pc.close();this._pc=null;}
    if(this._subscription){Promise.resolve(this._subscription()).catch(()=>{});this._subscription=null;}
    if(this._offerSubscription){Promise.resolve(this._offerSubscription()).catch(()=>{});this._offerSubscription=null;}
    for(const release of this._releases)release();this._releases=[];this._wired=false;this._listenedConnection=null;
    for(const timer of this._timers)clearTimeout(timer);this._timers.clear();this._mediaRetry=null;
    const video=this.$('video');if(video&&this._frameCallback)video.cancelVideoFrameCallback?.(this._frameCallback);
    this._session=null;
  }
}

class LocalBabyphoneCardEditor extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});}
  setConfig(config){this._config=config;this._render();}
  set hass(hass){this._hass=hass;this._render();}
  _render(){if(!this._config||!this._hass)return;if(!this._form){this._form=document.createElement('ha-form');this._form.schema=[{name:'entity',required:true,selector:{entity:{domain:'camera',integration:'local_babyphone'}}}];this._form.addEventListener('value-changed',event=>{this._config={...this._config,...event.detail.value};this.dispatchEvent(new CustomEvent('config-changed',{detail:{config:this._config},bubbles:true,composed:true}));});this.shadowRoot.append(this._form);}this._form.computeLabel=()=>cardText(this._hass,'camera_entity');this._form.hass=this._hass;this._form.data=this._config;}
}
if(!customElements.get('local-babyphone-card'))customElements.define('local-babyphone-card',LocalBabyphoneCard);
if(!customElements.get('local-babyphone-card-editor'))customElements.define('local-babyphone-card-editor',LocalBabyphoneCardEditor);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==='local-babyphone-card'))window.customCards.push({type:'local-babyphone-card',name:'Avent local',description:CARD_TRANSLATIONS.en.card_description,preview:true});
