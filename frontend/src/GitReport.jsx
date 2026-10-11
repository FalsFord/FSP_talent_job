import React from 'react';
import {evaluationLabels,gitStatus} from './TaskStatus';
const names={structure:'Структура',history:'История коммитов',quality:'Качество кода',tests:'Тесты',rubric:'Критерии задания',secrets:'Секреты'};
export default function GitReport({report,status,score}) {
  const label=evaluationLabels[gitStatus(report,status,score)];
  if(status==='evaluating')return <p role="status" className="notice-box">Проверяется репозиторий. Результат появится автоматически.</p>;
  if(!report)return null;
  if(report.error)return <div role="status" className="notice-box">{status==='reviewed'&&<p><b>{label} · оценка работодателя {Math.round(score*100)}%</b></p>}<p>Автопроверка недоступна: {report.error.message}. Решение доступно работодателю для ручной оценки.</p></div>;
  if(report.score==null)return <p className="muted">Репозиторий ожидает проверки.</p>;
  return <div className="notice-box"><h3>{label} · {Math.round(report.score*100)}%</h3><p>Предварительная рекомендация. Итоговую оценку выставляет работодатель.</p><p className="muted">Проверка тестов анализирует их наличие и содержимое. Код проекта не запускается.</p>{report.repo&&<p><a href={report.repo.url} target="_blank" rel="noreferrer">Репозиторий</a> · {report.repo.head_sha?.slice(0,12)}</p>}{report.summary?.map((s,i)=><p key={i}>{s}</p>)}<details><summary>Подробности проверки</summary>{Object.entries(report.breakdown||{}).map(([key,row])=><div key={key}><b>{names[key]||key} · {row.score==null?'Не оценено':Math.round(row.score*100)+'%'}</b>{row.findings?.map((f,i)=><p key={i}>{f.text}</p>)}</div>)}</details></div>;
}
