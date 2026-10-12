"""Local resume extraction. PDF contents are never sent to an external model."""
import asyncio
import json
import re
import sys
from datetime import date
from io import BytesIO
from pydantic import BaseModel, Field


class WorkExperience(BaseModel):
    company: str = Field(default='', max_length=200)
    position: str = Field(default='', max_length=200)
    period: str = Field(default='', max_length=150)
    description: str = Field(default='', max_length=5000)


SKILLS=('Python','JavaScript','TypeScript','Java','C++','C#','Go','PHP','SQL','PostgreSQL','MySQL','Redis','Docker','Kubernetes','React','Vue','Angular','FastAPI','Django','Flask','Spring','Git','Linux','HTML','CSS','REST','GraphQL','MongoDB')
CITIES=re.compile(r'^(Москва|Санкт-Петербург|Казань|Новосибирск|Екатеринбург|Нижний Новгород|Самара|Ростов-на-Дону|Уфа|Краснодар|Пермь|Воронеж|Челябинск|Омск|Красноярск|Волгоград)(?:,|$)')
HEADINGS=r'образование|education|ключевые навыки|skills|навыки|обо мне|about me|дополнительная информация|сертификаты|certifications|языки|languages'
PERIOD=re.compile(r'(?i)(?:(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]|january|february|march|april|may|june|july|august|september|october|november|december|\d{1,2}[./])\s*)?(?:19|20)\d{2}\s*[—–-]\s*(?:(?:(?:[а-яa-z]+|\d{1,2}[./])\s*)?(?:19|20)\d{2}|(?:по\s+)?настоящее время|по настоящее время|present|current)')


def parse_text(text):
    lines=[re.sub(r'\s+',' ',line).strip() for line in text.splitlines() if line.strip()]
    fields={}
    name=re.search(r'(?im)^(?:фио|full name|name)\s*[:—-]\s*([^\n]{3,150})',text)
    if name:
        parts=name[1].split()
        if len(parts)>=2:
            fields.update(name=parts[1] if re.search('[А-Яа-я]',name[1]) else parts[0],surname=parts[0] if re.search('[А-Яа-я]',name[1]) else parts[-1])
            if len(parts)==3 and re.search('[А-Яа-я]',name[1]): fields['patronymic']=parts[2]
    elif lines and re.fullmatch(r'[А-ЯЁ][а-яё-]+ [А-ЯЁ][а-яё-]+(?: [А-ЯЁ][а-яё-]+)?',lines[0]):
        parts=lines[0].split();fields.update(surname=parts[0],name=parts[1])
        if len(parts)==3: fields['patronymic']=parts[2]
    for key,label in [('city',r'город|city|проживает'),('role',r'должность|position|желаемая должность|headline')]:
        match=re.search(rf'(?im)^(?:{label})\s*[:—-]\s*([^\n]{{2,200}})',text)
        if match: fields[key]=match[1].strip()[:128 if key=='city' else 200]
    if not fields.get('role'):
        desired=re.search(r'(?im)^желаемая должность[^\n]*\n([^\n]{2,200})',text)
        if desired: fields['role']=desired[1].strip()
    if not fields.get('city'):
        city=next((match for line in lines[:20] if (match:=CITIES.match(line))),None)
        if city: fields['city']=city[1]
    phone=re.search(r'(?<!\d)(?:\+7|8)[\s(.-]*\d{3}[\s).—-]*\d{3}[\s.—-]*\d{2}[\s.—-]*\d{2}(?!\d)',text)
    if phone: fields['phone']=phone[0]
    email=re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}',text)
    if email: fields['contact_email']=email[0]
    fields['tech']=[skill for skill in SKILLS if re.search(r'(?<![\w+#])'+re.escape(skill)+r'(?![\w+#])',text,re.I)]
    about=re.search(rf'(?ims)^(?:обо мне|about me|summary)\s*[:—-]?\s*\n(.+?)(?=\n(?:{HEADINGS}|опыт работы|experience)\s*[:—-]?|\Z)',text)
    if about: fields['about']=about[1].strip()[:5000]
    section=re.search(rf'(?ims)^(?:опыт работы|work experience|employment history)\b[^\n]*\n(.*?)(?=\n(?:{HEADINGS})\s*[:—-]?\s*\n|\Z)',text)
    jobs=[]
    if section:
        block=section[1];periods=list(PERIOD.finditer(block))
        for index,match in enumerate(periods[:30]):
            tail=block[match.end():periods[index+1].start() if index+1<len(periods) else len(block)]
            parts=[line.strip() for line in tail.splitlines() if line.strip()]
            parts=[p for p in parts if not re.fullmatch(r'\d+\s+(?:год\w*|лет|месяц\w*)(?:\s+\d+\s+месяц\w*)?',p)]
            if parts:
                position=next((i for i,p in enumerate(parts[1:],1) if re.search(r'(?i)разработчик|инженер|аналитик|менеджер|дизайнер|программист|developer|engineer|analyst',p)),1 if len(parts)>1 else 0)
                jobs.append(WorkExperience(company=parts[0][:200],position=parts[position][:200] if position else '',period=match[0][:150],description='\n'.join(parts[position+1:])[:5000]).model_dump())
        duration=re.search(r'(?i)опыт работы\s*[:—–-]?\s*(\d+)\s*(?:лет|год)',text)
        if duration:
            years=int(duration[1]);fields['experience']='5+ лет' if years>=5 else f'{years} года' if years in (2,3,4) else '1 год' if years==1 else 'Без опыта'
        elif jobs:
            active_years=set()
            for job in jobs:
                years=re.findall(r'(?:19|20)\d{2}',job['period'])
                if years:
                    start=int(years[0]);end=int(years[1]) if len(years)>1 else date.today().year
                    active_years.update(range(start,max(start,end)))
            total=len(active_years)
            fields['experience']='5+ лет' if total>=5 else f'{total} года' if total in (2,3,4) else '1 год' if total==1 else 'Менее года'
    fields['work_experience']=jobs
    return {k:v for k,v in fields.items() if v}


def extract_pdf(content):
    from pypdf import PdfReader
    try:
        reader=PdfReader(BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(''):
            return {'status':'encrypted','message':'PDF защищён паролем. Загрузите копию без пароля.','fields':{}}
        if len(reader.pages)>30:
            return {'status':'too_large','message':'Для заполнения профиля нужен PDF до 30 страниц.','fields':{}}
        text='\n'.join((page.extract_text() or '')[:15000] for page in reader.pages)[:200000]
        if len(text.strip())<30:
            return {'status':'no_text','message':'В PDF нет читаемого текста. Для скана нужна текстовая версия резюме.','fields':{}}
        fields=parse_text(text)
        return {'status':'parsed','message':'Проверьте распознанные данные и опыт работы.','fields':fields}
    except Exception:
        return {'status':'invalid','message':'Не удалось прочитать PDF. Файл сохранён; заполните профиль вручную.','fields':{}}


async def parse_pdf_file(path):
    process=await asyncio.create_subprocess_exec(sys.executable,'-m','app.services.resume_parser_worker',str(path),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
    try:
        output,_=await asyncio.wait_for(process.communicate(),timeout=20)
        if process.returncode==0: return json.loads(output)
    except asyncio.TimeoutError:
        process.kill();await process.communicate()
    except (ValueError,TypeError): pass
    return {'status':'failed','message':'Не удалось обработать PDF за отведённое время. Файл сохранён.','fields':{}}
