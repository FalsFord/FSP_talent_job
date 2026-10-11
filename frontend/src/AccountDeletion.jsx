import React,{useState} from 'react';
import {api,setAuth,flushWrites} from './api';
export default function AccountDeletion(){
 const [password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 return <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{await flushWrites();await api('/api/me/account',{method:'DELETE',body:{password}});setAuth(null);window.dispatchEvent(new Event('auth-expired'));location.hash='/auth/login';location.reload();}catch(e){setError(e.message);setBusy(false)}}}><p>Вход в аккаунт будет закрыт, профиль очищен. Ваши активные предложения закроются, вакансии работодателя будут сняты с публикации. Отправленные решения и отчёты останутся в истории отбора.</p><label className="field"><span>Текущий пароль</span><input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{error&&<p role="alert">{error}</p>}<button className="pill secondary" disabled={busy||!password}>Удалить мой аккаунт</button></form>
}
