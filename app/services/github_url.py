from urllib.parse import urlsplit,unquote
import re
from app.core.errors import DomainError

def normalize_repository(value):
    value=value.strip()
    if value.startswith(('github.com/','www.github.com/')):value='https://'+value
    try:
        url=urlsplit(value)
        parts=url.path.strip('/').split('/')
        if url.scheme!='https' or url.hostname not in ('github.com','www.github.com') or url.username or url.password or url.port or url.query or url.fragment:raise ValueError()
        if len(parts)<2 or not re.fullmatch(r'[A-Za-z0-9_.-]+',parts[0]) or not re.fullmatch(r'[A-Za-z0-9_.-]+',parts[1]):raise ValueError()
        repo=parts[1].removesuffix('.git')
        if not repo or repo in ('.','..'):raise ValueError()
        ref=None
        if len(parts)>2:
            if parts[2]!='tree' or len(parts)<4:raise ValueError()
            ref=unquote('/'.join(parts[3:]))
            if len(ref)>100 or any(c.isspace() for c in ref) or '..' in ref or ref.startswith('/'):raise ValueError()
        return 'https://github.com/'+parts[0]+'/'+repo,ref
    except ValueError:
        raise DomainError('BAD_REPO_URL','Прикрепите ссылку на репозиторий GitHub или его ветку: https://github.com/владелец/репозиторий',422)
