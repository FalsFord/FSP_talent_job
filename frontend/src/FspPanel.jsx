import {PrivateImage} from './api';
import React, { useEffect, useState, lazy, Suspense } from 'react';
import { native } from './fspApi';
import { api } from './api';
import ATSApplications from './ATSApplications';
import StyledSelect from './StyledSelect';
import Rewards from './Rewards';
import GitReport from './GitReport';
import {evaluationLabels} from './TaskStatus';
import SubmissionReviews from './SubmissionReviews';
import RatingBadge from './RatingBadge';
const CodeEditor=lazy(()=>import('./CodeEditor'));

const verification = { confirmed:'Квалификация подтверждена', stale:'Подтверждение требует обновления', unconfirmed:'Квалификация пока не подтверждена' };
const statuses = { evaluating:'Проверяется репозиторий', in_progress:'В процессе', submitted: 'Отправлено', viewed: 'Просмотрено', accepted: 'Принято', rejected: 'Отклонено', assigned: 'Назначено', reviewed: 'Проверено', sent: 'Отправлено', declined: 'Отклонено', expired: 'Истекло', withdrawn: 'Отозвано' };
function useLoad(path) {
  const [value, setValue] = useState(null), [error, setError] = useState('');
  async function refresh() { try { setError(''); setValue(await native(path)); } catch (e) { setError(e.message); } }
  useEffect(() => { setValue(null); refresh(); }, [path]);
  return [value, refresh, error];
}
function Busy({ error, value }) { return error ? <p role="alert" className="auth-error">{error}</p> : value == null ? <p>Загрузка…</p> : null; }

export default function WorkPage({ authUser, notify, reloadWorkspace, workspace, section, theme, startCompanyTask }) {
  const role = authUser.role;
  async function action(fn) { try { const value = await fn(); await reloadWorkspace(); return value; } catch (e) { notify(e.message); throw e; } }
  const props = { role, notify, action, workspace, theme, startCompanyTask };
  const pages = {vacancies: Vacancies, applications: Applications, tasks: role==='employer'?SubmissionReviews:Tasks, settings: Privacy, development: History, notifications: Notifications};
  const Page = pages[section] || Notifications;
  const titles = {vacancies:'Вакансии',applications:'Отклики',tasks:role==='employer'?'Проверка решений':'Задания от компаний',settings:'Настройки профиля',development:'Моя квалификация',notifications:'Уведомления'};
  return <><div className="page-title"><div><span className="mono accent-text">{role==='employer'?'КОМАНДА':'КАРЬЕРА'}</span><h1>{titles[section] || 'Уведомления'}</h1></div></div><Page {...props} /></>;
}
function Notifications({ action }) {
  const [data, refresh, error] = useLoad('/notifications');
  async function read(id) { await action(() => native('/notifications/' + id + '/read', 'POST')); window.dispatchEvent(new Event('notifications-changed')); await refresh(); }
  return <section className="card fsp-card"><h2>Уведомления {data && `· ${data.unread} новых`}</h2><Busy error={error} value={data} />
    {data?.items.length>0&&<button className="pill secondary" onClick={()=>{if(window.confirm("Удалить все ваши уведомления?"))action(()=>native("/notifications","DELETE")).then(()=>{window.dispatchEvent(new Event("notifications-changed"));refresh();}).catch(()=>{});}}>Удалить все</button>}
    {data?.unread > 0 && <button className="pill secondary" onClick={() => action(() => native('/notifications/read-all', 'POST')).then(() => { window.dispatchEvent(new Event('notifications-changed')); refresh(); }).catch(() => {})}>Прочитать все</button>}
    {data?.items.map(n => <article className="fsp-row" key={n.id}><div><b>{n.title}</b><p>{n.body}</p><span className="mono muted">{new Date(n.created_at).toLocaleString('ru')}</span></div>{n.payload?.url && <a className="pill primary" href={'#'+n.payload.url} onClick={()=>read(n.id).catch(()=>{})}>Открыть задание</a>}{!n.read && <button className="pill secondary" onClick={() => read(n.id).catch(() => {})}>Прочитано</button>}<button className="text-button" onClick={()=>action(()=>native("/notifications/"+n.id,"DELETE")).then(()=>{window.dispatchEvent(new Event("notifications-changed"));refresh();}).catch(()=>{})}>Удалить</button></article>)}
    {data?.items.length === 0 && <p className="muted">Уведомлений пока нет.</p>}</section>;
}
function Vacancies({ action, notify, workspace }) {
  const canApply = workspace?.profile?.registration?.complete === true;
  const [data,setData]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const [applications, reload] = useLoad('/vacancies/applications/mine');
  const [draft,setDraft]=useState(''),[query,setQuery]=useState(''),[format,setFormat]=useState(''),[skill,setSkill]=useState(''),[salary,setSalary]=useState(''),[sort,setSort]=useState('relevance'),[hideApplied,setHideApplied]=useState(false);
  const [selected, setSelected] = useState(null), [letter, setLetter] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => {
    let active=true;const controller=new AbortController();setLoading(true);setError('');
    const timer=setTimeout(() => api('/api/vacancies/search',{method:'POST',signal:controller.signal,body:{query,work_format:format,skill,salary_min:salary,sort}}).then(result => { if(active) setData(result); }).catch(e => { if(active) setError(e.message); }).finally(() => { if(active) setLoading(false); }),200);
    return () => { active=false;clearTimeout(timer);controller.abort(); };
  },[query,format,skill,salary,sort]);
  useEffect(() => { if(!selected) return;const close=e => { if(e.key==='Escape' && !busy) setSelected(null); };window.addEventListener('keydown',close);return () => window.removeEventListener('keydown',close); },[selected,busy]);
  async function apply() { if(!canApply){notify('Завершите регистрацию в профиле, чтобы откликнуться.');return;} setBusy(true); try { await action(() => native('/vacancies/' + selected.id + '/apply', 'POST', { cover_letter: letter })); await reload(); setSelected(null); notify('Отклик отправлен'); } catch {} finally { setBusy(false); } }
  const appliedIds=new Set((applications || []).map(a=>a.vacancy_id));
  const items=(data?.items || []).filter(v=>!hideApplied || !appliedIds.has(v.id));
  const formats={remote:'Удалённо',office:'В офисе',hybrid:'Гибрид'};
  function reset() { setDraft('');setQuery('');setFormat('');setSkill('');setSalary('');setSort('relevance');setHideApplied(false); }
  return <>
    <section className="vacancy-search-hero"><span className="mono accent-text">ВАШ СЛЕДУЮЩИЙ ШАГ</span><h2>Работа, которая подходит вам</h2><p className="muted">Опишите, что хотите делать, или выберите технологии и условия.</p><form className="vacancy-query" onSubmit={e=>{e.preventDefault();setQuery(draft.trim());}}><input aria-label="Поиск вакансий по смыслу" maxLength={300} value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Например: писать серверные сервисы на питоне"/><button className="pill primary" type="submit" disabled={loading}>Найти работу</button></form></section>
    <div className="vacancy-catalog"><aside className="card vacancy-filters"><div className="section-heading"><h3>Фильтры</h3><button className="text-button" onClick={reset}>Сбросить</button></div>
      <div className="field"><span>Формат работы</span><StyledSelect label="Формат работы" value={format} onChange={setFormat} options={[{value:'',label:'Любой формат'},...Object.entries(formats).map(([value,label])=>({value,label}))]}/></div>
      <div className="field"><span>Технология</span><StyledSelect label="Технология" value={skill} onChange={setSkill} options={[{value:'',label:'Любой стек'},...(data?.skills || []).map(value=>({value,label:value}))]}/></div>
      <label className="field"><span>Зарплата от, ₽</span><input type="number" min="0" step="10000" value={salary} onChange={e=>setSalary(e.target.value)} placeholder="Например, 150000"/></label>
      <p className="muted">Покажем вакансии, чей диапазон достигает указанной суммы.</p><label className="check-row"><input type="checkbox" checked={hideApplied} onChange={e=>setHideApplied(e.target.checked)}/>Скрыть мои отклики</label>
    </aside><section aria-busy={loading}>
      <div className="section-heading vacancy-results-heading"><div><h2>Открытые вакансии</h2><p className="muted" role="status">{loading?'Ищем подходящие вакансии…':`${items.length} найдено${query?' · по вашему запросу':''}`}</p></div><label className="field"><span>Порядок</span><StyledSelect value={sort} onChange={e=>setSort(e.target.value)}><option value="relevance">По релевантности</option><option value="recent">Сначала новые</option><option value="salary">По зарплате</option></StyledSelect></label></div>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {!loading && !error && !items.length && <div className="card empty-state"><h3>Подходящих вакансий пока нет</h3><p>Попробуйте изменить запрос или убрать часть фильтров.</p><button className="pill secondary" onClick={reset}>Сбросить фильтры</button></div>}
      <div className="vacancy-grid">{items.map((v,index)=><article className={'vacancy-card card vacancy-tone-'+index%3} key={v.id}><div className="vacancy-card-top"><span className="vacancy-company-icon">{v.logo?<PrivateImage src={v.logo} alt="Логотип компании"/>:(v.company_name || 'К')[0]}</span><div><b>{v.company_name || 'Компания'}</b><p className="mono muted">{new Date(v.created_at).toLocaleDateString('ru')}</p></div>{appliedIds.has(v.id)&&<span className="tag">Отклик отправлен</span>}</div><h3>{v.title}</h3><p className="vacancy-salary">{v.salary_max>0?`${v.salary_min.toLocaleString('ru')}–${v.salary_max.toLocaleString('ru')} ₽`:'Зарплата по договорённости'}</p><span className="vacancy-format">{formats[v.work_format] || 'Формат обсуждается'}</span><p className="vacancy-excerpt">{v.description}</p><div className="vacancy-skills">{v.skills.map(s=><button key={s} title={'Фильтровать по '+s} onClick={()=>setSkill(s)}>{s}</button>)}</div><details className="vacancy-description"><summary>Подробнее о вакансии</summary><p className="preserve">{v.description}</p></details><button className="pill primary" disabled={!canApply || loading || !applications || appliedIds.has(v.id)} title={!canApply ? "Сначала завершите регистрацию — оставшиеся шаги указаны выше" : undefined} onClick={()=>{setSelected(v);setLetter('');}}>{appliedIds.has(v.id)?'Вы уже откликнулись':'Откликнуться'}</button></article>)}</div>
    </section></div>
    {selected && <div className="modal-backdrop" onClick={()=>{if(!busy)setSelected(null);}}><section className="dialog card" role="dialog" aria-modal="true" aria-label={'Отклик на '+selected.title} onClick={e=>e.stopPropagation()}><h2>Отклик на «{selected.title}»</h2><label className="field"><span>Сопроводительное письмо</span><textarea autoFocus maxLength={4000} value={letter} onChange={e=>setLetter(e.target.value)} /></label><div className="actions"><button disabled={busy || !canApply} className="pill primary" onClick={apply}>Отправить</button><button disabled={busy} className="pill secondary" onClick={()=>setSelected(null)}>Отмена</button></div></section></div>}
    <section className="card fsp-card"><h2>Мои отклики</h2>{applications?.map(a=><p key={a.id}>{a.vacancy_title} — {statuses[a.status] || a.status}</p>)}{applications?.length===0&&<p className="muted">Вы ещё не откликались на вакансии.</p>}</section>
  </>;
}
function Applications(props) { return <ATSApplications {...props}/>; }
function Privacy({ action, notify }) {
  const [profile, refresh, error] = useLoad('/candidates/me/profile'), [category] = useLoad('/candidates/me/category');
  const [privacy, setPrivacy] = useState(null), [external, setExternal] = useState(''), [linked, setLinked] = useState(null);
  useEffect(() => { if (profile) setPrivacy({ show_contacts_after_accept: profile.privacy?.show_contacts_after_accept ?? true, show_full_name: profile.privacy?.show_full_name ?? false, is_discoverable: profile.is_discoverable ?? true }); }, [profile]);
  return <><section className="card fsp-card"><h2>Приватность профиля</h2><Busy value={profile} error={error} />{privacy && <><div className="fsp-options">{[['is_discoverable', 'Показывать профиль в поиске'], ['show_full_name', 'Показывать полное имя до принятия приглашения'], ['show_contacts_after_accept', 'Открывать контакты после принятия приглашения']].map(([key, label]) => <label key={key}><input type="checkbox" checked={privacy[key]} onChange={e => setPrivacy({ ...privacy, [key]: e.target.checked })} /> {label}</label>)}</div><button className="pill primary" onClick={() => action(() => native('/candidates/me/privacy', 'PATCH', privacy)).then(() => notify('Настройки сохранены')).catch(() => {})}>Сохранить</button></>}</section>
    <section className="card fsp-card"><h2>Профиль Федерации спортивного программирования</h2><p className="muted">Достижения учитываются при подборе. Локальная демонстрационная интеграция ФСП.</p><label className="field"><span>Внешний ID участника</span><input value={external} onChange={e => setExternal(e.target.value)} maxLength={128} /></label><div className="actions"><button className="pill primary" disabled={!external.trim()} onClick={() => action(() => native('/candidates/me/fsp-link', 'POST', { external_id: external })).then(setLinked).catch(() => {})}>Связать профиль</button><button className="pill secondary" onClick={() => action(() => native('/candidates/me/fsp-link', 'DELETE')).then(() => { setLinked(null); notify('Связь удалена'); }).catch(() => {})}>Удалить связь</button></div>{linked && <><p>Профиль связан. Достижений: {linked.achievements?.length || 0}</p>{linked.achievements?.map((a, i) => <p key={i}>{a.event_name}: {a.title}, место {a.rank}</p>)}</>}</section>
    <section className="card fsp-card"><h2>Категория и подтверждение</h2>{category && <><h3>{category.category?.label || 'Категория ещё не определена'}</h3><p>{verification[category.verification_status] || 'Пройдите тест для подтверждения квалификации'}</p>{category.profile_strength != null && <p>Сила профиля: {Math.round(category.profile_strength)} / 100</p>}{category.valid_until && <p className="muted">Подтверждение действует до {new Date(category.valid_until).toLocaleDateString('ru')}</p>}</>}</section></>;
}
function History({action, notify}) {
  const [data, refresh, error] = useLoad('/assessments/history'), [status] = useLoad('/assessments/status'), [result, setResult] = useState(null), [detailError, setDetailError] = useState('');
  return <><Rewards variant="rating" /><section className="card fsp-card"><h2>Подтверждение квалификации</h2><p className="muted">Проверка профессиональных знаний влияет на подтверждённый уровень профиля. Практика алгоритмов доступна отдельно.</p><button className="pill primary" onClick={()=>action(()=>api("/api/me/assessments/grade/start",{method:"POST"})).then(()=>{location.hash="/candidate/assessment";}).catch(()=>{})}>Пройти проверку</button>{status && <><p>{verification[status.verification_status] || 'Пройдите тест для подтверждения квалификации'}</p>{status.valid_until && <p>Действует до {new Date(status.valid_until).toLocaleDateString('ru')}</p>}<p>{status.grade_change_available ? 'Доступна новая попытка тестирования' : 'Повторная попытка пока недоступна'}</p></>}</section><section className="card fsp-card"><h2>История попыток</h2><Busy value={data} error={error} />{data?.map(s => <article className="fsp-row" key={s.id}><div><p>{new Date(s.started_at).toLocaleString('ru')} · {s.languages?.join(', ')}</p><b>{statuses[s.status] || s.status}</b></div>{s.status === 'submitted' && <button className="pill secondary" onClick={() => native('/assessments/sessions/' + s.id + '/result').then(setResult).catch(e => setDetailError(e.message))}>Результат</button>}</article>)}{data?.length === 0 && <p>Вы ещё не проходили тест.</p>}{detailError && <p role="alert">{detailError}</p>}{result && <div className="notice-box"><h3>{result.category_label || 'Результат попытки'}</h3><p>Оценка: {Math.round(result.score * 100)}%</p><p>{result.passed ? 'Тест пройден' : 'Тест не пройден'}</p>{result.integrity_flags?.length > 0 && <p>При оценке учтены замечания к прохождению теста.</p>}</div>}</section></>;
}
function Tasks({ role, action, notify, workspace, theme, startCompanyTask }) {
  const employer = role === 'employer';
  const companySets = employer ? [] : (workspace.offers || []).filter(o => o.tasks?.length && !o.assessment_submitted && ['sent','viewed','accepted'].includes(o.native_status));
  async function startCompany(offer) {
    try {

      await startCompanyTask(offer);
    } catch(e) { notify(e.message); }
  }
  const [data, refresh, error] = useLoad(employer ? '/employers/tasks' : '/candidates/me/tasks');
  const [selected, setSelected] = useState(null), [assignments, setAssignments] = useState([]), [answer, setAnswer] = useState(''), [candidate, setCandidate] = useState(''), [scores, setScores] = useState({}), [repo,setRepo]=useState(''), [ref,setRef]=useState('');
  const [clockNow,setClockNow]=useState(Date.now()),[algorithmCheck,setAlgorithmCheck]=useState(null);
  useEffect(()=>{const timer=setInterval(()=>setClockNow(Date.now()),1000);return()=>clearInterval(timer)},[]);
  async function inspect(t) { if(!employer && t.status==='assigned'){t={...t,clock:await native('/candidates/me/tasks/'+t.id+'/start','POST')}} setAlgorithmCheck(t.check?{...t.check.result,source_code:t.check.source_code}:null);setSelected(t); setAnswer(t.check?.source_code || '');setRepo('');setRef(''); if (employer) setAssignments(await native('/employers/tasks/' + t.id + '/assignments')); }
  const pending=employer?assignments.some(a=>a.status==='evaluating'):selected?.status==='evaluating';
  useEffect(()=>{
    if(!selected||!pending)return;
    let active=true;
    const timer=setInterval(async()=>{
      try {
        if(employer){const rows=await native('/employers/tasks/'+selected.id+'/assignments');if(active)setAssignments(rows);}
        else {const rows=await native('/candidates/me/tasks');if(active)setSelected(rows.find(t=>t.id===selected.id)||null);await refresh();}
      }catch(e){if(active)notify(e.message);}
    },5000);
    return ()=>{active=false;clearInterval(timer);};
  },[selected?.id,pending,employer]);
  return <>{!employer && companySets.length>0 && <section className="card fsp-card"><h2>Тестовые от компаний</h2><p className="muted">Алгоритмы решаются в редакторе на платформе, проекты отправляются ссылкой на GitHub.</p>{companySets.map(o=><article className="fsp-row" key={o.id}><div><h3>{o.company} · {o.vacancy?.title || o.title}</h3><p>{o.tasks.length} заданий · Попытка {o.assessment_attempt || 1} · {o.assessment_progress?.startedAt ? "В процессе" : "Новое тестовое"}</p><p className="muted">{o.tasks.map(t=>t.title).join(" · ")}</p>{o.assessment_progress?.deadlineAt&&<p className="mono accent-text">Осталось {Math.max(0,Math.ceil((o.assessment_progress.deadlineAt-clockNow)/60000))} мин.</p>}</div><button className="pill primary" onClick={()=>startCompany(o)}>{o.assessment_progress?.startedAt ? "Продолжить" : "Принять и начать"}</button></article>)}</section>}<section className="card fsp-card"><h2>{employer ? 'Задания и проверка решений' : 'Назначенные задания'}</h2><Busy value={data} error={error} />{data?.filter(t=>employer || t.status==="assigned").map(t => <article className="fsp-row" key={t.id}><div><h3>{t.title}</h3><p>{t.company_name || t.language} · {t.vacancy_title || 'Вакансия не указана'} · {evaluationLabels[t.evaluation_status] || statuses[t.status] || t.origin}{t.score != null && ` · ${Math.round(t.score * 100)}%`}</p></div>{t.clock&&<p className="mono accent-text">В процессе · осталось {Math.max(0,Math.ceil((t.clock.deadlineAt-clockNow)/60000))} мин.</p>}<button className="pill secondary" onClick={() => inspect(t).catch(e => notify(e.message))}>Открыть</button></article>)}{data && data.filter(t=>employer || t.status==="assigned").length === 0 && !companySets.length && <p>Заданий пока нет. Когда работодатель отправит тестовое, оно появится здесь и в уведомлениях.</p>}</section>
    {selected && <section className="card fsp-card"><h2>{selected.title}</h2>{!employer&&(selected.status==="expired" || (selected.clock&&selected.clock.deadlineAt<=clockNow))&&<div role="status" className="notice-box"><h3>Время истекло — тестовое не пройдено</h3><p>Попытка закрыта. Редактор и отправка решения недоступны.</p></div>}{!employer&&selected.clock&&<p className="mono accent-text">{Math.max(0,Math.ceil((selected.clock.deadlineAt-clockNow)/1000))} секунд осталось · после истечения времени задание не пройдено</p>}{employer ? <><label className="field"><span>Назначить соискателю</span><StyledSelect value={candidate} onChange={e => setCandidate(e.target.value)}><option value="">Выберите соискателя</option>{workspace.people.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</StyledSelect></label><button className="pill primary" disabled={!candidate} onClick={() => action(() => native('/employers/tasks/' + selected.id + '/assign', 'POST', { candidate_ids: [candidate] })).then(() => inspect(selected)).catch(() => {})}>Назначить</button>{assignments.map(a => <article className="fsp-row" key={a.id}><div><b>{a.display_name}</b><p>{statuses[a.status]}</p><pre className="fsp-result">{a.answer || 'Решение ещё не отправлено'}</pre><GitReport report={a.eval_details}/></div>{['submitted','reviewed'].includes(a.status) && <div><label className="field"><span>Оценка, %</span><input type="number" min={0} max={100} value={scores[a.id] ?? Math.round((a.reviewer_score ?? a.auto_score ?? 0) * 100)} onChange={e => setScores({ ...scores, [a.id]: e.target.value })} /></label><button className="pill primary" onClick={() => action(() => native('/employers/tasks/assignments/' + a.id, 'PATCH', { score: Number(scores[a.id] ?? Math.round((a.reviewer_score ?? a.auto_score ?? 0) * 100)) / 100 })).then(() => inspect(selected)).catch(() => {})}>Сохранить оценку</button></div>}</article>)}</> : <><p className="preserve">{selected.statement}</p><GitReport report={selected.eval_details} status={selected.status} score={selected.score}/>{selected.status==='evaluating'&&<p role="status">Проверка репозитория выполняется. Результат появится автоматически.</p>}{selected.status === 'assigned' && (!selected.clock || selected.clock.deadlineAt>clockNow) && <>{!selected.practice_id&&!['hiring','qualification'].includes(selected.purpose)&&<label className="field"><span>Решение, от 20 символов</span><textarea value={answer} maxLength={8000} onChange={e => setAnswer(e.target.value)} /></label>}{!selected.practice_id&&<><label className="field"><span>Или репозиторий GitHub для объёмного задания</span><input type="url" placeholder="https://github.com/owner/repo" value={repo} maxLength={300} onChange={e=>setRepo(e.target.value)}/></label><label className="field"><span>Ветка или тег (необязательно)</span><input value={ref} maxLength={100} onChange={e=>setRef(e.target.value)}/></label></>}{selected.practice_id && <Suspense fallback={<p>Загрузка редактора…</p>}><CodeEditor theme={theme} storageKey={"company-task-"+selected.id} initialCode={selected.check?.source_code} initialLanguage={selected.check?.language_id} practiceId={selected.practice_id} checkUrl={"/api/practice/assignment/"+selected.id+"/check"} onCodeChange={setAnswer} onResult={setAlgorithmCheck} /></Suspense>}<button className="pill primary" disabled={selected.practice_id?(!algorithmCheck?.solved||algorithmCheck.source_code!==answer):!repo.trim()&&answer.trim().length < 20} onClick={() => action(() => native('/candidates/me/tasks/' + selected.id + '/submit', 'POST', repo.trim()?{repo_url:repo.trim(),ref:ref.trim()||null}:{ answer })).then(() => { setSelected(null); refresh();window.dispatchEvent(new Event('rewards-changed')); }).catch(() => {})}>Отправить решение</button></>}</>}</section>}</>;
}








