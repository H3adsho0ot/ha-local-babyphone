// A held press opens settings and must never fall through to the toggle click.
function bindPressAction({target,listen,schedule,cancel,onTap,onHold}){
  let pointer=null,timer=null,suppressClick=false;
  const clear=()=>{if(timer!==null){cancel(timer);timer=null;}};
  listen(target,'pointerdown',event=>{
    if(target.disabled||event.button!==0)return;
    clear();suppressClick=false;pointer={id:event.pointerId,x:event.clientX,y:event.clientY};
    timer=schedule(()=>{timer=null;if(pointer){suppressClick=true;onHold();}},650);
  });
  listen(target,'pointermove',event=>{
    if(pointer&&event.pointerId===pointer.id&&Math.hypot(event.clientX-pointer.x,event.clientY-pointer.y)>10){
      clear();pointer=null;suppressClick=true;
    }
  });
  listen(target,'pointerup',event=>{if(pointer?.id===event.pointerId){clear();pointer=null;}});
  listen(target,'pointercancel',()=>{clear();pointer=null;suppressClick=true;});
  listen(target,'click',event=>{
    if(target.disabled||suppressClick){event.preventDefault();event.stopPropagation();suppressClick=false;return;}
    onTap(event);
  });
  listen(target,'contextmenu',event=>{
    event.preventDefault();clear();pointer=null;
    if(!target.disabled&&!suppressClick){suppressClick=true;onHold();}
  });
  listen(target,'keydown',event=>{
    if((event.shiftKey&&event.key==='Enter')||event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')){
      event.preventDefault();clear();pointer=null;suppressClick=true;if(!target.disabled)onHold();
    }else if(event.key==='Enter'||event.key===' ')suppressClick=false;
  });
  return ()=>{clear();pointer=null;};
}
