import StyledSelect from './StyledSelect';
import RatingBadge from './RatingBadge';
import OfferActions from './OfferActions';
import './ATSApplications.css';
import React, { useEffect, useState } from 'react';
import { native } from './fspApi';
import { api } from './api';

const categories={all:'Все отклики',suitable:'Подходят',review:'Нужно уточнить',unsuitable:'Явные расхождения'};
const statuses={submitted:'Новый отклик',viewed:'Просмотрен',accepted:'Принят',rejected:'Отказ'};
const criterionStatus={match:'Совпадает',mismatch:'Расхождение',unknown:'Уточнить'};
const weights={grade:'Грейд',experience:'Опыт',skills:'Стек',format:'Формат',salary:'Зарплата'};

export default function ATSApplications({workspace,action,notify}) {
  const publishedVacancies=(workspace.vacancies || []).filter(v=>v.published);
  const [selectedVacancy,setVacancy]=useState(workspace.vacancy?.id || '');
  const vacancy=publishedVacancies.find(v=>v.id===selectedVacancy)?.id || publishedVacancies[0]?.id || '';
  const [items,setItems]=useState(null),[settings,setSettings]=useState(null),[error,setError]=useState('');
  const [filter,setFilter]=useState('all'),[busy,setBusy]=useState(false),[showSettings,setShowSettings]=useState(false);
  const [skillText,setSkillText]=useState('');
  useEffect(()=>{
    if(!vacancy) {setItems(null);setSettings(null);return;}
    let active=true;
    setItems(null);setSettings(null);setError('');setFilter('all');
    async function refresh() {
      try { const data=await native('/vacancies/'+vacancy+'/applications');if(active){setItems(data);setError('');} }
      catch(e){if(active)setError(e.message);}
    }
    refresh();
    native('/vacancies/'+vacancy+'/ats/settings').then(data=>{if(active){setSettings(data.criteria);setSkillText(data.criteria.required_skills.join(', '));}}).catch(e=>{if(active)setError(e.message);});
    const timer=setInterval(refresh,5000);
    return ()=>{active=false;clearInterval(timer);};
  },[vacancy]);
  async function reload() {setItems(await native('/vacancies/'+vacancy+'/applications'));}
  function patch(key,value){setSettings(current=>({...current,...(key==='reqcore_criteria'?{mode:'manual'}:{}),[key]:value}));}
  async function save(e) {
    e.preventDefault();setBusy(true);
    try {
      const data=await native('/vacancies/'+vacancy+'/ats/settings','PUT',{...settings,required_skills:skillText.split(',').map(s=>s.trim()).filter(Boolean)});
      setSettings(data.criteria);setSkillText(data.criteria.required_skills.join(', '));await reload();
      notify('Критерии сохранены. Отклики пересчитываются.');
    } catch(e){notify(e.message);} finally{setBusy(false);}
  }
  async function recalculate(){setBusy(true);try{await native('/vacancies/'+vacancy+'/ats/recalculate','POST');await reload();notify('Оценка откликов запущена');}catch(e){notify(e.message);}finally{setBusy(false);}}
  async function generate(){setBusy(true);try{const data=await native('/vacancies/'+vacancy+'/ats/generate','POST');setSettings({...data.criteria,mode:'manual'});setSkillText(data.criteria.required_skills.join(', '));setShowSettings(true);notify('Reqcore сформировал критерии. Проверьте их и сохраните.');}catch(e){notify(e.message);}finally{setBusy(false);}}
  async function decide(item,status){setBusy(true);try{await action(()=>native('/vacancies/applications/'+item.id,'PATCH',{status}));await reload();}catch{}finally{setBusy(false);}}
  async function sendAssessment(item){setBusy(true);try{const offer=await action(()=>api('/api/vacancies/'+vacancy+'/assessment-invitations',{method:'POST',body:{candidate_id:item.candidate_id}}));await reload();notify(offer.assessment_created?'Тестовое отправлено соискателю':'Соискателю уже назначено это тестовое');}catch{}finally{setBusy(false);}}
  async function prepareAssessment(){setBusy(true);try{await action(()=>api('/api/me/active-vacancy',{method:'PUT',body:{vacancy_id:vacancy}}));location.hash='/employer/builder';}catch{}finally{setBusy(false);}}
  async function continueApplication(item){setBusy(true);try{await action(()=>native('/vacancies/applications/'+item.id+'/conversation','POST'));await reload();}catch{}finally{setBusy(false);}}
  async function download(item){try{const blob=await api('/api/v1/vacancies/applications/'+item.id+'/ats/report?download=true',{blob:true});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='ATS-отчёт-'+item.id+'.html';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){notify(e.message);}}
  const displayed=(items || []).filter(item=>filter==='all' || (item.ats_report?.category || 'review')===filter);
  return <div className="ats-applications">
    <section className="card ats-filters" aria-labelledby="ats-filters-title">
    <div className="section-heading"><div><h2 id="ats-filters-title">Фильтры откликов</h2><p className="muted">ATS объясняет соответствие требованиям. Принять кандидата или отказать решаете вы.</p></div></div>
    <label className="field"><span>Вакансия</span><StyledSelect value={vacancy} disabled={!publishedVacancies.length} onChange={e=>setVacancy(e.target.value)}>{!publishedVacancies.length && <option value="">Нет опубликованных вакансий</option>}{publishedVacancies.map(v=><option key={v.id} value={v.id}>{v.title}</option>)}</StyledSelect></label>
    <div className="fsp-tabs ats-tabs" role="group" aria-label="Категории откликов">{Object.entries(categories).map(([key,label])=><button type="button" disabled={!items} aria-pressed={filter===key} className={'pill '+(filter===key?'primary':'secondary')} key={key} onClick={()=>setFilter(key)}>{label} · {(items||[]).filter(item=>key==='all' || (item.ats_report?.category || 'review')===key).length}</button>)}</div>
    </section>
    <div className={'ats-content-layout'+(showSettings?' ats-settings-expanded':'')}>
    <aside className="card ats-control-panel" aria-labelledby="ats-controls-title">
      <span className="mono accent-text">ОЦЕНКА СООТВЕТСТВИЯ</span><h2 id="ats-controls-title">Настройки ATS</h2>
      <p className="muted">Критерии оценки для выбранной вакансии. Последнее слово остаётся за вами.</p>
      {vacancy ? <div className="ats-control-actions"><button type="button" className="pill secondary" aria-expanded={showSettings} aria-controls="ats-settings-form" disabled={!settings} onClick={()=>setShowSettings(!showSettings)}>{showSettings?'Свернуть критерии':'Настроить критерии'}</button><button type="button" className="pill secondary" disabled={busy} onClick={generate}>Автонастройка Reqcore</button><button type="button" className="pill secondary" disabled={busy} onClick={recalculate}>Пересчитать отклики</button></div> : <p className="muted">Опубликуйте вакансию, чтобы настроить оценку откликов.</p>}
    {showSettings && settings && <form id="ats-settings-form" className="ats-settings" onSubmit={save}>
      <h3>Критерии для этой вакансии</h3>
      <button type="button" className="text-button" disabled={(settings.reqcore_criteria || []).length>=10} onClick={()=>patch('reqcore_criteria',[...(settings.reqcore_criteria || []),{key:'custom_'+Date.now(),name:'Дополнительное требование',description:'Укажите профессиональное требование к кандидату',category:'custom',maxScore:10,weight:25}])}>Добавить критерий</button>
      {(settings.reqcore_criteria || []).map((c,index)=><div className="field" key={c.key}><input aria-label="Название критерия" value={c.name} onChange={e=>patch('reqcore_criteria',settings.reqcore_criteria.map((row,i)=>i===index?{...row,name:e.target.value}:row))}/><textarea aria-label="Описание критерия" value={c.description || ''} onChange={e=>patch('reqcore_criteria',settings.reqcore_criteria.map((row,i)=>i===index?{...row,description:e.target.value}:row))}/><label>Вес <input type="number" min="0" max="100" value={c.weight} onChange={e=>patch('reqcore_criteria',settings.reqcore_criteria.map((row,i)=>i===index?{...row,weight:Number(e.target.value)}:row))}/></label><button type="button" className="text-button" onClick={()=>patch('reqcore_criteria',settings.reqcore_criteria.filter((_,i)=>i!==index))}>Убрать критерий</button></div>)}
      <label className="field"><span>Режим настройки</span><StyledSelect value={settings.mode} onChange={e=>patch('mode',e.target.value)}><option value="auto">Автоматически по вакансии</option><option value="manual">Настроить вручную</option></StyledSelect></label>
      <p className="muted">Автонастройка использует грейд, опыт, технологии и условия вакансии. В ручном режиме вы задаёте собственные критерии.</p>
      <fieldset disabled={settings.mode==='auto'} className="ats-settings-fields">
        <label className="field"><span>Минимальный грейд</span><StyledSelect value={settings.min_grade || ''} onChange={e=>patch('min_grade',e.target.value || null)}><option value="">Не учитывать</option>{['intern','junior','middle','senior','lead'].map(g=><option key={g} value={g}>{g}</option>)}</StyledSelect></label>
        <label className="field"><span>Опыт от, лет</span><input type="number" min="0" max="50" step="0.5" value={settings.min_experience_years} onChange={e=>patch('min_experience_years',Number(e.target.value))}/></label>
        <label className="field"><span>Обязательные технологии через запятую</span><input value={skillText} onChange={e=>setSkillText(e.target.value)}/></label>
        <label className="field"><span>Формат работы</span><StyledSelect value={settings.work_format || ''} onChange={e=>patch('work_format',e.target.value || null)}><option value="">Не учитывать</option><option value="remote">Удалённо</option><option value="office">В офисе</option><option value="hybrid">Гибрид</option></StyledSelect></label>
        <label className="field"><span>Зарплатные ожидания до, ₽</span><input type="number" min="0" value={settings.salary_max ?? ''} onChange={e=>patch('salary_max',e.target.value===''?null:Number(e.target.value))}/></label>
        <label className="field"><span>Порог «Подходят», %</span><input type="number" min="1" max="100" value={settings.suitable_threshold} onChange={e=>patch('suitable_threshold',Number(e.target.value))}/></label>
        <label className="field"><span>Порог явных расхождений, %</span><input type="number" min="0" max="99" value={settings.unsuitable_threshold} onChange={e=>patch('unsuitable_threshold',Number(e.target.value))}/></label>
        <div className="ats-weight-fields">{Object.entries(weights).map(([key,label])=><label className="field" key={key}><span>Вес: {label}</span><input type="number" min="0" max="100" value={settings.weights[key]} onChange={e=>patch('weights',{...settings.weights,[key]:Number(e.target.value)})}/></label>)}</div>
        <label className="check-row"><input type="checkbox" checked={settings.strict_grade} onChange={e=>patch('strict_grade',e.target.checked)}/>Подтверждённый грейд ниже требуемого — явное расхождение</label>
        <label className="check-row"><input type="checkbox" checked={settings.strict_experience} onChange={e=>patch('strict_experience',e.target.checked)}/>Указанный опыт меньше требуемого — явное расхождение</label>
      </fieldset>
      <p className="muted">Отсутствие данных само по себе не означает несоответствие. Если основных данных недостаточно, отклик попадёт в «Нужно уточнить». Небольшие пробелы отмечаются в отчёте.</p>
      <button className="pill primary" disabled={busy}>Сохранить и пересчитать</button>
    </form>}
    </aside>
    {!showSettings && <section className="ats-candidates" aria-labelledby="ats-candidates-title">
    <div className="section-heading"><h2 id="ats-candidates-title">Соискатели</h2><span className="mono muted">{displayed.length} откликов</span></div>
    {error && <p role="alert" className="auth-error card">{error}</p>}
    {vacancy && !items && !error && <p className="card" role="status">Загрузка откликов…</p>}
    {displayed.map(item=>{const report=item.ats_report;return <article className="card ats-application" key={item.id}>
      <div className="section-heading"><a href={'#/employer/person/'+item.candidate_id}><h3>{item.display_name}</h3></a><span className="tag">{statuses[item.status] || item.status}</span></div>
      <p>{item.cover_letter || 'Без сопроводительного письма'}</p>
      <RatingBadge value={item.profile_strength}/>
      {item.contacts && <p className="muted">{item.contacts.email} {item.contacts.phone}</p>}
      <div className={'ats-report ats-'+(report?.category || 'review')}>
        <div className="section-heading"><b>{categories[report?.category] || 'Нужно уточнить'}</b>{report?.state==='ready' && <span>{report.score == null?'Недостаточно данных':report.score+' / 100'} · покрытие {report.coverage}%</span>}</div>
        <p>{report?.summary || 'Отчёт формируется'}</p>
        {report?.state==='ready' && <>
          <details><summary>Почему такая рекомендация</summary><p className="muted">{report.provider} · {report.model}</p><div className="ats-criteria">{report.criteria.map(row=><div key={row.key}><b>{row.label} · {criterionStatus[row.status]}</b><p>Требование: {row.requirement}</p><p>{row.evidence}</p>{row.strengths?.length>0 && <p>Сильные стороны: {row.strengths.join('; ')}</p>}{row.gaps?.length>0 && <p>Пробелы: {row.gaps.join('; ')}</p>}</div>)}</div><p className="muted">{report.notice}</p></details>
          <button className="text-button" onClick={()=>download(item)}>Скачать отчёт</button>
        </>}
      </div>
      {['submitted','viewed'].includes(item.status) && <div className="actions">{item.status==='submitted' && <button className="pill secondary" disabled={busy} onClick={()=>decide(item,'viewed')}>Просмотрен</button>}<button className="pill primary" disabled={busy} onClick={()=>decide(item,'accepted')}>Принять</button><button className="pill secondary" disabled={busy} onClick={()=>decide(item,'rejected')}>Отказать</button></div>}
      {item.status==='accepted' && <div className="notice-box application-next-step"><h3>Следующий шаг отбора</h3>{item.offer_id?<><div className="button-row">{['sent','viewed','accepted'].includes(item.offer_status)&&<><button className="pill primary" disabled={busy} onClick={()=>sendAssessment(item)}>Отправить тестовое</button><button className="pill secondary" disabled={busy} onClick={prepareAssessment}>Подготовить тестовое</button></>}<a className="pill secondary" href={'#/employer/chat/'+item.offer_id}>Открыть чат</a></div><OfferActions offerId={item.offer_id} status={item.offer_status} stage={item.hiring_stage} review notify={notify} onChanged={async()=>{await action(()=>Promise.resolve());await reload();}}/></>:<button className="pill primary" disabled={busy} onClick={()=>continueApplication(item)}>Продолжить отбор</button>}</div>}
    </article>;})}
    {items && !displayed.length && <div className="card ats-empty"><h3>Пока нет откликов</h3><p className="muted">В этой категории пока нет откликов.</p></div>}{!vacancy&&<div className="card ats-empty"><h3>Нет опубликованных вакансий</h3><p className="muted">Отклики появятся здесь после публикации вакансии.</p></div>}
  </section>}
  </div>
  </div>;
}
