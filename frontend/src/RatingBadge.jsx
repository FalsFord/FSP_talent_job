import React from 'react';
import {ChartNoAxesColumnIncreasing, Award} from 'lucide-react';

export default function RatingBadge({value,level}) {
  if(value==null||!Number.isFinite(Number(value)))return null;
  const rating=Number(value).toLocaleString('ru-RU',{maximumFractionDigits:2});
  return <span className="candidate-progress"><span className="candidate-rating" title="Рейтинг учитывает квалификацию, результаты заданий и достижения ФСП"><ChartNoAxesColumnIncreasing size={16} aria-hidden="true"/><span>Рейтинг <b>{rating} / 100</b></span></span>{level!=null&&<span className="candidate-rating candidate-level" title="Уровень за ежедневные задания и накопленный опыт XP"><Award size={16} aria-hidden="true"/><span>Уровень <b>{level}</b></span></span>}</span>;
}
