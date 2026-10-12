import StyledSelect from './StyledSelect';
import Rewards from './Rewards';
import React, {lazy, Suspense, useEffect, useState} from 'react';
import {api} from './api';
const CodeEditor = lazy(()=>import('./CodeEditor'));

export default function Practice({theme}) {
  const [tasks,setTasks]=useState([]), [selected,setSelected]=useState(null), [error,setError]=useState(''), [hint,setHint]=useState(false), [result,setResult]=useState(null), [loading,setLoading]=useState(true);
  function load() { setLoading(true);setError('');api('/api/practice').then(setTasks).catch(e=>setError(e.message)).finally(()=>setLoading(false)); }
  useEffect(load,[]);
  const task=tasks.find(t=>t.id===selected);
  return <><div className="page-title"><div><span className="mono accent-text">УЧИСЬ И ПРОБУЙ</span><h1>Практика алгоритмов</h1><p className="muted">Короткие задачи с автоматической проверкой. Практика помогает учиться и не меняет подтверждённую квалификацию.</p></div><span className="tag">{tasks.filter(t=>t.progress?.solved).length} / {tasks.length} решено</span></div>
    {error && <div role="alert" className="notice-box"><p>{error}</p><button className="pill secondary" disabled={loading} onClick={load}>Повторить загрузку</button></div>}
    {loading && !tasks.length && <p role="status" className="notice-box">Подготавливаем алгоритмы из базы знаний и проверяем тесты. Это может занять немного времени.</p>}
    {tasks[0]?.generation_notice && <div role="status" className="notice-box"><p>{tasks[0].generation_notice}</p><button className="pill secondary" disabled={loading} onClick={load}>Повторить генерацию набора</button></div>}
    <Rewards variant="daily" /><KnowledgeQuiz />
    <div className="section-heading"><h2>Алгоритмы на сегодня</h2><span className="mono muted">Новый набор ежедневно · RAG</span></div>
    <div className="practice-grid">{tasks.map(t=><button key={t.id} className={'card practice-card '+(selected===t.id?'selected':'')} onClick={()=>{setSelected(t.id);setHint(false);setResult(null);}}><span className="mono accent-text">{t.topic} · {t.level}</span><h2>{t.title}</h2><p className="muted">{t.progress?.solved?'Решено · '+t.progress.daily_assessment?.score+' / 100':'Решить на сайте →'}</p></button>)}</div>
    {task && <><section className="card fsp-card"><div className="section-heading"><h2>{task.title}</h2><span className="tag">2 секунды · 128 МБ</span></div><p>{task.statement}</p><div className="practice-examples"><div><b>Ввод</b><pre>{task.example.input}</pre></div><div><b>Вывод</b><pre>{task.example.output}</pre></div></div><p className="muted">Программа читает стандартный ввод и печатает только ответ. Кнопка запуска проверяет решение на наборе тестов.</p><button className="pill secondary" onClick={()=>setHint(!hint)}>{hint?'Скрыть подсказку':'Показать подсказку'}</button>{hint&&<p className="notice-box">{task.hint}</p>}{result&&<p role="status" className="notice-box">{result.solved?'Отлично, задача решена!':'Попробуйте исправить решение.'} Пройдено {result.passed} из {result.total} тестов.</p>}</section>
    {task.sources?.length>0&&<p className="mono muted">Темы из базы знаний: {task.sources.join('; ')}</p>}
    <AlgorithmAssessment report={result?.daily_assessment||result?.assessment||task.progress?.daily_assessment} saved={!!(result?.daily_assessment||task.progress?.daily_assessment)} />
    <Suspense fallback={<p>Загружаем редактор…</p>}><CodeEditor key={task.id} theme={theme} storageKey={'practice-'+task.id} practiceId={task.id} onResult={r=>{setResult(r);load();window.dispatchEvent(new Event('rewards-changed'));}} /></Suspense></>}
  </>;
}

function AlgorithmAssessment({report,saved}) {
  if(!report)return null;
  return <section className="card fsp-card"><div className="section-heading"><h2>{saved?'Оценка ежедневного решения':'Результат попытки'}</h2><span className="tag">{report.score} / 100</span></div><div className="practice-metrics"><div><span className="muted">Время выполнения</span><b>{report.time_seconds==null?'Нет данных':report.time_seconds+' с'}</b></div><div><span className="muted">Пиковая память</span><b>{report.memory_kb==null?'Нет данных':(report.memory_kb/1024).toFixed(1)+' МБ'}</b></div><div><span className="muted">Проверки с синтаксическими ошибками</span><b>{report.syntax_errors}</b></div><div><span className="muted">Предполагаемая сложность</span><b>{report.complexity.estimate||'Недостаточно данных'}</b></div></div><p className="muted">{report.complexity.method}</p><details><summary>Как рассчитана оценка</summary><p className="muted">{report.note}</p><p>Тесты: {report.components.correctness}/60 · Время: {report.components.time}/20 · Память: {report.components.memory}/10 · Синтаксис: {report.components.syntax}/10</p></details>{saved&&<p className="mono muted">Сохранено первое успешное решение. Повторные запуски оценку не меняют.</p>}</section>;
}

function KnowledgeQuiz() {
  const [language,setLanguage]=useState('python'), [session,setSession]=useState(null), [questions,setQuestions]=useState([]), [answers,setAnswers]=useState({}), [result,setResult]=useState(null), [busy,setBusy]=useState(false), [error,setError]=useState('');
  async function start() {
    setBusy(true);setError('');setResult(null);
    try { const s=await api('/api/learning/start',{method:'POST',body:{language}});setSession(s);setQuestions(s.questions);setAnswers(s.answers||{}); }
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function finish() {
    setBusy(true);setError('');
    try {setResult(await api('/api/learning/'+session.id+'/submit',{method:'POST',body:{answers}}));setSession(null);window.dispatchEvent(new Event('rewards-changed'));}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <section className="card fsp-card"><h2>Разминка по знаниям</h2><p className="muted">Пять вопросов с объяснениями. Учебная попытка не изменяет уровень профиля.</p><div className="actions"><label className="field"><span>Направление</span><StyledSelect value={language} onChange={e=>setLanguage(e.target.value)} disabled={!!session}><option value="python">Python</option><option value="java">Java</option><option value="sql">SQL</option></StyledSelect></label><button className="pill primary" disabled={busy||!!session} onClick={start}>{busy?'Загрузка…':'Начать разминку'}</button></div>{error&&<p role="alert">{error}</p>}{session&&<>{questions.map(q=><article className="fsp-row" key={q.id}><div><p>{q.statement}</p><div className="fsp-options">{q.options.map((option,i)=><label key={i}><input type={q.kind==='quiz_multi'?'checkbox':'radio'} name={q.id} checked={q.kind==='quiz_multi'?(answers[q.id]||[]).includes(option):answers[q.id]===option} onChange={()=>{const value=q.kind==='quiz_multi'?((answers[q.id]||[]).includes(option)?answers[q.id].filter(o=>o!==option):[...(answers[q.id]||[]),option]):option;const next={...answers,[q.id]:value};setAnswers(next);api('/api/learning/'+session.id+'/answers',{method:'PUT',body:{answers:next}}).catch(e=>setError(e.message));}} /> {typeof option==='string'?option:option.text}</label>)}</div></div></article>)}<button disabled={busy||questions.some(q=>answers[q.id]==null)} className="pill primary" onClick={finish}>Проверить ответы</button></>}{result&&<div className="notice-box"><h3>{result.correct} из {result.total} верно</h3>{result.items.map((item,i)=><p key={i}>{item.passed?'✓':'○'} {item.statement}<br/><span className="muted">{item.explanation || 'Повторите тему и попробуйте ещё раз.'}</span></p>)}</div>}</section>;
}
