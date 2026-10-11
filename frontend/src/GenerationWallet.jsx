import React,{useEffect,useState} from 'react';
import {api} from './api';

export default function GenerationWallet({onChange}) {
  const [access,setAccess]=useState(null),[units,setUnits]=useState(100),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
  useEffect(()=>{let active=true;api('/api/me/generation-access').then(v=>{if(active)setAccess(v)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[]);
  async function topup(){
    if(busy)return;setBusy(true);setError('');setMessage('');
    try{const data=await api('/api/me/generation-access/demo-topup',{method:'POST',body:{units:Number(units),request_id:crypto.randomUUID()}});setAccess(data);onChange(data);setMessage('Демонстрационный баланс пополнен. Реальная оплата не проводилась.');}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  return <div className="generation-wallet">
    <div className="wallet-balance"><div><span className="mono muted">ВАШ БАЛАНС</span><strong>{access?.balance_units??'…'} <small>ед.</small></strong><span className="muted">На {access?.credits??0} генераций</span></div><div className="wallet-price"><span className="tag">Демо</span><b>10 ед. / {access?.generation_price_rub??25} ₽</b><span className="muted">за генерацию</span></div></div>
    {access&&<><div className="wallet-packages">{access.packages.map(p=><button type="button" className={'wallet-package '+(Number(units)===p.units?'selected':'')} key={p.units} disabled={busy} aria-pressed={Number(units)===p.units} onClick={()=>setUnits(p.units)}><strong>{p.generations}</strong><span>генераций</span><b>{p.price_rub.toLocaleString('ru-RU')} ₽</b><small className="muted">{p.units} единиц</small></button>)}</div><div className="wallet-topup"><label className="field"><span>Своя сумма, в единицах</span><input type="number" min="1" max="10000" step="1" value={units} disabled={busy} onChange={e=>setUnits(e.target.value)}/></label><button type="button" className="pill primary" onClick={topup} disabled={busy||!access.demo||!Number.isInteger(Number(units))||Number(units)<1||Number(units)>10000}>{busy?'Пополняем…':'Пополнить на '+(Number(units||0)*access.unit_price_rub).toLocaleString('ru-RU')+' ₽'}</button></div></>}
    <p className="wallet-footnote muted">1 ед. = 2,5 ₽. Ручное создание и алгоритмы бесплатны. Списание только после успешной генерации. Пополнение демонстрационное, реальная оплата не проводится.</p>
    {message&&<p role="status">{message}</p>}{error&&<p role="alert" className="auth-error">{error}</p>}
  </div>;
}
