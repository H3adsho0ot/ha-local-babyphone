// HA's selected language wins over the browser language; unsupported languages use English.
function cardLanguage(hass){return String(hass?.locale?.language||hass?.language||'en').toLowerCase().split(/[-_]/)[0]==='de'?'de':'en';}
function cardLocale(hass){return cardLanguage(hass)==='de'?'de-DE':'en-US';}
function cardText(hass,key,values={}){
  const text=CARD_TRANSLATIONS[cardLanguage(hass)]?.[key]??CARD_TRANSLATIONS.en[key]??key;
  return text.replace(/\{(\w+)\}/g,(match,name)=>Object.hasOwn(values,name)?String(values[name]):match);
}
function cardError(hass,error,fallback){
  const message=error?.message;
  if(!message)return cardText(hass,fallback);
  for(const catalog of Object.values(CARD_TRANSLATIONS))for(const [key,text]of Object.entries(catalog)){
    if(key.startsWith('error_')&&text===message)return cardText(hass,key);
  }
  return message;
}
