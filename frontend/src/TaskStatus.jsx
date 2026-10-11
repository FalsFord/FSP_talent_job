export const evaluationLabels={checking:'Проверяется',unavailable:'Проверка недоступна',failed:'Не пройдено',awaiting_employer:'Ожидает решения работодателя',passed:'Пройдено',expired:'Время истекло',assigned:'Назначено'};
export function gitStatus(report,status,score){
 if(status==='evaluating')return 'checking';
 if(status==='reviewed')return score>=.7?'passed':'failed';
 if(report?.error)return 'unavailable';
 if(report?.score!=null&&report.score<.7)return 'failed';
 return 'awaiting_employer';
}
