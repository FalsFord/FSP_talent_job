export function taskIssues(t){
  const issues=[];const title=(t.title||'').trim(),condition=(t.condition||t.statement||'').trim();
  if(title.length<3||/^новое задание(?:\s*\d+)?$/i.test(title))issues.push('Укажите название');
  if(condition.length<10||condition==='Опишите задачу и требования к решению.')issues.push('Заполните условие');
  if(t.practice_id?.startsWith('custom:')||t.purpose==='practice'&&!t.practice_id){
    let tests;try{tests=JSON.parse(t.tests_json||'[]')}catch{}
    if(!Array.isArray(tests)||tests.length<1||tests.length>20||tests.some(v=>typeof v?.input!=='string'||typeof v?.output!=='string'||(!v.input.trim()&&!v.output.trim())||v.input.length>20000||v.output.length>20000))issues.push('Добавьте заполненные проверочные тесты');
  }else if(!t.practice_id && !(t.criteria||'').trim() && !(t.rubric||[]).length)issues.push('Укажите критерии оценки');
  return issues;
}
