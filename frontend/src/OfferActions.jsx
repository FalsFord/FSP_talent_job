import React,{useState} from 'react';
import {api,revalidate} from './api';

export default function OfferActions({offerId,status,stage,review=false,notify,onChanged}) {
 const [editing,setEditing]=useState(false),[name,setName]=useState('Собеседование'),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const active=['sent','viewed','accepted'].includes(status);
 async function run(path,body){setBusy(true);try{await api(path,{method:'POST',...(body?{body}:{})});revalidate();await onChanged?.();setEditing(false);notify(body?'Соискателю отправлено сообщение о новом этапе':'Предложение отозвано');}catch(e){notify(e.message)}finally{setBusy(false)}}
 if(!offerId)return null;
 return <div className="offer-actions">
   {stage?.name&&<p className="muted">Текущий этап: <b>{stage.name}</b></p>}
   {!active?<p className="muted">{status==='withdrawn'?'Предложение отозвано. Отбор завершён.':'Предложение закрыто.'}</p>:<>
   <div className="button-row">{review&&<button className="pill primary" disabled={busy} onClick={()=>setEditing(!editing)}>Пригласить на новый этап</button>}<button className="pill secondary" disabled={busy} onClick={()=>run('/api/v1/invitations/'+offerId+'/withdraw')}>Отозвать предложение</button></div>
   {editing&&<div className="notice-box"><label className="field"><span>Следующий этап</span><input value={name} maxLength={100} onChange={e=>setName(e.target.value)} placeholder="Например, техническое собеседование"/></label><label className="field"><span>Сообщение соискателю</span><textarea value={message} maxLength={2000} onChange={e=>setMessage(e.target.value)} placeholder="Расскажите, что будет дальше и как договориться о встрече"/></label><p className="muted">Соискатель получит уведомление и сообщение в чате.</p><div className="button-row"><button className="pill primary" disabled={busy||name.trim().length<2} onClick={()=>run('/api/offers/'+offerId+'/stage',{stage:name.trim(),message:message.trim()})}>Отправить приглашение</button><button className="pill secondary" disabled={busy} onClick={()=>setEditing(false)}>Отмена</button></div></div>}
   </>}
 </div>;
}
