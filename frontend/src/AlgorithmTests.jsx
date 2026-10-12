import React from 'react';
export default function AlgorithmTests({value,onChange}) {
  let tests=[];try{tests=JSON.parse(value||'[]')}catch{}
  if(!Array.isArray(tests))tests=[];
  if(!tests.length)tests=[{input:'',output:''}];
  function edit(index,key,text){onChange(JSON.stringify(tests.map((t,i)=>i===index?{...t,[key]:text}:t)))}
  return <div className="manual-algorithm-tests"><h3>Проверочные тесты</h3><p className="muted">Добавьте входные данные и точный ответ программы. Соискатель не увидит ответы этих тестов.</p>{tests.map((t,i)=><div className="manual-test-case" key={i}><div className="section-heading"><b>Тест {i+1}</b>{tests.length>1&&<button type="button" className="text-button" onClick={()=>onChange(JSON.stringify(tests.filter((_,j)=>i!==j)))}>Удалить тест</button>}</div><label className="field"><span>Ввод</span><textarea maxLength={20000} value={t.input} onChange={e=>edit(i,'input',e.target.value)}/></label><label className="field"><span>Ожидаемый вывод</span><textarea maxLength={20000} value={t.output} onChange={e=>edit(i,'output',e.target.value)}/></label></div>)}<button type="button" className="pill secondary" disabled={tests.length>=20} onClick={()=>onChange(JSON.stringify([...tests,{input:'',output:''}]))}>Добавить тест</button></div>;
}
