import React, {useEffect,useState} from 'react';
import {api} from './api';
import {Flame, ArrowRight, CodeXml, ListChecks, BriefcaseBusiness, Check} from 'lucide-react';
import './Rewards.css';

export default function Rewards({variant='all'}) {
  const [data,setData]=useState(null),[error,setError]=useState('');
  useEffect(()=>{
    let active=true;
    const load=()=>api('/api/rewards').then(v=>{if(active){setData(v);setError('');}}).catch(e=>{if(active)setError(e.message);});
    load();window.addEventListener('rewards-changed',load);
    return ()=>{active=false;window.removeEventListener('rewards-changed',load);};
  },[]);
  if(!data)return <section className="card fsp-card">{error?<p role="alert">{error}</p>:<p>Загрузка прогресса…</p>}</section>;
  const activities=[{key:'algorithm',label:'Решить алгоритм',hint:'Пройти все тесты в редакторе',icon:CodeXml,href:'#/candidate/practice'},
    {key:'test',label:'Пройти тест знаний',hint:'Ответить верно на 4 из 5 вопросов',icon:ListChecks,href:'#/candidate/practice'},
    {key:'company',label:'Выполнить тестовое',hint:'Получить оценку работодателя от 70%',icon:BriefcaseBusiness,href:'#/candidate/tasks'}];
  const format=n=>Number(n||0).toLocaleString('ru-RU',{maximumFractionDigits:2});
  return <div className={'rewards-layout'+(variant!=='all'?' rewards-layout-single':'')}>
    {variant!=='daily' && <section className="card rewards-rating" aria-label="Рейтинг профиля">
      <div className="rewards-heading"><div><span className="mono accent-text">ВАШИ РЕЗУЛЬТАТЫ</span><h2>Рейтинг профиля</h2></div><div className="rewards-score"><b>{format(data.profile_rating)}</b><span className="mono muted">из 100</span></div></div>
      <div className="rewards-note"><p>Этот рейтинг видят работодатели.</p><p className="muted">Квалификация, результаты заданий и достижения ФСП помогают оценить ваш опыт.</p></div>
      <div className="rewards-breakdown">{[{key:'qualification',label:'Квалификация',max:60},{key:'fsp',label:'Достижения ФСП',max:25},{key:'tasks',label:'Задания компаний',max:15}].map(row=><div key={row.key}><div className="rewards-line"><span className="muted">{row.label}</span><span className="mono">{format(data.rating_components?.[row.key])} / {row.max}</span></div><progress aria-label={row.label} max={row.max} value={data.rating_components?.[row.key]||0}/></div>)}</div>
      <details className="rewards-rules"><summary>Как формируется рейтинг</summary><p className="muted">До 60 баллов — квалификация, до 25 — ФСП, до 15 — задания компаний. Учитывается актуальность подтверждения. Ежедневные XP поощряют регулярность и отображаются отдельно.</p><p className="muted">ФСП: {data.fsp_count} достижений, вклад +{format(data.fsp_rating_bonus)}. Данные ФСП пока демонстрационные.</p></details>
      <a className="pill secondary" href="#/candidate/development">Подтвердить квалификацию <ArrowRight size={18} aria-hidden="true"/></a>
    </section>}
    {variant!=='rating' && <section className="card rewards-daily" aria-label="Ежедневный прогресс">
      <div className="rewards-heading"><div><span className="mono accent-text">ШАГ ЗА ШАГОМ</span><h2>Ежедневный прогресс</h2></div><span className="tag">Уровень {data.level}</span></div>
      <div className="rewards-overview"><div className="rewards-stats"><div><span className="rewards-stat-label"><Flame size={18} aria-hidden="true"/> Серия дней</span><b>{data.streak}</b><span className="mono muted">Лучшая серия: {data.best_streak}</span></div><div><span className="muted">Опыт</span><b>{data.xp}<small> XP</small></b><span className="mono muted">До следующего уровня: {100-data.xp%100} XP</span></div></div>
      <div className="rewards-today"><div className="rewards-line"><span>Сегодня</span><span className="mono">{data.earned_today} / {data.daily_limit} XP</span></div><progress aria-label="Награда за сегодня" value={data.earned_today} max={data.daily_limit}/></div></div>
      <div className="rewards-activities">{activities.map(row=>{const done=!!data.daily[row.key], Icon=row.icon;return <a key={row.key} className={'rewards-activity '+(done?'is-done':'')} href={row.href}><span className="rewards-activity-icon">{done?<Check size={20} aria-hidden="true"/>:<Icon size={20} aria-hidden="true"/>}</span><span className="rewards-activity-copy"><b>{row.label}</b><span className="muted">{row.hint}</span></span><span className="mono accent-text">{done?'Получено':'+10 XP'}</span></a>;})}</div>
      <details className="rewards-rules"><summary>Правила ежедневных наград</summary><p className="muted">Одна награда на тип задания за день. Повторное прохождение не приносит XP. После лимита можно продолжать заниматься без начисления. Новый день начинается в полночь по Москве; пропуск дня сбрасывает текущую серию.</p></details>
    </section>}
  </div>;
}

