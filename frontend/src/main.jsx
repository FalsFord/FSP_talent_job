import StyledSelect from './StyledSelect';
import Hackathons from './Hackathons';
import OfferActions from './OfferActions';
import AccountDeletion from './AccountDeletion';
import GithubAttachment,{validRepository} from './GithubAttachment';
import RegistrationNotice from './RegistrationNotice';
import GitReport from './GitReport';
import RatingBadge from './RatingBadge';
import Rewards from './Rewards';
import GenerationWallet from './GenerationWallet';
import AlgorithmTests from './AlgorithmTests';
import {taskIssues} from './taskReadiness';
import React, { useState, useEffect, useRef, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import {
  Sun,
  Moon,
  ArrowLeft,
  MessageCircle,
  Send,
  Star,
  X,
  Check,
  Menu,
  Bell,
  Settings,
  Clock,
  Plus,
  Trash2,
  GripVertical,
  UserRound,
} from "lucide-react";
const WorkPage = lazy(() => import("./FspPanel"));
const KnowledgeAdmin = lazy(() => import("./KnowledgeAdmin"));
const Practice = lazy(() => import("./Practice"));
const CodeEditor = lazy(() => import("./CodeEditor"));
function CodeWorkspace(props) {
  return (
    <Suspense
      fallback={<div className="card empty-state">Загрузка редактора…</div>}
    >
      <CodeEditor key={props.storageKey} {...props} />
    </Suspense>
  );
}
import "./style.css";
import AuthRoot, { PasswordDialog } from "./Auth";
import {
  api,
  useRemoteState,
  useMessages,
  flushWrites,
  discardWrites,
  openPrivateFile,
  previewPrivateFile,
  PrivateImage,
  useOfferChat,
  sendChatMessage,
} from "./api";

const asset = "/assets/figma/";
const icons = {
  user: "4a102.svg",
  file: "e0656.svg",
  sliders: "04cfe.svg",
  code: "7d9e7.svg",
  arrow: "d01eb.svg",
  check: "734e3.svg",
  search: "73d8e.svg",
  sparkles: "73455.svg",
  pencil: "d873a.svg",
  eye: "fbcf6.svg",
};
function Icon({ name }) {
  return <img className="design-icon" alt="" src={asset + icons[name]} />;
}
const candidateSteps = [
  "Начало",
  "Данные о себе",
  "Резюме",
  "Роль и предпочтения",
  "Тест на грейд",
  "Готовый профиль",
];
const employerSteps = [
  "Начало",
  "Компания",
  "Роль и найм",
  "Задачи и требования",
  "Условия и отбор",
  "Готовая вакансия",
];
const stack = [
  "Python",
  "Golang",
  "PostgreSQL",
  "Redis",
  "RabbitMQ",
  "Docker",
  "Kubernetes",
  "gRPC",
  "CI/CD",
];
function read(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}
function useSaved(key, initial) {
  const [value, set] = useState(() => read(key, initial));
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.warn("Не удалось сохранить черновик:", error.name);
    }
  }, [value, key]);
  return [value, set];
}
function navigate(path) {
  location.hash = path;
}
function Button({
  children,
  onClick,
  secondary = false,
  type = "button",
  disabled = false,
  ...rest
}) {
  return (
    <button
      className={"pill " + (secondary ? "secondary" : "primary")}
      type={type}
      onClick={onClick}
      disabled={disabled}
      {...rest}
    >
      {children}
    </button>
  );
}
function Tags({ items }) {
  return (
    <div className="tags">
      {items.map((t) => (
        <span key={t}>{t}</span>
      ))}
    </div>
  );
}
function Field({
  label,
  value,
  onChange,
  options,
  area = false,
  required = false,
  type = "text",
  ...rest
}) {
  return (
    <label className={"field " + (area ? "wide" : "")}>
      <span>
        {label}
        {required ? " *" : ""}
      </span>
      {options ? (
        <StyledSelect
          value={value}
          onChange={(e) => onChange(e.target.value)}
          {...rest}
        >
          {options.map((v) => (
            <option key={typeof v === "object" ? v.value : v} value={typeof v === "object" ? v.value : v}>{typeof v === "object" ? v.label : v}</option>
          ))}
        </StyledSelect>
      ) : area ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          {...rest}
        />
      ) : (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          {...rest}
        />
      )}
    </label>
  );
}
function Choices({ items, value, onChange, multiple = false }) {
  return (
    <div className="choices">
      {items.map((t) => (
        <button
          type="button"
          key={t}
          aria-pressed={multiple ? value.includes(t) : value === t}
          className={
            (multiple ? value.includes(t) : value === t) ? "chosen" : ""
          }
          onClick={() =>
            onChange(
              multiple
                ? value.includes(t)
                  ? value.filter((v) => v !== t)
                  : [...value, t]
                : t,
            )
          }
        >
          {t}
        </button>
      ))}
    </div>
  );
}
function App({ workspace, authUser, onLogout, reloadWorkspace }) {
  const [route, setRoute] = useState(
    location.hash.slice(1).split("?")[0] || "/candidate/start",
  );
  const [theme, setTheme] = useSaved("endpoint-theme", "light");
  const employer = authUser.role === "employer";
  const [profile, setProfile] = useRemoteState(
    workspace.profile,
    employer ? null : "/api/me/profile",
  );
  const [vacancy, setVacancy] = useRemoteState(
    workspace.vacancy,
    employer ? "/api/me/vacancy" : null,
    {preserveEdits:true},
  );
  const [tasks, setTasks] = useRemoteState(
    workspace.tasks,
    employer ? "/api/me/tasks" : null,
  );
  const [offerStatuses, setOfferStatuses] = useRemoteState(
    workspace.offerStatuses,
    employer ? null : "/api/me/offer-statuses",
  );
  const [sent, setSent] = useRemoteState(workspace.sent, null);
  const [favorites, setFavorites] = useRemoteState(
    workspace.favorites,
    employer ? "/api/me/favorites" : null,
  );
  const [messages, setMessages] = useMessages(workspace.messages,workspace.chat_deleted_until);
  const [assessment, setAssessment] = useRemoteState(
    workspace.assessment,
    employer ? null : "/api/me/assessments/grade",
  );
  const [assignment, setAssignment] = useRemoteState(
    workspace.assignment,
    employer ? null : "/api/me/assessments/assignment",
  );
  const [notice, setNotice] = useState(""),
    [modal, setModal] = useState(null),
    [menu, setMenu] = useState(false);
  useEffect(() => {
    if (!route.startsWith("/" + authUser.role + "/"))
      navigate(
        authUser.role === "admin" ? "/admin/knowledge" : employer
          ? "/employer/dashboard"
          : profile.complete
            ? "/candidate/inbox"
            : "/candidate/start",
      );
  }, [route, authUser.role]);
  useEffect(() => {
    const handler = (e) => setNotice(e.detail);
    addEventListener("api-save-error", handler);
    return () => removeEventListener("api-save-error", handler);
  }, []);
  useEffect(() => {
    const change = () => {
      setRoute(location.hash.slice(1).split("?")[0] || "/candidate/start");
      setMenu(false);
      window.scrollTo(0, 0);
    };
    addEventListener("hashchange", change);
    return () => removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [theme]);
  useEffect(() => {
    if (notice) {
      const id = setTimeout(() => setNotice(""), 4500);
      return () => clearTimeout(id);
    }
  }, [notice]);

  const notify = (text) => setNotice(text);
  const patchProfile = (k, v) => setProfile((p) => ({ ...p, [k]: v }));
  const patchVacancy = (k, v) => setVacancy((p) => ({ ...p, [k]: v }));
  async function completeRegistration() {
    await flushWrites('/api/me/profile');
    const saved = await api('/api/me/registration/complete', {method:'POST'});
    setProfile(saved,{persist:false});
    await reloadWorkspace();
    return saved;
  }
  async function sendOffer(candidate_id) {
    await flushWrites();
    const offer = await api("/api/offers", {
      method: "POST",
      body: { candidate_id, vacancy_id: vacancy.id },
    });
    await reloadWorkspace();
    return offer;
  }
  async function sendMessage(id, text) {
    return sendChatMessage(id, text);
  }
  async function uploadProfile(kind, file) {
    try {
      await flushWrites();
      const body = new FormData();
      body.append("file", file);
      const data = await api("/api/me/files/" + kind, { method: "POST", body });
      if(kind==='logo'){await reloadWorkspace();}else setProfile(data);
      notify(kind === 'resume' ? data.resume_parse?.message || 'Резюме сохранено' : 'Файл сохранён в аккаунте');
    } catch (e) {
      notify(e.message);
    }
  }
  async function applyResume() {
    await flushWrites();
    const data = await api('/api/me/resume/apply', {method:'POST'});
    setProfile(data);
    notify('Поля заполнены из PDF. Проверьте данные профиля.');
  }
  async function createNewVacancy() {
    try {
      await flushWrites(['/api/me/vacancy','/api/me/tasks']);
      await api("/api/vacancies", { method: "POST" });
      navigate("/employer/company");
      await reloadWorkspace();
    } catch (e) {
      notify(e.message);
    }
  }
  async function generateTasks(options = {}) {
    await flushWrites();
    const data = await api("/api/me/tasks/generate", { method: "POST", body: options });
    setTasks(data);
    return data;
  }
  const context = {
    vacancies: workspace.vacancies || [],
    selectVacancy: async (vacancy_id) => {
      try {
        await flushWrites(['/api/me/vacancy','/api/me/tasks']);
        await api("/api/me/active-vacancy", {
          method: "PUT",
          body: { vacancy_id },
        });
        await reloadWorkspace();
      } catch (e) {
        notify(e.message);
      }
    },
    publishVacancy: async () => {
      await flushWrites('/api/me/vacancy');
      const id=vacancy.id || (await reloadWorkspace()).vacancy.id;
      const saved=await api('/api/me/vacancy/publish',{method:'POST',body:{id}});
      setVacancy(saved,{persist:false});
      await reloadWorkspace();
      return saved;
    },
    people: workspace.people,
    offers: workspace.offers,
    gradeTasks: workspace.gradeTasks,
    taskNames: workspace.gradeTasks.map((t) => t.title),
    authUser,
    sendOffer,
    sendMessage,
    uploadProfile,
    applyResume,
    createNewVacancy,
    generateTasks,
    reloadWorkspace,
    completeRegistration,
    generationFocus: workspace.generationFocus,
    hiddenChatIds: workspace.hidden_chat_ids || [],
    profile,
    vacancy,
    tasks,
    setTasks,
    offerStatuses,
    setOfferStatuses,
    sent,
    setSent,
    favorites,
    setFavorites,
    messages,
    setMessages,
    assessment,
    setAssessment,
    patchProfile,
    patchVacancy,
    notify,
    setModal,
    theme,
    assignment,
    setAssignment,
  };
  const nav = authUser.role === "admin" ? [] : employer
    ? [
        ["Соискатели", "/employer/dashboard"],
        ["Тестовые задания", "/employer/builder"],
      ]
    : [
        ["Редактор кода", "/candidate/playground"],
      ];
  if (authUser.role === 'candidate') nav.push(['Вакансии','/candidate/vacancies'], ['Практика','/candidate/practice'], ['Квалификация','/candidate/development'], ['Задания компаний','/candidate/tasks']);
  if (employer) nav.push(['Отклики','/employer/applications'], ['Проверка решений','/employer/tasks'], ['Хакатоны ФСП','/employer/hackathons']);
  if (authUser.role === 'admin') nav.push(['База знаний','/admin/knowledge']);
  let page;
  if (
    /^\/(candidate|employer)\/(start|about|resume|preferences|test|result|company|role|requirements|conditions|review)$/.test(
      route,
    )
  )
    page = <Onboarding route={route} {...context} />;
  else if (route === '/admin/knowledge') page = <Suspense fallback={<p>Загрузка…</p>}><KnowledgeAdmin /></Suspense>;
  else if (route === '/candidate/practice') page = <Suspense fallback={<div className="card">Загрузка…</div>}><Practice theme={theme} /></Suspense>;
  else if (/\/(services|vacancies|applications|tasks|settings|development|notifications)$/.test(route)) page = <Suspense fallback={<div className="card">Загрузка…</div>}><WorkPage key={route} section={route.split('/').pop()} theme={theme} authUser={authUser} notify={notify} reloadWorkspace={reloadWorkspace} workspace={workspace} startCompanyTask={async offer=>{await flushWrites();const progress=await api('/api/offers/'+offer.id+'/assignment/start',{method:'POST'});setAssignment(progress,{persist:false});navigate('/candidate/assignment');}} /></Suspense>;
  else if ((route === "/employer/dashboard" || route === "/employer/needs")) page = <Dashboard {...context} />;
  else if (route === "/employer/hackathons" && employer) page = <Hackathons />;
  else if (route === "/employer/builder") page = <Builder {...context} />;
  else if (route.includes("/chat/")) page = <Chat route={route} {...context} />;
  else if (route.includes("/offer/"))
    page = <OfferDetail route={route} {...context} />;
  else if (route.includes("/person/"))
    page = <PersonDetail key={route} route={route} {...context} />;
  else if (route.endsWith("/inbox"))
    page = <Inbox employer={employer} {...context} />;
  else if (route === "/candidate/profile") page = <Profile {...context} />;
  else if (route === "/candidate/assessment")
    page = <Assessment {...context} />;
  else if (route === "/candidate/assignment")
    page = (
      <Assessment
        {...context}
        key={assignment?.offerId || 'company-assignment'}
        assigned
        tasks={
          workspace.offers.find((o) => o.id === String(assignment?.offerId))
            ?.tasks || []
        }
        assessment={assignment}
        setAssessment={setAssignment}
      />
    );
  else if (route.endsWith("/playground"))
    page = (
      <>
        <PageTitle
          title="Ваше пространство для кода"
          subtitle="Пишите, запускайте и экспериментируйте. Результат, ошибки и время выполнения — в одном месте."
        />
        <div className="editor-context">
          <span>ЗАПУСК КОДА · АВТОСОХРАНЕНИЕ</span>
          <Button
            secondary
            onClick={() =>
              navigate(employer ? "/employer/builder" : "/candidate/test")
            }
          >
            Назад
          </Button>
        </div>
        <CodeWorkspace
          theme={theme}
          storageKey="codespace"
        />
      </>
    );
  else
    page = (
      <div className="card">
        <h1>Страница не найдена</h1>
        <Button onClick={() => navigate("/candidate/start")}>На главную</Button>
      </div>
    );
  return (
    <>
      <header className="site-header">
        <a
          className="logo"
          href={employer ? "#/employer/dashboard" : "#/candidate/start"}
        >
          EndPoint.
        </a>
        <button
          className="mobile-menu"
          aria-label="Меню"
          onClick={() => setMenu(!menu)}
        >
          <Menu />
        </button>
        <nav className={menu ? "opened" : ""}>
          {nav.map(([label, url]) => (
            <a
              key={url}
              href={"#" + url}
              className={route === url ? "active" : ""}
            >
              {label}
            </a>
          ))}
        </nav>
        <div className="header-controls">
          {authUser.role !== 'admin' && <InboxButton role={authUser.role} />}
          <NotificationBell role={authUser.role}/>
          {employer && (
            <a
              className="profile-button"
              href="#/employer/company"
              aria-label="Профиль работодателя"
              title="Профиль работодателя"
            >
              <UserRound size={20} aria-hidden="true" />
            </a>
          )}
          {authUser.role === "candidate" && (
            <a
              className="profile-button"
              href={profile.complete ? "#/candidate/profile" : "#/candidate/start"}
              aria-label="Профиль соискателя"
              title="Профиль соискателя"
            >
              <UserRound size={20} aria-hidden="true" />
            </a>
          )}
          <span className="account-role">
            {authUser.role === "admin" ? "Администратор" : employer ? "Работодатель" : "Соискатель"}
          </span>
          <details className="settings-menu"><summary aria-label="Настройки" title="Настройки"><Settings size={20}/></summary><div className="settings-dropdown">
          {authUser.role === 'candidate' && <a href="#/candidate/settings">Настройки профиля</a>}
          <button
            className="text-button"
            onClick={() =>
              setModal({
                title: "Сменить пароль",
                body: <PasswordDialog onChanged={() => setModal(null)} />,
              })
            }
          >
            Пароль
          </button>
          <button
            className="text-button"
            onClick={() => onLogout().catch((e) => notify(e.message))}
          >
            Выйти
          </button>
          <button className="text-button" onClick={()=>setModal({title:'Удалить аккаунт',body:<AccountDeletion/>})}>Удалить аккаунт</button>
          </div></details>
          <button
            className="theme-button"
            aria-label={
              theme === "light"
                ? "Включить тёмную тему"
                : "Включить светлую тему"
            }
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            {theme === "light" ? <Moon size={19} /> : <Sun size={19} />}
          </button>
        </div>
      </header>
      <main className="site-main">
        {!employer && ['/candidate/profile','/candidate/vacancies','/candidate/inbox'].includes(route) && <RegistrationNotice profile={workspace.profile} completeRegistration={completeRegistration}/>}
        {page}
      </main>
      <footer className="site-footer">
        <a href="#/candidate/start">EndPoint.</a>
        <span>EndPoint · тестовые аккаунты содержат вымышленные данные</span>
        <button
          onClick={() =>
            setModal({
              title: "Нужна помощь?",
              body: "Заполните профиль или создайте вакансию. Профили, резюме, предложения и переписка сохраняются в вашем аккаунте. Код выполняется в изолированной среде.",
            })
          }
        >
          Нужна помощь?
        </button>
      </footer>
      {notice && (
        <div className="toast" role="status">
          <Check size={18} />
          {notice}
          <button
            aria-label="Закрыть уведомление"
            onClick={() => setNotice("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {modal && (
        <div className="modal-backdrop" onClick={() => setModal(null)}>
          <section
            className={'dialog card '+(modal.className||'')}
            role="dialog"
            aria-modal="true"
            aria-label={modal.title}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close"
              aria-label="Закрыть"
              onClick={() => setModal(null)}
            >
              <X />
            </button>
            <h2>{modal.title}</h2>
            {modal.body}
            <div className="actions modal-footer">
              <Button onClick={() => setModal(null)}>Понятно</Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
function PageTitle({ title, subtitle, label }) {
  return (
    <div className="page-title">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {label && <span className="mono muted">{label}</span>}
    </div>
  );
}
const candidateRoutes = [
    "start",
    "about",
    "resume",
    "preferences",
    "test",
    "result",
  ],
  employerRoutes = [
    "start",
    "company",
    "role",
    "requirements",
    "conditions",
    "review",
  ];
function Onboarding(c) {
  const [switchingVacancy, setSwitchingVacancy] = useState(false);
  const [publishing,setPublishing]=useState(false),[publicationError,setPublicationError]=useState('');
  useEffect(()=>setPublicationError(''),[c.vacancy.id]);
  const { taskNames, uploadProfile, authUser } = c;
  const {
    route,
    profile,
    vacancy,
    patchProfile: p,
    patchVacancy: v,
    setModal,
    notify,
    assessment,
  } = c;
  const employer = route.startsWith("/employer"),
    routes = employer ? employerRoutes : candidateRoutes,
    steps = employer ? employerSteps : candidateSteps;
  const step = routes.indexOf(route.split("/")[2]);
  const titles = employer
    ? [
        "Давайте найдём специалистов для вашей команды",
        "Расскажите о компании",
        "Кого вы ищете в команду?",
        "Задачи и требования",
        "Условия и процесс отбора",
        `${vacancy.representative || authUser.name}, вакансия готова к публикации`,
      ]
    : [
        `${profile.name || authUser.name}, начнём с вашего профиля`,
        "Расскажите о себе",
        "Добавьте своё резюме",
        "Какую работу вы ищете?",
        "Узнайте свой предварительный грейд",
        `${profile.name}, ваш профиль готов`,
      ];
  const descriptions = employer
    ? [
        "Расскажите о компании и роли — соберём понятную вакансию для подходящих ИТ-специалистов.",
        "Представьте продукт и команду. Добавьте контакты представителя.",
        "Укажите роль и ключевые параметры — они помогут соискателям оценить соответствие вакансии.",
        "Расскажите, чем будет заниматься будущий коллега и какие навыки ему понадобятся.",
        "Прозрачные условия помогают быстрее найти подходящих специалистов.",
        "Проверьте, как её увидят соискатели. Любой раздел можно изменить до публикации.",
      ]
    : [
        "Поможем найти подходящую работу — с учётом опыта, навыков и того, что важно вам.",
        "Проверьте данные и добавьте контакты, чтобы работодатели могли связаться с вами.",
        "Прикрепите актуальный документ — он дополнит профиль опытом работы и образованием.",
        "Выберите направление, технологии и условия. По ним мы подберём тест и подходящие вакансии.",
        "Тест поможет оценить текущие навыки и точнее настроить подбор предложений.",
        "Данные сохранены, резюме добавлено, предпочтения настроены. Можно переходить к поиску работы.",
      ];
  const base = employer ? "/employer/" : "/candidate/";
  const next = () => navigate(base + routes[step + 1]);
  const rightTitles = employer
    ? [
        "Не просто вакансия. Ваша будущая команда.",
        "Познакомьте с вашей командой",
        "Точнее роль — точнее подбор",
        "Понятные задачи — точные ожидания",
        "Прозрачность с первого шага",
        "Осталось ваше решение",
      ]
    : [
        "Не просто резюме. Ваш следующий шаг.",
        "Профиль начинается с вас",
        "Что включить в резюме",
        "Настроим подбор под вас",
        "Оценка, а не аттестация",
        "Профиль заполнен",
      ];
  const rightBodies = employer
    ? [
        "Обозначьте задачи, стек и условия. Поможем соискателям понять, подходит ли им ваша роль.",
        "Расскажите о продукте и людях, с которыми предстоит работать.",
        "Выбирайте грейд по самостоятельности и сложности задач. Опыт в годах — ориентир, а не единственный критерий.",
        "Отделяйте обязательные навыки от желательных. Это поможет сильным кандидатам оценить свою готовность.",
        "Укажите зарплатную вилку и этапы отбора. Соискатели смогут принять осознанное решение.",
        "Сейчас это черновик — соискатели его не видят. Нажмите «Опубликовать вакансию», когда убедитесь, что всё верно.",
      ]
    : [
        "Покажите свой опыт, обозначьте интересы и получите предварительную оценку навыков.",
        "Используйте настоящее имя и актуальные контакты. Так работодателю будет проще познакомиться с вами.",
        "Лучше всего подойдёт документ с актуальной информацией о вашем опыте.",
        "Выбирайте технологии, с которыми действительно работали. Предпочтения можно будет обновить в профиле.",
        "Результат — предварительная оценка по ответам на тест. Он не подтверждает квалификацию и не заменяет техническое собеседование.",
        "Все данные можно изменить в профиле. Предварительный грейд сохранён отдельно от сведений об опыте.",
      ];
  let content;
  if (step === 0) {
    const stageTitles = employer
      ? [
          "Представьте компанию",
          "Определите роль",
          "Опишите задачи",
          "Добавьте условия",
        ]
      : [
          "Расскажите о себе",
          "Добавьте резюме",
          "Выберите свою роль",
          "Узнайте свой грейд",
        ];
    const stageBodies = employer
      ? [
          "Сфера, продукт и контакт представителя.",
          "Направление, грейд, стек и число позиций.",
          "Зона ответственности и навыки будущего коллеги.",
          "Зарплата, формат работы и этапы отбора.",
        ]
      : [
          "Имя, контакты и опыт — основа вашего профиля.",
          "Загрузите документ с опытом и образованием.",
          "Стек, формат работы и ваши ожидания.",
          "Короткий тест по выбранному направлению.",
        ];
    content = (
      <>
        <h2>
          {employer
            ? "От знакомства до готовой вакансии"
            : "Четыре шага к новым возможностям"}
        </h2>
        <p className="muted introduction">
          {employer
            ? "Заполните четыре раздела и проверьте результат. Вакансия появится на платформе только после вашего решения о публикации."
            : "Заполните профиль один раз. EndPoint будет использовать его, чтобы подбирать релевантные предложения от ИТ-команд."}
        </p>
        <div className="stage-grid">
          {stageTitles.map((title, i) => (
            <button
              className="stage"
              key={title}
              onClick={() => navigate(base + routes[i + 1])}
            >
              <div className="stage-top">
                <Icon name={["user", "file", "sliders", "code"][i]} />
                <span className="mono muted">
                  {(employer ? [3, 2, 5, 3] : [2, 1, 2, 20])[i]}{" "}
                  {
                    (employer
                      ? ["минуты", "минуты", "минут", "минуты"]
                      : ["минуты", "минута", "минуты", "минут"])[i]
                  }
                </span>
              </div>
              <h3>{title}</h3>
              <p>{stageBodies[i]}</p>
            </button>
          ))}
        </div>
        <div className="actions">
          <span className="mono muted">Можно продолжить позже</span>
          <Button onClick={next}>
            {employer ? "Создать вакансию" : "Создать профиль"}
            <Icon name="arrow" />
          </Button>
        </div>
      </>
    );
  } else if (!employer && step === 1)
    content = (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        <div className="photo-row">
          <PrivateImage
            src={profile.photo || asset + "b08f2.png"}
            alt="Фото профиля"
          />
          <div>
            <h3>Фото профиля</h3>
            <p className="muted">JPG или PNG, до 5 МБ</p>
            <label className="upload-button">
              Заменить фото
              <input
                type="file"
                accept="image/png,image/jpeg"
                onChange={(e) => {
                  const file = e.target.files[0];
                  if (!file) return;
                  if (file.size > 5 * 1024 * 1024) {
                    notify("Фото должно быть меньше 5 МБ");
                    return;
                  }
                  uploadProfile("avatar", file);
                }}
              />
            </label>
          </div>
        </div>
        <div className="form-grid">
          {[
            ["Фамилия", "surname"],
            ["Имя", "name"],
            ["Отчество", "patronymic"],
            ["Электронная почта", "email"],
            ["Телефон", "phone"],
            ["Город", "city"],
          ].map(([label, k]) => (
            <Field
              key={k}
              label={label}
              value={profile[k]}
              onChange={(val) => p(k, val)}
              required={k !== "patronymic"}
              type={k === "email" ? "email" : k === "phone" ? "tel" : "text"}
            />
          ))}
          <Field
            label="Опыт в ИТ"
            value={profile.experience}
            onChange={(val) => p("experience", val)}
            options={[
              "Без опыта",
              "Менее года",
              "1 год",
              "2 года",
              "3 года",
              "4 года",
              "5+ лет",
            ]}
          />
          <Field
            label="Коротко о себе"
            area
            value={profile.about}
            onChange={(val) => p("about", val)}
          />
        </div>
        <Consent
          checked={profile.consent}
          onChange={(val) => p("consent", val)}
        />
        <StepActions
          back={() => navigate(base + "start")}
          nextLabel="К загрузке резюме"
          disabled={!profile.consent}
        />
      </form>
    );
  else if (!employer && step === 2) content = <Resume {...c} next={next} />;
  else if (!employer && step === 3)
    content = (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        <div className="field">
          <span>Желаемая роль *</span>
          <Choices
            items={[
              "Backend-разработчик",
              "Frontend-разработчик",
              "Fullstack-разработчик",
            ]}
            value={profile.role}
            onChange={(val) => p("role", val)}
          />
        </div>
        <div className="form-grid">
          <Field
            label="Основные языки"
            value={profile.languages}
            onChange={(val) => p("languages", val)}
            options={[
              "Python / Golang",
              "JavaScript / TypeScript",
              "Java",
              "C++",
            ]}
          />
          <Field
            label="Что хотите делать"
            value={profile.focus || "Разрабатывать сервисы и API"}
            onChange={(val) => p("focus", val)}
            options={[
              "Разрабатывать сервисы и API",
              "Создавать интерфейсы",
              "Работать с данными",
              "Развивать инфраструктуру",
            ]}
          />
        </div>
        <TechPicker
          value={profile.tech}
          onChange={(val) => p("tech", val)}
          {...c}
        />
        <div className="field">
          <span>Предпочтительный формат *</span>
          <Choices
            items={["Удалённо", "Гибрид", "В офисе"]}
            value={profile.format}
            onChange={(val) => p("format", val)}
          />
        </div>
        <div className="form-grid">
          <Field
            label="Город для гибрида"
            value={profile.city}
            onChange={(val) => p("city", val)}
          />
          <Field
            label="Занятость"
            value={profile.employment}
            onChange={(val) => p("employment", val)}
            options={[
              "Полная занятость",
              "Частичная занятость",
              "Проектная работа",
            ]}
          />
          <Field
            label="Доход на руки, ₽ / месяц"
            value={profile.salary}
            onChange={(val) => p("salary", val)}
            required
          />
        </div>
        <StepActions
          back={() => navigate(base + "resume")}
          nextLabel="К тесту на грейд"
        />
      </form>
    );
  else if (!employer && step === 4)
    content = (
      <>
        <div className="test-heading">
          <div className="icon-tile">
            <Icon name="code" />
          </div>
          <div>
            <h2>
              {profile.role.replace("-разработчик", "")} · {profile.languages}
            </h2>
            <p className="muted">Подобран по вашей роли и основным языкам</p>
          </div>
        </div>
        <div className="stats test-stats">
          <div>
            <b>20</b>
            <span>ЗАДАНИЙ</span>
          </div>
          <div>
            <b>20 минут</b>
            <span>НА ПРОХОЖДЕНИЕ</span>
          </div>
          <div>
            <b>Свой ответ</b>
            <span>НА КАЖДЫЙ ВОПРОС</span>
          </div>
        </div>
        <h3>Перед началом</h3>
        <div className="check-row">
          <Icon name="check" />
          <div>
            <b>Проходите самостоятельно</b>
            <p className="muted">
              Не используйте поиск и подсказки. Так оценка будет полезнее для
              подбора работы.
            </p>
          </div>
        </div>
        <div className="check-row">
          <Icon name="check" />
          <div>
            <b>Ответы сохраняются</b>
            <p className="muted">
              Можно вернуться к предыдущему вопросу до завершения теста. Таймер
              не останавливается.
            </p>
          </div>
        </div>
        <p className="notice-box">
          Код запускается в изолированной среде. Решения сохраняются на сервере и
          ожидают проверки.
        </p>
        <StepActions
          back={() => navigate("/candidate/preferences")}
          nextLabel={
            assessment && !assessment.done ? "Продолжить тест" : "Начать тест"
          }
          onNext={async () => {
            try {
              if (!assessment || assessment.done) {
                await api('/api/me/assessments/grade/start', { method: 'POST' });
                await c.reloadWorkspace();
              }
              navigate('/candidate/assessment');
            } catch (e) { c.notify(e.message); }
          }}
        />
      </>
    );
  else if (!employer && step === 5)
    content = (
      <>
        <span className="mono accent-text">РЕЗУЛЬТАТЫ ТЕСТА</span>
        <div className="grade">
          <h2>{assessment?.result?.grade || "Ожидает проверки"}</h2>
          <b>
            {assessment?.result?.score != null
              ? assessment.result.score + "%"
              : "—"}
          </b>
        </div>
        <p className="muted">
          {profile.role} · {profile.languages} / результаты теста
        </p>
        <div className="notice-box">
          Оценка основана только на ответах в этом тесте. Квалификация не
          подтверждена. Используем результат как ориентир для подбора.
        </div>
        <p className="notice-box">
          Ответы сохранены на сервере. Итоговая оценка появится после проверки
          решений.
        </p>
        <div className="actions">
          <Button
            secondary
            onClick={() =>
              setModal({
                title: "Ответы на тест",
                body: (
                  <>
                    <p>
                      {assessment?.result?.status === "reviewed"
                        ? "Результат проверен"
                        : "Ответы ожидают проверки"}
                    </p>
                    <p className="muted">Ваши сохранённые решения:</p>
                    {Object.entries(assessment?.answers || {}).map(([i, a]) => (
                      <div key={i}>
                        <b>
                          {Number(i) + 1}. {taskNames[i]}
                        </b>
                        <pre>{a || "Ответ пропущен"}</pre>
                      </div>
                    ))}
                  </>
                ),
              })
            }
          >
            Посмотреть ответы
          </Button>
          <Button
            onClick={async () => {
              try { await c.completeRegistration(); navigate("/candidate/profile"); }
              catch(e) { c.notify(e.message); navigate("/candidate/profile"); }
            }}
          >
            Перейти в профиль
            <Icon name="arrow" />
          </Button>
        </div>
      </>
    );
  else if (employer && step === 1)
    content = (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        <h2>Компания и представитель</h2>
        <div className="company-logo-upload photo-row">{vacancy.logo?<PrivateImage src={vacancy.logo} alt="Логотип компании"/>:<div className="initials"><UserRound size={24}/></div>}<label className="pill secondary">Загрузить логотип<input type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={e=>{const file=e.target.files?.[0];if(file)uploadProfile('logo',file);}}/></label><span className="muted">PNG, JPG или WebP · до 10 МБ</span></div>
        <div className="form-grid">
          {[
            ["Название компании", "company"],
            ["Сфера деятельности", "sector"],
            ["Сайт компании", "website"],
            ["Имя представителя", "representative"],
            ["Должность", "position"],
            ["Электронная почта", "email"],
          ].map(([label, k]) => (
            <Field
              key={k}
              label={label}
              value={vacancy[k]}
              onChange={(val) => v(k, val)}
              required
              type={k === "email" ? "email" : "text"}
            />
          ))}
          <Field
            label="Размер команды"
            value={vacancy.size}
            onChange={(val) => v("size", val)}
            options={[
              "1–10 сотрудников",
              "11–50 сотрудников",
              "51–200 сотрудников",
              "200+ сотрудников",
            ]}
          />
          <Field
            label="О компании"
            area
            value={vacancy.description}
            onChange={(val) => v("description", val)}
            required
          />
        </div>
        <StepActions
          back={() => navigate(base + "start")}
          nextLabel="К роли и найму"
        />
      </form>
    );
  else if (employer && step === 2)
    content = (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        <Field
          label="Название вакансии"
          value={vacancy.title}
          onChange={(val) => v("title", val)}
          required
        />
        <div className="field">
          <span>Направление *</span>
          <Choices
            items={["Backend", "Frontend", "Fullstack"]}
            value={vacancy.direction}
            onChange={(val) => v("direction", val)}
          />
        </div>
        <div className="field">
          <span>Грейд *</span>
          <Choices
            items={["Junior", "Middle", "Senior", "Lead"]}
            value={vacancy.grade}
            onChange={(val) => v("grade", val)}
          />
        </div>
        <div className="form-grid">
          <Field
            label="Число открытых позиций"
            type="number"
            min="1"
            value={vacancy.count}
            onChange={(val) => v("count", val)}
            required
          />
          <Field
            label="Коммерческий опыт"
            value={vacancy.experience}
            onChange={(val) => v("experience", val)}
            options={["Без опыта", "От 1 года", "От 3 лет", "От 5 лет"]}
          />
        </div>
        <TechPicker
          value={vacancy.tech}
          onChange={(val) => v("tech", val)}
          {...c}
        />
        <p className="notice-box">
          Одна вакансия — одна роль. Для другого направления создайте отдельную
          вакансию.
        </p>
        <StepActions
          back={() => navigate(base + "company")}
          nextLabel="К задачам и требованиям"
        />
      </form>
    );
  else if (employer && step === 3)
    content = (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        {[
          ["Задачи будущего коллеги", "tasks"],
          ["Обязательные требования", "requirements"],
          ["Будет плюсом", "bonus"],
          ["Команда и продукт", "team"],
        ].map(([label, k]) => (
          <Field
            key={k}
            area
            label={label}
            value={vacancy[k]}
            onChange={(val) => v(k, val)}
            required={k !== "bonus"}
          />
        ))}
        <StepActions
          back={() => navigate(base + "role")}
          nextLabel="К условиям и отбору"
        />
      </form>
    );
  else if (employer && step === 4)
    content = (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        <div className="form-grid">
          <Field
            label="Зарплата от, ₽ на руки"
            value={vacancy.salaryMin}
            onChange={(val) => v("salaryMin", val)}
            required
          />
          <Field
            label="Зарплата до, ₽ на руки"
            value={vacancy.salaryMax}
            onChange={(val) => v("salaryMax", val)}
            required
          />
          <Field
            label="Формат работы"
            value={vacancy.format}
            onChange={(val) => v("format", val)}
            options={["Удалённо", "Гибрид", "В офисе"]}
          />
          <Field
            label="Местоположение"
            value={vacancy.city}
            onChange={(val) => v("city", val)}
            required
          />
        </div>
        <Field
          area
          label="Условия работы"
          value={vacancy.conditions}
          onChange={(val) => v("conditions", val)}
          required
        />
        <Field
          area
          label="Процесс отбора"
          value={vacancy.selection}
          onChange={(val) => v("selection", val)}
          required
        />
        <Field
          label="Тестовое задание"
          value={vacancy.test}
          onChange={(val) => v("test", val)}
          options={["Без тестового задания", "Тестовое задание на платформе"]}
        />
        <StepActions
          back={() => navigate(base + "requirements")}
          nextLabel="Проверить вакансию"
        />
      </form>
    );
  else
    content = (
      <>
        <VacancyContent vacancy={vacancy} edit />
        <Consent
          checked={vacancy.consent}
          onChange={(val) => v("consent", val)}
          employer
        />
        {publicationError&&<p role="alert" className="auth-error">{publicationError}</p>}
        <StepActions
          back={() => navigate(base + "conditions")}
          nextLabel={
            publishing ? "Сохраняем…" : vacancy.published ? "Сохранить изменения" : "Опубликовать вакансию"
          }
          onNext={async () => {
            if(publishing)return;
            setPublishing(true);setPublicationError('');
            try {
              await c.publishVacancy();
              notify(vacancy.published ? 'Изменения вакансии сохранены' : 'Вакансия сохранена и опубликована');
              navigate('/employer/dashboard');
            } catch(error) {setPublicationError(error.message);}
            finally {setPublishing(false);}
          }}
          disabled={!vacancy.consent || publishing}
        />
      </>
    );
  return (
    <>
      <PageTitle
        title={titles[step]}
        subtitle={descriptions[step]}
        label={`ОНБОРДИНГ / ${String(!employer && step === 5 ? 7 : step + 1).padStart(2, "0")} — ${employer ? "06" : "07"}`}
      />
      <div className="onboarding-layout">
        <aside className="stepper">
          <span className="mono">Ваш путь в EndPoint</span>
          <div className="steps">
            {steps.map((label, i) => (
              <a
                href={"#" + base + routes[i]}
                key={label}
                className={step === i ? "current" : step > i ? "completed" : ""}
              >
                <span className="step-circle">
                  {step > i ? (
                    <Icon name="check" />
                  ) : (
                    String(i + 1).padStart(2, "0")
                  )}
                </span>
                {label}
              </a>
            ))}
          </div>
          <div className="stepper-bottom mono muted">
            {step === 0
              ? `Около ${employer ? "15" : "25"} минут на все этапы`
              : "Черновик сохранён автоматически"}
            <button
              onClick={() =>
                setModal({
                  title: "Помощь с заполнением",
                  body: "Заполните профиль и перейдите к следующему шагу. Черновики сохраняются в вашем аккаунте автоматически.",
                })
              }
            >
              Нужна помощь?
            </button>
          </div>
        </aside>
        <section className="card onboarding-card">{content}</section>
        <aside className={"card guide " + (step === 0 ? "brand-guide" : "")}>
          {step === 0 ? (
            <>
              <div className="glow">
                <img src={asset + "f6665.svg"} alt="" />
                <img src={asset + "c40a7.svg"} alt="" />
              </div>
              <div className="guide-logo">EndPoint.</div>
            </>
          ) : (
            <div className="icon-tile">
              <Icon
                name={
                  ["user", "user", "file", "sliders", "code", "check"][step]
                }
              />
            </div>
          )}
          <h2>{rightTitles[step]}</h2>
          <p>{rightBodies[step]}</p>
          {step === 0 ? (
            <div className="benefits">
              {(employer
                ? [
                    "Подбор по стеку и опыту",
                    "Прозрачные условия найма",
                    "Управление вакансией в профиле",
                  ]
                : [
                    "Предложения под ваш стек",
                    "Работа в удобном формате",
                    "Контроль над своим профилем",
                  ]
              ).map((t) => (
                <div className="check-row" key={t}>
                  <Icon name="check" />
                  {t}
                </div>
              ))}
            </div>
          ) : step === 5 && !employer ? (
            <>
              <div className="photo-row">
                <PrivateImage
                  src={profile.photo || asset + "dab9b.png"}
                  alt="Фото соискателя"
                />
                <div>
                  <h3>
                    {profile.surname} {profile.name}
                  </h3>
                  <p className="muted">{profile.role}</p>
                </div>
              </div>
              <Tags items={profile.tech} />
              <p>
                {profile.format} / {profile.city}
              </p>
              <p>От {profile.salary} ₽ на руки</p>
            </>
          ) : (
            <div className="notice-box">
              <h3>
                {employer
                  ? "Ваша вакансия"
                  : step === 1
                    ? "Кто увидит контакты?"
                    : step === 2
                      ? "В актуальном резюме"
                      : step === 3
                        ? "Ваш тест"
                        : "Темы теста"}
              </h3>
              {employer ? <>
                <StyledSelect
                  className="vacancy-edit-select"
                  aria-label="Ваша вакансия"
                  value={vacancy.id}
                  disabled={switchingVacancy}
                  onChange={async (e) => {
                    setSwitchingVacancy(true);
                    try { await c.selectVacancy(e.target.value); }
                    finally { setSwitchingVacancy(false); }
                  }}
                >
                  {c.vacancies.map(item => (
                    <option key={item.id} value={item.id}>
                      {item.title || 'Новая вакансия'} · {item.grade || 'Грейд не указан'} · {item.published ? 'Опубликована' : 'Черновик'}
                    </option>
                  ))}
                </StyledSelect>
                <p className="muted">При переключении текущие изменения сохраняются.</p>
                {vacancy.id&&<button className="text-button" onClick={async()=>{if(!window.confirm('Удалить вакансию и её отклики? Активные предложения закроются, отправленные решения сохранятся.'))return;try{await flushWrites();await api('/api/me/vacancies/'+vacancy.id,{method:'DELETE'});await c.reloadWorkspace();c.notify('Вакансия удалена');}catch(e){c.notify(e.message)}}}>Удалить вакансию</button>}
              </> : <p>
                {step === 1
                    ? "Контакты будут доступны работодателю после вашего согласия на общение."
                    : step === 2
                      ? "Последние места работы, результаты проектов, технологии, образование и курсы."
                      : `${profile.role} · ${profile.languages}`}
              </p>}
            </div>
          )}
          <p className="mono guide-foot muted">
            {employer
              ? "Демонстрационный пример: компания и вакансия вымышлены. Данные не проверены."
              : "Результат теста — ориентир для подбора, а не подтверждение квалификации."}
          </p>
        </aside>
      </div>
    </>
  );
}
function StepActions({ back, nextLabel, onNext, disabled }) {
  return (
    <div className="actions">
      <Button secondary onClick={back}>
        <ArrowLeft size={16} />
        Назад
      </Button>
      <Button
        type={onNext ? "button" : "submit"}
        onClick={onNext}
        disabled={disabled}
      >
        {nextLabel}
        <Icon name="arrow" />
      </Button>
    </div>
  );
}
function Consent({ checked, onChange, employer }) {
  return (
    <label className="consent">
      <input
        type="checkbox"
        required
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {employer
        ? "Подтверждаю актуальность условий и право размещать вакансию от имени компании."
        : "Соглашаюсь на обработку персональных данных и принимаю условия использования платформы."}
    </label>
  );
}
function TechPicker({ value, onChange, notify }) {
  const [custom, setCustom] = useState(""),
    [adding, setAdding] = useState(false);
  return (
    <div className="field">
      <span>Ваш стек · можно выбрать несколько</span>
      <Choices
        items={[...new Set([...stack, "FastAPI", ...value])]}
        multiple
        value={value}
        onChange={onChange}
      />
      {adding ? (
        <div className="inline-form">
          <input
            aria-label="Новая технология"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="Название технологии"
          />
          <Button
            secondary
            onClick={() => {
              if (custom.trim()) {
                onChange([...new Set([...value, custom.trim()])]);
                setCustom("");
                setAdding(false);
              }
            }}
          >
            Добавить
          </Button>
        </div>
      ) : (
        <button
          type="button"
          className="text-button"
          onClick={() => setAdding(true)}
        >
          + Добавить технологию
        </button>
      )}
    </div>
  );
}
function Experience({items = [], onChange}) {
  function change(index,key,value) { onChange(items.map((job,i) => i === index ? {...job,[key]:value} : job)); }
  return <section className="vacancy-section">
    <div className="section-heading"><h3>Опыт работы</h3>{onChange && <Button secondary disabled={items.length >= 30} onClick={() => onChange([...items,{company:'',position:'',period:'',description:''}])}>Добавить место работы <Plus size={16}/></Button>}</div>
    {!items.length && <p className="muted">{onChange ? 'Добавьте опыт вручную или загрузите PDF-резюме.' : 'Места работы пока не указаны.'}</p>}
    {items.map((job,index) => <div className="notice-box experience-entry" key={index}>
      {onChange ? <><div className="section-heading"><b>Место работы {index + 1}</b><button className="text-button" aria-label={'Удалить место работы ' + (index + 1)} onClick={() => onChange(items.filter((_,i) => i !== index))}><Trash2 size={16}/></button></div>
        <Field label="Компания" value={job.company || ''} onChange={value => change(index,'company',value)}/>
        <Field label="Должность" value={job.position || ''} onChange={value => change(index,'position',value)}/>
        <Field label="Период работы" value={job.period || ''} placeholder="Январь 2022 — настоящее время" onChange={value => change(index,'period',value)}/>
        <Field area label="Обязанности и достижения" value={job.description || ''} onChange={value => change(index,'description',value)}/>
      </> : <><h4>{job.position || 'Должность не указана'}{job.company && ' · ' + job.company}</h4><p className="mono muted">{job.period}</p><p className="experience-description">{job.description}</p></>}
    </div>)}
  </section>;
}
function InboxButton({role}) {
  const [unread,setUnread]=useState(0);
  useEffect(()=>{
    let active=true;
    async function refresh(){try{const data=await api('/api/messages/unread');if(active)setUnread(data.unread);}catch{}}
    refresh();
    const timer=setInterval(refresh,5000);
    window.addEventListener('focus',refresh);
    window.addEventListener('messages-read',refresh);
    return ()=>{active=false;clearInterval(timer);window.removeEventListener('focus',refresh);window.removeEventListener('messages-read',refresh);};
  },[role]);
  return <a className="profile-button" href={'#/'+role+'/inbox'} title="Входящие" aria-label={'Входящие: '+unread+' непрочитанных сообщений'}><MessageCircle size={21}/>{unread>0 && <span className="notification-count">{unread>99?'99+':unread}</span>}</a>;
}
function NotificationBell({role}) {
  const menuRef=useRef(null);
  const [position,setPosition]=useState({top:118,right:16});
  const [unread,setUnread]=useState(0);
  const [items,setItems]=useState([]);
  const [loading,setLoading]=useState(false);
  function positionPreview() {
    const controls=menuRef.current?.closest('.header-controls');
    if(!controls) return;
    const bounds=controls.getBoundingClientRect();
    setPosition({top:bounds.bottom+10,right:Math.max(16,window.innerWidth-bounds.right)});
  }
  useEffect(()=>{
    function reposition() { if(menuRef.current?.open) positionPreview(); }
    window.addEventListener('resize',reposition);
    window.addEventListener('scroll',reposition,true);
    return ()=>{window.removeEventListener('resize',reposition);window.removeEventListener('scroll',reposition,true);};
  },[]);
  useEffect(() => {
    let active=true;
    async function refresh() { try { const data=await api('/api/v1/notifications?limit=1'); if(active) setUnread(data.unread); } catch {} }
    refresh();const timer=setInterval(refresh,30000);
    window.addEventListener('notifications-changed',refresh);
    window.addEventListener('focus',refresh);
    return () => { active=false;clearInterval(timer);window.removeEventListener('notifications-changed',refresh);window.removeEventListener('focus',refresh); };
  },[role]);
  async function openPreview() {
    positionPreview();
    setLoading(true);
    try {
      const data=await api('/api/v1/notifications?limit=5');
      setItems(data.items || []);
      setUnread(data.unread || 0);
    } catch {} finally { setLoading(false); }
  }
  async function markRead(item) {
    if(item.read) return;
    try {
      await api('/api/v1/notifications/'+item.id+'/read',{method:'POST'});
      setItems(current=>current.map(n=>n.id===item.id?{...n,read:true}:n));
      setUnread(value=>Math.max(0,value-1));
      window.dispatchEvent(new Event('notifications-changed'));
    } catch {}
  }
  return <details ref={menuRef} className="notification-menu" onToggle={e=>{if(e.currentTarget.open) openPreview();}}>
    <summary className="notification-bell" aria-label={'Уведомления: '+unread+' непрочитанных'} title="Уведомления"><Bell size={21}/>{unread>0 && <span className="notification-count">{unread>99?'99+':unread}</span>}</summary>
    <section className="notification-dropdown" style={{position:'fixed',top:position.top,right:position.right}} aria-label="Последние уведомления">
      <h3>Уведомления</h3>
      <div className="notification-list">{loading ? <p className="muted">Загрузка…</p> : items.length ? items.map(item=><button type="button" className={'notification-item'+(item.read?'':' unread')} key={item.id} onClick={async()=>{await markRead(item);if(item.payload?.url){menuRef.current.open=false;navigate(item.payload.url);}}}><span className="notification-item-dot"/><span className="notification-item-content"><b>{item.title}</b><span>{item.body}</span><time>{new Date(item.created_at).toLocaleString('ru',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}</time></span></button>) : <p className="muted">Уведомлений пока нет.</p>}</div>
      <a className="notification-show-all" href={'#/'+role+'/notifications'}>Показать все</a>
    </section>
  </details>;
}
function Resume({
  profile,
  patchProfile: p,
  next,
  notify,
  setModal,
  uploadProfile,
  applyResume,
}) {
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  async function load(file) {
    if (busy) return;
    if (!file) return;
    if (!/\.(pdf|doc|docx)$/i.test(file.name) || file.size > 10 * 1024 * 1024) {
      notify("Выберите PDF, DOC или DOCX размером до 10 МБ");
      return;
    }
    setBusy(true);
    try { await uploadProfile("resume", file); } finally { setBusy(false); }
  }
  return (
    <>
      <div
        className={"upload-zone " + (drag ? "dragging" : "")}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          load(e.dataTransfer.files[0]);
        }}
      >
        <div className="icon-tile">
          <Icon name="file" />
        </div>
        <h3>{busy ? 'Читаем резюме и заполняем профиль…' : profile.resume || "Загрузите резюме"}</h3>
        <p className="muted">
          {profile.resume
            ? "Резюме успешно добавлено"
            : "Перетащите документ сюда"}
        </p>
        <div className="upload-actions">
          <label className="upload-button">
            {profile.resume ? "Заменить резюме" : "Выбрать файл"}
            <input
              type="file"
              accept=".pdf,.doc,.docx"
              disabled={busy}
              onChange={(e) => load(e.target.files[0])}
            />
          </label>
          {profile.resume && (
            <Button
              secondary
              onClick={() =>
                openPrivateFile(profile.resume_url, profile.resume).catch((e) =>
                  notify(e.message),
                )
              }
            >
              Посмотреть файл
            </Button>
          )}
        </div>
        <p className="mono muted">
          PDF, DOC или DOCX · до 10 МБ · один документ
        </p>
      </div>
      <p className="notice-box">
        PDF с текстом автоматически заполнит пустые поля и опыт работы. Уже введённые данные сохраняются. Проверьте результат; email входа и подтверждённый грейд остаются прежними.
      </p>
      {profile.resume_parse && <div className="notice-box"><p>{profile.resume_parse.message}</p>{profile.resume_parse.status === 'parsed' && <>
        <p className="muted">Заполнено полей: {profile.resume_parse.filled_fields?.length || 0}. Найдено мест работы: {profile.resume_parse.fields?.work_experience?.length || 0}. Данные можно отредактировать в профиле.</p>
        {profile.resume_parse.skipped_fields?.length > 0 && <><p>Кнопка ниже заменит заполненные поля данными из PDF. Навыки будут объединены.</p><Button secondary disabled={busy} onClick={async () => { setBusy(true); try { await applyResume(); } catch(error) { notify(error.message); } finally { setBusy(false); } }}>Применить данные PDF к профилю</Button></>}
      </>}</div>}
      <Experience items={profile.work_experience || []} onChange={value => p('work_experience',value)}/>
      <Field label="Email для связи из резюме" value={profile.contact_email || ''} onChange={value => p('contact_email',value)}/>
      <StepActions
        back={() => navigate("/candidate/about")}
        nextLabel="К выбору роли"
        onNext={next}
        disabled={busy || !profile.resume}
      />
    </>
  );
}
function VacancyContent({ vacancy: v, edit = false }) {
  return (
    <>
      <div className="vacancy-title">
        <span className="tag">{v.published ? "Опубликована" : "Черновик"}</span>
        <h2>{v.title}</h2>
        <p className="muted">
          {v.company} · {v.direction} · {v.grade} · {v.experience} опыта
        </p>
        <h3>
          {v.salaryMin}–{v.salaryMax} ₽ на руки / месяц
        </h3>
        <p className="muted">
          {v.format} · {v.city} · {v.count} позиции
        </p>
      </div>
      {[
        ["Компания", v.description, "company"],
        [
          "Роль и стек",
          `${v.grade} разработчик в команде платформы заказов.`,
          "role",
        ],
        [
          "Задачи и требования",
          v.tasks +
            "\n\nОбязательно: " +
            v.requirements +
            "\n\nБудет плюсом: " +
            v.bonus +
            "\n\nКоманда: " +
            v.team,
          "requirements",
        ],
        [
          "Условия и процесс отбора",
          v.conditions + "\n\n" + v.selection + "\n\n" + v.test,
          "conditions",
        ],
      ].map(([title, body, path]) => (
        <section className="vacancy-section" key={title}>
          <div className="section-heading">
            <h3>{title}</h3>
            {edit && (
              <a className="text-button" href={"#/employer/" + path}>
                Изменить
                <Icon name="pencil" />
              </a>
            )}
          </div>
          <p className="preserve">{body}</p>
          {path === "role" && <Tags items={v.tech} />}
        </section>
      ))}
    </>
  );
}
function Profile({ profile: p, ...c }) {
  return (
    <>
      <PageTitle
        title="Ваш профиль"
        subtitle="Опыт, навыки и предпочтения — всё, что поможет найти вашу команду."
        label="ПРОФИЛЬ СОИСКАТЕЛЯ"
      />
      <div className="profile-layout candidate-profile-layout">
        <section className="card">
          <div className="photo-row">
            <PrivateImage
              src={p.photo || asset + "dab9b.png"}
              alt="Фото профиля"
            />
            <div>
              <h2>
                {p.surname} {p.name} {p.patronymic}
              </h2>
              <p className="muted">
                {p.role} · {p.experience} опыта
              </p>
            </div>
            <Button secondary onClick={() => navigate("/candidate/about")}>
              Изменить
            </Button>
          </div>
          <p>{p.about}</p>
          <Tags items={p.tech} />
          <div className="profile-facts">
            <div>
              <span className="muted">Формат работы</span>
              <b>
                {p.format} / {p.city}
              </b>
            </div>
            <div>
              <span className="muted">Занятость</span>
              <b>{p.employment}</b>
            </div>
            <div>
              <span className="muted">Ожидания</span>
              <b>От {p.salary} ₽ на руки</b>
            </div>
          </div>
          <div className="section-heading">
            <h3>Резюме</h3>
            <a className="text-button" href="#/candidate/resume">
              Заменить
            </a>
          </div>
          <p className="resume-filename">{p.resume||"Резюме пока не прикреплено"}</p>
          <Experience items={p.work_experience || []}/>
          {p.resume_url && <Button secondary onClick={()=>previewPrivateFile(p.resume_url).catch(e=>c.notify(e.message))}>Открыть резюме</Button>}
          {p.resume_url && (
            <Button
              secondary
              onClick={() =>
                openPrivateFile(p.resume_url, p.resume).catch((e) =>
                  c.notify(e.message),
                )
              }
            >
              Скачать резюме
            </Button>
          )}
          <div className="actions">
            <Button
              secondary
              onClick={() => navigate("/candidate/preferences")}
            >
              Предпочтения
            </Button>
            <Button onClick={() => navigate("/candidate/inbox")}>
              Входящие предложения
              <Icon name="arrow" />
            </Button>
          </div>
        </section>
        <aside className="card">
          <span className="mono accent-text">ПРЕДВАРИТЕЛЬНАЯ ОЦЕНКА</span>
          <h2 className="grade-label">
            {c.assessment?.result?.grade || "Ожидает проверки"}
          </h2>
          <p className="muted">
            {c.assessment?.result?.score != null
              ? c.assessment.result.score + "%"
              : "Пройдите тест и дождитесь проверки"}
          </p>
          <p>
            Оценка помогает точнее подобрать предложения и не заменяет
            собеседование.
          </p>
          <Button secondary onClick={() => navigate("/candidate/result")}>
            Результаты теста
          </Button>
          <div className="divider" />
          <h3>Пора к новым возможностям</h3>
          <p className="muted">
            В вашем профиле уже есть всё для первого знакомства.
          </p>
          <Button onClick={() => navigate("/candidate/playground")}>
            Открыть редактор
            <Icon name="code" />
          </Button>
        </aside>
      </div>
      <Rewards />
    </>
  );
}
function Dashboard(c) {
  const people = c.people;
  const publishedVacancies = c.vacancies.filter(item => item.published);
  const v = publishedVacancies.find(item => item.id === c.vacancy.id) || publishedVacancies[0];
  const [matches, setMatches] = useState({});
  const [matchError, setMatchError] = useState('');
  const [matching, setMatching] = useState(false);
  useEffect(() => {
    let active = true;
    setMatches({}); setMatchError(''); setMatching(!!v?.id);
    if (v?.id) api('/api/vacancies/' + v.id + '/candidate-matches')
      .then(data => { if (active) setMatches(data); })
      .catch(() => { if (active) setMatchError('Соответствие вакансии временно недоступно'); })
      .finally(() => { if (active) setMatching(false); });
    return () => { active = false; };
  }, [v?.id]);
  const {
    sent,
    setSent,
    favorites,
    setFavorites,
    notify,
    setModal,
  } = c;
  const [query, setQuery] = useState(""),
    [searchQuery, setSearchQuery] = useState(""),
    [tab, setTab] = useState("all"),
    [tech, setTech] = useState("Любая"),
    [city, setCity] = useState("Россия"),
    [experience, setExperience] = useState("Любой опыт"),
    [direction, setDirection] = useState("Backend"),
    [salary, setSalary] = useState("Любой доход"),
    [format, setFormat] = useState("Любой формат"),
    [page, setPage] = useState(1);
  useEffect(() => {
    if (v && c.vacancy.id !== v.id) c.selectVacancy(v.id);
  }, [v?.id, c.vacancy.id]);
  const filtered = [...people].sort((a,b)=>(matches[b.id]?.match_score ?? -1)-(matches[a.id]?.match_score ?? -1)).filter(
    (p) =>
      (!searchQuery ||
        [p.name, p.about, ...p.tech]
          .join(" ")
          .toLowerCase()
          .includes(searchQuery.toLowerCase())) &&
      (tab !== "saved" || favorites.includes(p.id)) &&
      (tech === "Любая" || p.tech.includes(tech)) &&
      (city === "Россия" || p.city === city) &&
      (experience === "Любой опыт" ||
        parseInt(p.experience) >=
          parseInt(experience.match(/\d+/)?.[0] || 0)) &&
      p.role.startsWith(direction) &&
      (salary === "Любой доход" ||
        Number(p.salary.replaceAll(" ", "")) <= Number(salary)) &&
      (format === "Любой формат" || p.format === format),
  );
  if (!v) return <>
    <PageTitle title="Соискатели" subtitle="Соискатели под ваши опубликованные вакансии." />
    <section className="card"><h2>Нет опубликованных вакансий</h2><p>Опубликуйте вакансию, чтобы подобрать соискателей.</p><div className="actions">{c.vacancy.id&&<Button onClick={()=>navigate('/employer/company')}>Редактировать вакансию</Button>}<Button secondary onClick={c.createNewVacancy}>Новая вакансия</Button></div></section>
  </>;
  return (
    <>
      <PageTitle
        title={`${v.representative || c.authUser.name}, найдём вашу команду`}
        subtitle="Соискатели под вашу вакансию — сравнивайте опыт и отправляйте предложения."
        label={`${v.representative} · ${v.position} · ${v.company}`}
      />
      <label className="field">
        <span>Ваша вакансия</span>
        <StyledSelect
          value={v.id}
          onChange={(e) => c.selectVacancy(String(e.target.value))}
        >
          {publishedVacancies.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title || "Вакансия"} · Опубликована
            </option>
          ))}
        </StyledSelect>
      </label>
      <section className="card vacancy-banner">
        <div>
          <span className="mono accent-text">
            {v.published ? "АКТИВНАЯ" : "ЧЕРНОВИК"} ВАКАНСИЯ / {v.count} ПОЗИЦИИ
          </span>
          <h2>{v.title}</h2>
          <p className="muted">
            {v.grade} · {v.experience} · {v.salaryMin}–{v.salaryMax} ₽ на руки /
            месяц · {v.format.toLowerCase()}
          </p>
        </div>
        <div className="stats">
          <div>
            <b>{people.length}</b>
            <span>Профилей в базе</span>
          </div>
          <div>
            <b>{sent.length}</b>
            <span>Предложений отправлено</span>
          </div>
          <div>
            <b>
              {
                c.offers.filter(
                  (o) => o.vacancy_id === v.id && o.status === "accepted",
                ).length
              }
            </b>
            <span>Ответа получено</span>
          </div>
        </div>
        <Button secondary onClick={() => navigate("/employer/review")}>
          К вакансии
          <Icon name="arrow" />
        </Button>
      </section>
      <div className="listing-layout">
        <aside className="filters">
          <div className="section-heading">
            <h3>Фильтры</h3>
            <button
              className="text-button"
              onClick={() => {
                setTech("Любая");
                setCity("Россия");
                setExperience("Любой опыт");
                setDirection("Backend");
                setSalary("Любой доход");
                setFormat("Любой формат");
                setQuery("");
                setSearchQuery("");
                setPage(1);
              }}
            >
              Сбросить
            </button>
          </div>
          <Field
            label="Направление"
            value={direction}
            options={["Backend", "Frontend", "Fullstack"]}
            onChange={setDirection}
          />
          <Field
            label="Опыт работы"
            value={experience}
            options={["Любой опыт", "От 3 лет", "От 4 лет"]}
            onChange={setExperience}
          />
          <Field
            label="Технологии"
            value={tech}
            options={[
              "Любая",
              "Python",
              "Golang",
              "FastAPI",
              "Redis",
              "Docker",
            ]}
            onChange={setTech}
          />
          <Field
            label="Местоположение"
            value={city}
            options={["Россия", "Москва", "Воронеж", "Казань"]}
            onChange={setCity}
          />
          <Field
            label="Доход на руки, до"
            value={salary}
            options={["Любой доход", "150000", "200000", "240000"]}
            onChange={setSalary}
          />
          <Field
            label="Формат работы"
            value={format}
            options={["Любой формат", "Удалённо", "Гибрид"]}
            onChange={setFormat}
          />
          <p className="mono muted">
            Подбор учитывает стек и опыт. Формат работы и итоговый уровень
            уточняйте у соискателя.
          </p>
          <Button secondary onClick={c.createNewVacancy}>
            Новая вакансия
          </Button>
        </aside>
        <div>
          <SearchBox
            value={query}
            onChange={setQuery}
            onSearch={() => { setSearchQuery(query.trim()); setPage(1); }}
            placeholder="Имя, технология или ключевое слово"
          />
          <div className="list-tabs">
            <button
              className={tab === "all" ? "selected" : ""}
              onClick={() => setTab("all")}
            >
              Подобраны для вас / {filtered.length}
            </button>
            <button
              className={tab === "saved" ? "selected" : ""}
              onClick={() => setTab("saved")}
            >
              Избранные / {favorites.length}
            </button>
            <span className="mono muted">ПО СОВПАДЕНИЮ СО СТЕКОМ ↓</span>
          </div>
          <div className="card-list">
            {filtered.length ? (
              filtered
                .slice(
                  (Math.min(page, Math.max(1, Math.ceil(filtered.length / 6))) -
                    1) *
                    6,
                  Math.min(page, Math.max(1, Math.ceil(filtered.length / 6))) *
                    6,
                )
                .map((person) => (
                  <section className="card person-card" key={person.id}>
                    <div className="person-top">
                      <div className="photo-row">
                        {person.photo ? <PrivateImage src={person.photo} alt="Фото соискателя"/> : <div className="initials">{person.initials}</div>}
                        <div>
                          <h3>{person.name}</h3>
                          <p className="muted">
                            {person.role} · {person.experience} опыта
                          </p>
                        </div>
                      </div>
                      <button
                        className={
                          "favorite " +
                          (favorites.includes(person.id) ? "saved" : "")
                        }
                        aria-label={
                          favorites.includes(person.id)
                            ? "Удалить из избранного"
                            : "Добавить в избранное"
                        }
                        onClick={() =>
                          setFavorites(
                            favorites.includes(person.id)
                              ? favorites.filter((i) => i !== person.id)
                              : [...favorites, person.id],
                          )
                        }
                      >
                        <Star
                          size={20}
                          fill={
                            favorites.includes(person.id)
                              ? "currentColor"
                              : "none"
                          }
                        />
                      </button>
                      <span className="mono accent-text">
                        {person.tech.filter((t) => v.tech.includes(t)).length}{" "}
                        ИЗ {v.tech.length} ТЕХНОЛОГИЙ
                      </span>
                    </div>
                    <div className="person-details">
                      <div>
                        <b>от {person.salary} ₽ на руки</b>
                        <p className="muted">
                          {person.format} / {person.city}
                        </p>
                        <span className="mono muted">Полная занятость</span>
                      </div>
                      <Tags items={person.tech} />
                    </div>
                    <p>{person.about}</p>
                    <RatingBadge value={person.profile_strength} level={person.reward_level}/>
                    <div className="candidate-match-info">
                      {matches[person.id] ? <>
                        <b>Соответствие вакансии · {Math.round(matches[person.id].match_score * 100)}%</b>
                        <div className="candidate-match-skills">
                          <p><span className="muted">Совпали навыки: </span>{matches[person.id].explanation.skills_matched.join(', ') || 'Нет'}</p>
                          <p><span className="muted">Не хватает: </span>{matches[person.id].explanation.skills_missing.join(', ') || 'Нет'}</p>
                        </div>
                        <ul>{matches[person.id].explanation.reasons?.map(reason => <li key={reason.code}>{reason.text}</li>)}</ul>
                      </> : <p className="muted">{matching ? 'Рассчитываем соответствие вакансии…' : matchError || 'Для этого профиля нет рекомендации по выбранной вакансии.'}</p>}
                    </div>
                    <div className="person-bottom">
                      <span className="mono muted">{person.grade}</span>
                      <div className="button-row">
                        <Button
                          secondary
                          onClick={() =>
                            navigate("/employer/person/" + person.id)
                          }
                        >
                          Смотреть профиль
                        </Button>
                        <Button
                          disabled={sent.includes(person.id)}
                          onClick={() => {
                            c.sendOffer(person.id)
                              .then(() => notify("Предложение отправлено"))
                              .catch((e) => notify(e.message));
                          }}
                        >
                          {sent.includes(person.id)
                            ? "Предложение отправлено"
                            : "Предложить вакансию"}
                          <Icon name="arrow" />
                        </Button>
                      </div>
                    </div>
                  </section>
                ))
            ) : (
              <Empty
                title="Соискателей пока нет"
                description="Попробуйте изменить фильтры или добавить профили в избранное."
              />
            )}
          </div>
          <div className="pagination">
            <span className="mono muted">
              Всего {filtered.length} соискателей
            </span>
            {Array.from(
              { length: Math.ceil(filtered.length / 6) },
              (_, i) => i + 1,
            ).map((i) => (
              <button
                className={page === i ? "selected" : ""}
                key={i}
                onClick={() => {
                  setPage(i);
                }}
              >
                {i}
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
function SearchBox({ value, onChange, onSearch, placeholder }) {
  return (
    <form className="search-box" onSubmit={(e) => { e.preventDefault(); onSearch(); }}>
      <button type="submit" className="search-icon-button" aria-label="Найти соискателей"><Icon name="search" /></button>
      <input
        aria-label="Поиск"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      <button type="submit" className="search-submit mono accent-text">Найти</button>
    </form>
  );
}
function Empty({ title, description }) {
  return (
    <div className="card empty-state">
      <MessageCircle size={32} />
      <h3>{title}</h3>
      <p className="muted">{description}</p>
    </div>
  );
}
function Inbox({ employer, offerStatuses, setOfferStatuses, sent, ...c }) {
  const [tab, setTab] = useState("all");
  const data = c.offers.map((o) => ({
    ...o,
    company: employer ? o.person.name : o.company,
    status: offerStatuses[o.id] || o.status,
  }));
  const filtered = data.filter((o) => tab === "all" || o.status === tab);
  return (
    <>
      <PageTitle
        title={
          employer
            ? "Входящие и отправленные предложения"
            : `${c.authUser.name}, ваши предложения`
        }
        subtitle="Знакомьтесь с командой, обсуждайте детали и выбирайте следующий шаг."
        label="ВХОДЯЩИЕ"
      />
      <div className="inbox-layout">
        <aside className="card inbox-sidebar">
          <h3>Предложения</h3>
          {[
            ["all", "Все предложения"],
            ["new", "Новые"],
            ["accepted", "В работе"],
            ["declined", "Отклонённые"],
          ].map(([id, label]) => (
            <button
              className={tab === id ? "selected" : ""}
              key={id}
              onClick={() => setTab(id)}
            >
              {label}
              <span>
                {data.filter((o) => id === "all" || o.status === id).length}
              </span>
            </button>
          ))}
          <div className="divider" />
          <p className="muted">
            Контакты будут доступны после согласия на общение.
          </p>
        </aside>
        <div className="card-list">
          {filtered.length ? (
            filtered.map((o) => (
              <article className="card offer-card" key={o.id}>
                <div className="section-heading">
                  <span className="tag">
                    {o.native_status === "withdrawn" ? "Предложение отозвано" : o.native_status === "expired" ? "Срок истёк" : o.status === "new"
                      ? "Новое предложение"
                      : o.status === "accepted"
                        ? "В работе"
                        : "Отклонено"}
                  </span>
                  <span className="mono muted">{o.date}</span>
                </div>
                <div className="company-row">
                  <div className="company-mark">{o.logo?<PrivateImage src={o.logo} alt="Логотип компании"/>:o.company.slice(0,1)}</div>
                  <div>
                    <h2>{o.title}</h2>
                    <p className="muted">{o.company}</p>
                  </div>
                </div>
                <h3>{o.salary} ₽ на руки / месяц</h3>
                <p className="muted">
                  {o.format} · {o.city || "Россия"}
                </p>
                <Tags items={o.tech} />
                <p>{o.about}</p>
                <div className="actions">
                  <Button
                    secondary
                    onClick={() =>
                      navigate(
                        employer
                          ? "/employer/person/" + o.candidate_id
                          : "/candidate/offer/" + o.id,
                      )
                    }
                  >
                    Подробнее
                  </Button>
                  <div className="button-row">
                  {employer && ['sent','viewed','accepted'].includes(o.native_status) && <OfferActions offerId={o.id} status={o.native_status} notify={c.notify} onChanged={c.reloadWorkspace}/>}
                  <Button
                    onClick={() =>
                      navigate(
                        (employer ? "/employer" : "/candidate") +
                          "/chat/" +
                          o.id,
                      )
                    }
                  >
                    Открыть чат
                    <Icon name="arrow" />
                  </Button>
                  </div>
                </div>
              </article>
            ))
          ) : (
            <Empty
              title="Здесь пока пусто"
              description="Предложения с выбранным статусом появятся здесь."
            />
          )}
        </div>
      </div>
    </>
  );
}
function OfferDetail({
  offers,
  route,
  vacancy,
  offerStatuses,
  setOfferStatuses,
  notify,
}) {
  const id = String(route.split("/").pop()),
    o = offers.find((o) => o.id === id);
  if (!o) return <Empty title="Предложение не найдено" />;
  const status = offerStatuses[id] || o.status;
  return (
    <>
      <PageTitle
        title="Предложение от команды"
        subtitle={`${o.company} · познакомьтесь с задачами и условиями`}
      />
      <div className="profile-layout">
        <section className="card">
          <VacancyContent vacancy={o.vacancy} />
          <div className="actions">
            <Button secondary onClick={() => navigate("/candidate/inbox")}>
              К предложениям
            </Button>
            <Button
              onClick={() => {
                setOfferStatuses((s) => ({ ...s, [id]: "accepted" }));
                notify("Вы согласились на общение");
                navigate("/candidate/chat/" + id);
              }}
            >
              {status === "accepted" ? "Продолжить общение" : "Мне интересно"}
              <Icon name="arrow" />
            </Button>
          </div>
        </section>
        <aside className="card">
          <h2>Давайте познакомимся</h2>
          <p className="muted">
            Здравствуйте, Михаил! Ваш опыт подходит нашей команде. Предлагаем
            обсудить вакансию и познакомиться поближе.
          </p>
          <p>
            {o.vacancy.representative} · {o.vacancy.position}
          </p>
          <Button secondary onClick={() => navigate("/candidate/chat/" + id)}>
            Задать вопрос
          </Button>
          <div className="divider" />
          <button
            className="text-button"
            onClick={() => {
              setOfferStatuses((s) => ({ ...s, [id]: "declined" }));
              notify("Предложение отклонено");
              navigate("/candidate/inbox");
            }}
          >
            Отклонить предложение
          </button>
        </aside>
      </div>
    </>
  );
}
function PersonDetail({ route, sent, sendOffer, notify, people }) {
  const id = String(route.split("/").pop()),
    initial = people.find((p) => p.id === id);
  const [detail, setDetail] = useState(null);
  const [loading,setLoading]=useState(true),[error,setError]=useState('');
  useEffect(() => {
    let active=true;
    setDetail(null);setLoading(true);setError('');
    api("/api/candidates/" + id)
      .then(data=>{if(active)setDetail(data)})
      .catch(e=>{if(active)setError(e.status===404?'Профиль не найден или недоступен для просмотра.':e.message)})
      .finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  }, [id]);
  const p = detail || initial;
  if(error)return <Empty title="Профиль недоступен" description={error}/>;
  if(loading&&!p)return <section className="card" role="status">Загрузка профиля соискателя…</section>;
  if (!p) return <Empty title="Профиль не найден" />;
  return (
    <>
      <PageTitle
        title="Профиль соискателя"
        subtitle="Сравните опыт специалиста с задачами вашей команды."
      />
      <section className="card">
        <div className="photo-row">
          {p.photo?<PrivateImage src={p.photo} alt="Фото соискателя"/>:<div className="initials">{p.initials}</div>}
          <div>
            <h2>{p.name}</h2>
            <p className="muted">
              {p.role} · {p.experience} опыта
            </p>
          </div>
        </div>
        <p>{p.about}</p>
        <RatingBadge value={p.profile_strength} level={p.reward_level}/>
        <Tags items={p.tech} />
        <div className="profile-facts">
          <div>
            <span className="muted">Город</span>
            <b>{p.city}</b>
          </div>
          <div>
            <span className="muted">Зарплата</span>
            <b>От {p.salary} ₽</b>
          </div>
          <div>
            <span className="muted">Оценка</span>
            <b>{p.grade}</b>
          </div>
        </div>
        <Experience items={p.work_experience || []}/>
        <h3>Общий стаж</h3>
        <p>
          {p.experience} · {p.role}
        </p>
        {p.email && (
          <p>
            {p.email} · {p.phone}
          </p>
        )}
        {p.resume_url && (
          <Button
            secondary
            onClick={() =>
              openPrivateFile(p.resume_url, p.resume).catch((e) =>
                notify(e.message),
              )
            }
          >
            Скачать резюме
          </Button>
        )}
        <div className="actions">
          <Button secondary onClick={() => navigate("/employer/dashboard")}>
            К соискателям
          </Button>
          <Button
            onClick={() => {
              sendOffer(id)
                .then((o) => navigate("/employer/chat/" + o.id))
                .catch((e) => notify(e.message));
            }}
          >
            Предложить вакансию
            <Icon name="arrow" />
          </Button>
        </div>
      </section>
    </>
  );
}
function Chat({
  offers,
  setModal,
  route,
  messages,
  setMessages,
  sendMessage,
  notify,
  tasks,
  assignment,
  setAssignment,
  hiddenChatIds=[],
}) {
  const employer = route.startsWith("/employer"),
    id = route.split("/").pop(),
    key = (employer ? "employer-" : "candidate-") + id,
    [text, setText] = useState("");
  const offer = offers.find((o) => o.id === String(id)),
    person = offer?.person;
  const newerAttempt = offer && offers.find(o=>o.candidate_id===offer.candidate_id && o.vacancy_id===offer.vacancy_id && o.tasks?.length && !o.assessment_submitted && o.assessment_attempt>offer.assessment_attempt);
  tasks = offer?.tasks || [];
  const title = employer
    ? person?.name || "Соискатель"
    : offer?.company || "КонтурЛаб";
  const thread = messages[key] || [];
  const lastMessageId=thread.reduce((maximum,message)=>Math.max(maximum,Number(message.id)||0),0);
  useEffect(()=>{if(offer?.id)api('/api/offers/'+offer.id+'/chat/restore',{method:'POST'}).catch(()=>{});},[offer?.id]);
  useEffect(()=>{
    if(!offer?.id || !lastMessageId)return;
    let active=true;
    async function markRead(){
      if(document.hidden || !document.hasFocus())return;
      try{await api('/api/offers/'+offer.id+'/messages/read',{method:'POST',body:{last_id:lastMessageId}});if(active)window.dispatchEvent(new Event('messages-read'));}catch{}
    }
    markRead();
    window.addEventListener('focus',markRead);
    document.addEventListener('visibilitychange',markRead);
    return ()=>{active=false;window.removeEventListener('focus',markRead);document.removeEventListener('visibilitychange',markRead);};
  },[offer?.id,lastMessageId]);
  const connection = useOfferChat(offer?.id, Boolean(offer), {
    onMessage: (item) =>
      setMessages((current) => {
        const list = current[key] || [];
        return {
          ...current,
          [key]: (list.some((message) => message.id === item.id)
            ? list.map((message) => (message.id === item.id ? item : message))
            : [...list, item]
          ).sort((a, b) => Number(a.id) - Number(b.id)),
        };
      }),
    onError: notify,
  });
  async function send(e) {
    e.preventDefault();
    if (!text.trim()) return;
    try {
      await sendChatMessage(String(id), text);
      setText("");
    } catch (error) {
      notify(error.message);
    }
  }
  return (
    <>
      <PageTitle
        title="Обсудим ваш следующий шаг"
        subtitle="Задавайте вопросы, знакомьтесь с командой и договаривайтесь о встрече."
      />
      <div className="chat-layout">
        <aside className="card chat-sidebar">
          <h3>Переписка</h3>
          {offers.filter(o=>o.id===id||!hiddenChatIds.includes(o.id)).map((o) => (
            <a
              className={String(o.id) === id ? "selected" : ""}
              key={o.id}
              href={
                "#/" + (employer ? "employer" : "candidate") + "/chat/" + o.id
              }
            >
              <div className="company-mark">
                {(employer?o.person?.photo:o.logo)?<PrivateImage src={employer?o.person.photo:o.logo} alt="Фото собеседника"/>:(employer ? o.person.name : o.company).slice(0, 1)}
              </div>
              <div>
                <b>{employer ? o.person.name : o.company}</b>
                <p className="muted">Обсудим вакансию</p>
              </div>
            </a>
          ))}
          <Button
            secondary
            onClick={() =>
              navigate("/" + (employer ? "employer" : "candidate") + "/inbox")
            }
          >
            К предложениям
          </Button>
        </aside>
        <section className="card chat-card">
          <div className="chat-header">
            <button className="text-button" title="Удалить чат у себя" aria-label="Удалить чат" onClick={async()=>{if(!window.confirm('Удалить чат у себя? У собеседника переписка останется.'))return;try{await api('/api/offers/'+id+'/chat',{method:'DELETE'});window.dispatchEvent(new Event('workspace-refresh'));navigate('/'+(employer?'employer':'candidate')+'/inbox');notify('Чат удалён у вас');}catch(e){notify(e.message)}}}><Trash2 size={18}/></button>
            <div className="company-mark">{(employer?offer?.person?.photo:offer?.logo)?<PrivateImage src={employer?offer.person.photo:offer.logo} alt="Фото собеседника"/>:title.slice(0,1)}</div>
            <div>
              <h3>{title}</h3>
              <p className="muted">{offer?.title} · приглашение к знакомству</p>
            </div>
            <span className="tag">
              {connection === "connected"
                ? "Онлайн · WebSocket"
                : connection === "connecting" || connection === "reconnecting"
                  ? "Подключение…"
                  : "Нет связи"}
            </span>
          </div>
          <div className="chat-messages">
            <div className="date-divider">Сегодня</div>
            {thread.map((m, i) => (
              <div key={i} className={"bubble " + (m.mine ? "mine" : "")}>
                <p>{m.text}</p>
                <span>{m.date} ✓</span>
              </div>
            ))}
            <div
              className="chat-end"
              ref={(node) => {
                if (node)
                  node.parentElement.scrollTop =
                    node.parentElement.scrollHeight;
              }}
            />
          </div>
          <form className="message-form" onSubmit={send}>
            <input
              aria-label="Сообщение"
              placeholder="Напишите сообщение…"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <button
              className="send-button"
              type="submit"
              aria-label="Отправить сообщение"
              disabled={!text.trim() || ["declined", "expired", "withdrawn"].includes(offer?.native_status)}
            >
              <Send size={20} />
            </button>
          </form>
          <span className="mono muted chat-note">
            Сообщения сохраняются в аккаунте.
          </span>
        </section>
        <aside className="card chat-info">
          {employer ? <OfferActions offerId={offer?.id} status={offer?.native_status} stage={offer?.hiring_stage} notify={notify}/> : <>{offer?.hiring_stage?.name&&<p className="notice-box">Следующий этап: <b>{offer.hiring_stage.name}</b></p>}{offer?.native_status==='withdrawn'&&<p className="notice-box">Работодатель отозвал предложение. Отбор завершён.</p>}</>}
          <span className="mono accent-text">СЛЕДУЮЩИЙ ШАГ</span>
          <h3>Тестовое задание</h3>
          {offer?.assessment_attempt>1 && <p className="mono accent-text">Попытка {offer.assessment_attempt}</p>}
          {!employer && newerAttempt && <a className="pill primary" href={'#/candidate/chat/'+newerAttempt.id}>Открыть новую попытку · {newerAttempt.assessment_attempt}</a>}
          <p className="muted">
            {tasks.length} заданий · {tasks.reduce((sum,t)=>sum+Math.max(1,Number(t.time)||20),0)} минут
          </p>
          {employer ? (
            <div className="button-row">
              <Button onClick={() => navigate("/employer/builder")}>
                Настроить задание
              </Button>
              <Button
                secondary
                onClick={() =>
                  navigate("/employer/tasks?offer=" + id)
                }
              >
                Решения
              </Button>
            </div>
          ) : (
            <Button
              disabled={!tasks.length || offer?.assessment_submitted || !['sent','viewed','accepted'].includes(offer?.native_status)}
              onClick={async () => {
                try {
                  if (offer.native_status !== 'accepted') {
                    await api('/api/v1/invitations/'+id+'/accept',{method:'POST'});

                  }
                  await flushWrites();
                  const progress=await api('/api/offers/'+id+'/assignment/start',{method:'POST'});
                  setAssignment(progress,{persist:false});
                  navigate('/candidate/assignment');
                } catch(e) { notify(e.message); }
              }}
            >
              Перейти к заданию
              <Icon name="arrow" />
            </Button>
          )}
          <div className="divider" />
          <h3>Встреча с командой</h3>
          <p className="muted">Выберите удобное время и обсудите его в чате.</p>
          {["Завтра, 11:00", "Завтра, 15:00", "Послезавтра, 12:00"].map(
            (time) => (
              <Button
                secondary
                key={time}
                onClick={() => {
                  sendMessage(String(id), "Предлагаю встретиться: " + time)
                    .then(() => notify("Время отправлено в чат"))
                    .catch((error) => notify(error.message));
                }}
              >
                {time}
              </Button>
            ),
          )}
        </aside>
      </div>
    </>
  );
}
function Builder({
  tasks,
  setTasks,
  vacancy,
  notify,
  setModal,
  gradeTasks,
  people,
  sendOffer,
  sendMessage,
  generateTasks,
  generationFocus,
  reloadWorkspace,
}) {
  const defaultTasks = gradeTasks;
  const [generator, setGenerator] = useState(null);
  const [generationAccess,setGenerationAccess]=useState(null);
  useEffect(()=>{let active=true;api('/api/me/generation-access').then(v=>{if(active)setGenerationAccess(v)}).catch(()=>{});return()=>{active=false}},[]);
  function showPaidAccess(){setModal({title:'Баланс и пакеты генераций',className:'wallet-dialog',body:<GenerationWallet onChange={setGenerationAccess}/>})}
  useEffect(() => { let active = true; api('/api/me/generator').then(value => { if (active) setGenerator(value); }).catch(() => {}); return () => { active = false; }; }, []);
  const [purpose, setPurpose] = useState('hiring'), [generationLanguage, setGenerationLanguage] = useState('python'), [generationGrade, setGenerationGrade] = useState('middle'), [generating, setGenerating] = useState(false);
  const [focus, setFocus] = useRemoteState(
    generationFocus,
    "/api/me/generation-focus",
  );
  const [selected, setSelected] = useState(
      tasks.find((t) => t.id === 15)?.id || tasks[0]?.id,
    ),
    [mode, setMode] = useState("ai");
  const task = tasks.find((t) => t.id === selected);
  const incomplete=tasks.map((t,i)=>({index:i+1,issues:taskIssues(t)})).filter(t=>t.issues.length);
  const ready=tasks.length>0&&!incomplete.length;
  useEffect(() => {
    if (!task) return;
    const format = task.purpose || (task.practice_id ? 'practice' : 'hiring');
    setPurpose(format);
    setGenerationLanguage(task.language || 'python');
    setGenerationGrade(task.grade || (format === 'practice' ? 'junior' : 'middle'));
  }, [selected]);
  function update(k, val) {
    setTasks((all) =>
      all.map((t) => (t.id === selected ? { ...t, [k]: val } : t)),
    );
  }
  async function removeTask(id) {
    if (generating) return;
    const remaining = tasks.filter(t => t.id !== id);
    setTasks(remaining);
    if (selected === id) setSelected(remaining[0]?.id);
    try { await flushWrites(); notify('Задание удалено'); }
    catch (error) { notify('Не удалось сохранить удаление: ' + error.message); }
  }
  async function generate(replace = false) {
    if (generating || (replace && !task)) return;
    if(purpose!=='practice' && (!generationAccess || generationAccess.credits<1)){showPaidAccess();return;}
    setGenerating(true);
    try {
      const data = await generateTasks({purpose,language:generationLanguage,grade:generationGrade,focus:typeof focus==='string'?focus:focus?.value || '',...(replace ? {replace_id:task.id} : task ? {base_id:task.id} : {})});
      if (!replace) setSelected(data.at(-1)?.id);
      notify(replace ? 'Задание дополнено. Проверьте новые требования и критерии.' : 'Создано другое задание по новому шаблону.');
    } catch (error) { notify(error.message); }
    finally { setGenerating(false);api('/api/me/generation-access').then(setGenerationAccess).catch(()=>{}); }
  }
  function add() {
    const id = Date.now();
    setTasks([
      ...tasks,
      {
        ...defaultTasks[0],
        id,
        title: "Новое задание",
        condition: "Опишите задачу и требования к решению.",
        kind:'Практический кейс', time:'45', points:'100', sample:'', criteria:'', purpose:'hiring',
      },
    ]);
    setSelected(id);
    setMode("manual");
  }
  return (
    <>
      <PageTitle
        title="Создание тестового задания"
        subtitle="Соберите задания вручную или сгенерируйте набор под вашу вакансию."
        label={`${vacancy.representative} · ${vacancy.company}`}
      />
      <div className="builder-modes">
        <section className={"card builder-ai-mode " + (mode === "ai" ? "outlined" : "")}>
        <button
          className="builder-mode-choice"
          onClick={() => {
            setMode("ai");
            notify("Выберите назначение и навыки для генерации");
          }}
        >
          <Icon name="sparkles" />
          <div>
            <h3>Создать из базы знаний</h3>
            {generator && <p className="muted">{generator.configured ? 'Черновики создаёт модель по материалам базы знаний.' : 'Сейчас работает подбор заданий по базе знаний. Генерация моделью ещё не настроена.'}</p>}
            <p className="muted">
              Укажите роль, стек и фокус. Проверьте и отредактируйте каждое
              задание перед отправкой.
            </p>
          </div>
          <span className="tag">{mode === "ai" ? "Выбрано" : "Выбрать"}</span>
        </button>
        <div className="builder-wallet-summary"><div><span className="mono accent-text">БАЛАНС ГЕНЕРАЦИЙ</span><strong>{generationAccess?.balance_units??'…'} <small>ед.</small></strong><span className="muted">{generationAccess?.credits??0} генераций · 10 ед. / 25 ₽ за задание</span></div><Button secondary onClick={showPaidAccess}>Пополнить баланс</Button></div>
        </section>
        <button
          className={"card " + (mode === "manual" ? "outlined" : "")}
          onClick={()=>setMode('manual')}
        >
          <Icon name="pencil" />
          <div>
            <h3>Создать вручную</h3>
            <p className="muted">
              Добавьте свои задания с условиями, кодом и критериями — или
              используйте задания из библиотеки.
            </p>
            <div className="manual-mode-formats"><span><b>Алгоритм</b>Редактор кода и тесты на платформе</span><span><b>Отбор кандидатов</b>GitHub-проект для оценки навыков</span><span><b>Квалификация</b>GitHub-проект для подтверждения уровня</span></div>
          </div>
          <span className="tag">{mode==='manual'?'Выбрано':'Выбрать'}</span>
        </button>
      </div>
      <div className="card builder-banner">
        <div>
          <h2>{vacancy.title} / {vacancy.company}</h2>
          <span className="mono muted">
            {vacancy.title} · {vacancy.grade} · версия 1 · изменения сохранены
          </span>
        </div>
        <div className="button-row">
          <Button
            disabled={!ready}
            onClick={async () => {
              try {
              await flushWrites();
              const recipients = await api('/api/vacancies/' + vacancy.id + '/assessment-recipients');
              setModal({
                title: "Отправить тестовое задание",
                body: (
                  <>
                    <p>
                      Набор: {tasks.length} заданий. Выберите соискателя для
                      приглашения.
                    </p>
                    {!recipients.length && <p>Пока нет получателей: соискатель должен откликнуться на эту вакансию или получить ваше предложение.</p>}
                    {recipients.map((p) => (
                      <div className="section-heading" key={p.id}>
                        <span>{p.name}</span>
                        <Button
                          onClick={() => {
                            api('/api/vacancies/' + vacancy.id + '/assessment-invitations', {method:'POST',body:{candidate_id:p.id}})
                              .then(async (o) => {
                                await reloadWorkspace();
                                if(o.assessment_created === false) notify('У соискателя уже есть активное тестовое. Новый шанс можно отправить после завершения этой попытки.');
                                else await sendMessage(
                                  o.id,
                                  "Приглашаем выполнить тестовое задание: " +
                                    tasks.length +
                                    " заданий.",
                                );
                                navigate("/employer/chat/" + o.id);
                                setModal(null);
                              })
                              .catch((e) => notify(e.message));
                          }}
                        >
                          Отправить
                        </Button>
                      </div>
                    ))}
                  </>
                ),
              });
              } catch(e) { notify(e.message); }
            }}
          >
            Отправить соискателю
            <Icon name="arrow" />
          </Button>
        </div>
      </div>
      <div className="builder-layout">
        <aside className="filters">
          <h3>{mode==='manual'?'Для вакансии':'Роль и параметры'}</h3>
          <Field
            label="Вакансия"
            value={vacancy.title}
            options={[vacancy.title]}
            onChange={() => {}}
          />
          {mode==='ai'&&<><Field
            label="Уровень"
            value={vacancy.grade + " · " + vacancy.experience}
            options={[vacancy.grade + " · " + vacancy.experience]}
            onChange={() => {}}
          />
          <span className="mono muted">ТЕХНОЛОГИИ</span>
          <Tags items={vacancy.tech} />
          <div className="divider" />
          <Field
            label="Состав тестового"
            value={`${tasks.length} заданий`}
            options={[`${tasks.length} заданий`]}
            onChange={() => {}}
          />
          <Field
            label="Формат ответа"
            value="Кейс или алгоритм"
            options={["Кейс или алгоритм"]}
            onChange={() => {}}
          />
          <Field
            label="Какие навыки проверить"
            area
            value={typeof focus==='string'?focus:focus?.value || ''}
            onChange={value=>setFocus({value})}
          />
          <Field label="Назначение" value={purpose} options={[{value:'hiring',label:'Отбор кандидатов · Платно'},{value:'qualification',label:'Проверка квалификации · Платно'},{value:'practice',label:'Алгоритм на сайте · Бесплатно'}]} onChange={value=>{setPurpose(value);if(value==='practice'){setGenerationGrade('junior');if(generationLanguage==='sql')setGenerationLanguage('python');}else if(generationGrade==='junior')setGenerationGrade('middle');if(value!=='practice'&&['javascript','cpp'].includes(generationLanguage))setGenerationLanguage('python');}} />
          <div className="notice-box">{purpose==='practice'?'Алгоритм решается на сайте. Проверяются тесты, ошибки, время и память.':purpose==='qualification'?'Кейс для подтверждения профессиональных навыков. Итоговую оценку выставляет работодатель.':'Рабочая ситуация для отбора кандидатов. Решение оценивается по рубрике.'}</div>
          <Field label="Язык" value={generationLanguage} options={purpose==='practice'?['python','java','javascript','cpp']:['python','java','sql']} onChange={setGenerationLanguage} />
          <Field label="Сложность" value={generationGrade} options={purpose==='practice'?['junior','middle']:['middle','senior','lead']} onChange={setGenerationGrade} />
          <div className="button-row">
          <Button disabled={generating || !task} onClick={() => generate(true)}>
            {generating ? 'Генерируем…' : 'Перегенерировать выбранное'}
            <Icon name="sparkles" />
          </Button>
          <Button secondary disabled={generating || tasks.length >= 100} onClick={() => generate(false)}>Создать новое задание</Button>
          </div>
          <p className="muted">Перегенерация сохраняет основу выбранного задания и добавляет требования. Новое задание создаётся по другому шаблону из базы знаний под выбранные критерии.</p>
          <p className="mono muted">Задания из библиотеки. Проверьте условия перед отправкой.</p></>}
        </aside>
        <section className="card task-list">
          <div className="section-heading">
            <h3>Все задания / {tasks.length}</h3>
            <span className="tag">
              {tasks.reduce((sum, t) => sum + Number(t.points || 0), 0)} баллов
            </span>
          </div>
          <p className="mono muted">
            Выберите задание для редактирования. Меняйте порядок стрелками.
          </p>
          <Tags items={[`${tasks.filter(t=>t.practice_id).length} алгоритмов`, `${tasks.filter(t=>!t.practice_id).length} кейсов`]} />
          <div className="task-items">
            {tasks.map((t, i) => (
              <div
                className={"task-item " + (t.id === selected ? "selected" : "")}
                key={t.id}
              >
                <button disabled={generating} onClick={() => setSelected(t.id)}>
                  <span className="mono muted">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <b>{t.title}</b>
                    <span className="mono muted">
                      {t.language || 'python'} · {t.kind || 'Кейс'} · {t.time} мин · {t.points} б.
                    </span>
                  </div>
                </button>
                <button
                  aria-label="Переместить задание выше"
                  disabled={generating || i === 0}
                  onClick={() =>
                    setTasks((all) => {
                      const arr = [...all];
                      [arr[i - 1], arr[i]] = [arr[i], arr[i - 1]];
                      return arr;
                    })
                  }
                >
                  ↑
                </button>
                <button disabled={generating} aria-label={'Удалить задание «' + t.title + '»'} title="Удалить задание" onClick={() => removeTask(t.id)}><Trash2 size={16} /></button>
              </div>
            ))}
          </div>
          <Button secondary disabled={generating} onClick={add}>
            Добавить вручную
            <Plus size={16} />
          </Button>
        </section>
        <div>
          <section className="card task-detail">
            {task ? (
              <>
                <div className="section-heading">
                  <span className="tag">
                    ЗАДАНИЕ {tasks.findIndex((t) => t.id === selected) + 1} /{" "}
                    {tasks.length}
                  </span>
                  <span className="mono success">Изменения сохранены</span>
                </div>
                <Field
                  label="Название задания"
                  value={task.title}
                  onChange={(val) => update("title", val)}
                  required
                />
                <div className="task-parameters">
                  <Field
                    label="Тип"
                    value={task.purpose||(task.practice_id?'practice':'hiring')}
                    options={task.practice_id&&!task.practice_id.startsWith('custom:')?[{value:'practice',label:'Алгоритм'}]:[{value:'practice',label:'Алгоритм'},{value:'qualification',label:'Квалификация'},{value:'hiring',label:'Отбор кандидатов'}]}
                    onChange={val=>setTasks(all=>all.map(t=>t.id===selected?{...t,purpose:val,kind:val==='practice'?'Алгоритм':val==='qualification'?'Проверка квалификации':'Практический кейс',practice_id:val==='practice'?(t.practice_id||'custom:local:'+t.id):undefined}:t))}
                  />
                  <Field
                    label="Время, минут"
                    type="number"
                    min="1"
                    value={task.time}
                    onChange={(val) => update("time", val)}
                  />
                  <Field
                    label="Вес, баллов"
                    type="number"
                    min="0"
                    value={task.points}
                    onChange={(val) => update("points", val)}
                  />
                </div>
                <Field
                  area
                  label="Условие"
                  readOnly={!!task.practice_id&&!task.practice_id.startsWith("custom:")}
                  value={task.condition}
                  onChange={(val) => update("condition", val)}
                />
                {task.practice_id?.startsWith('custom:')&&<AlgorithmTests value={task.tests_json} onChange={val=>update('tests_json',val)}/>}
                <Field
                  area
                  label="Входные данные / пример"
                  readOnly={!!task.practice_id&&!task.practice_id.startsWith("custom:")}
                  value={task.sample}
                  onChange={(val) => update("sample", val)}
                  className="code-input"
                />
                <div className="notice-box">
                  <b>Формат ответа</b>
                  <p>
                    {task.practice_id ? 'Решение во встроенном редакторе. Программа проверяется на скрытых тестах; условие и критерии закреплены за ними.' : 'Соискатель прикрепляет публичный GitHub-репозиторий. Алгоритм проверяет структуру, качество кода и тесты; итоговое решение принимает работодатель.'}
                  </p>
                </div>
                <Field
                  area
                  label="Критерии проверки"
                  readOnly={!!task.practice_id&&!task.practice_id.startsWith("custom:")}
                  value={task.criteria}
                  onChange={(val) => update("criteria", val)}
                />
                {task.sources?.length > 0 && <details className="notice-box"><summary>Основа задания · {task.sources.length} источников</summary><p className="muted">Черновик составлен по найденным материалам базы знаний. Проверьте соответствие вакансии перед отправкой.</p>{task.source_details?.map((source,i)=><p key={i}>{source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.title.replace('full_data: ', '')}</a> : source.title}{source.partial && <small> · использована только сохранённая часть</small>}</p>)}</details>}
                <div className="actions">
                  <button
                    className="text-button"
                    disabled={generating}
                    onClick={() => removeTask(selected)}
                  >
                    <Trash2 size={16} />
                    Удалить задание
                  </button>
                  <Button
                    disabled={generating}
                    onClick={() => flushWrites().then(() => notify('Изменения сохранены')).catch(error => notify(error.message))}
                  >
                    Сохранить
                  </Button>
                </div>
              </>
            ) : (
              <Empty
                title="Добавьте первое задание"
                description="Нажмите «Добавить вручную» или «Создать новое задание»."
              />
            )}
          </section>
          <div className="notice-box">
            <h3>{ready?'Набор готов к отправке':'Набор ещё не готов'}</h3>
            {ready?<p className="muted">Заполнено {tasks.length} заданий. Можно отправить соискателю.</p>:!tasks.length?<p className="muted">Добавьте первое задание.</p>:<div className="muted">{incomplete.map(t=><p key={t.index}>Задание {t.index}: {t.issues.join(' · ')}</p>)}</div>}
          </div>
        </div>
      </div>
    </>
  );
}
function Assessment({
  gradeTasks,
  reloadWorkspace,
  assessment,
  setAssessment,
  completeRegistration,
  theme,
  setModal,
  assigned = false,
  tasks: customTasks,
  setMessages,
  sendMessage,
  notify,
}) {
  const source = assigned ? customTasks : gradeTasks,
    duration = assessment?.duration || (assigned ? source.reduce((sum,t)=>sum+Math.max(1,Number(t.time)||20)*60,0) : 1200);
  const state = assessment || {
    startedAt: Date.now(),
    answers: {},
    index: 0,
    done: false,
  };
  const [seconds, setSeconds] = useState(() =>
    Math.max(0, duration - Math.floor((Date.now() - state.startedAt) / 1000)),
  );
  const index = Math.min(state.index, source.length - 1),
    task = source[index];
  const [checks,setChecks]=useState(state.checks || {});
  const [expired,setExpired]=useState(false);
  const expiryRequested=useRef(false);
  const finishing=useRef(false);
  useEffect(()=>{setChecks(current=>({...current,...(state.checks||{})}))},[state.checks]);
  const unchecked=assigned&&source.some((t,i)=>t.practice_id&&state.answers[i]?.trim()&&(!checks[i]?.solved||checks[i]?.source_code!==state.answers[i]));
  const invalidRepo=assigned&&source.some((t,i)=>!t.practice_id&&state.answers[i]?.trim()&&!validRepository(state.answers[i]));
  async function finish() {
    if(finishing.current || expired || state.done)return;
    finishing.current=true;
    setAssessment({ ...state, done: true });
    try { await flushWrites(); } catch (e) { finishing.current=false;if(assigned){await reloadWorkspace();if(seconds===0){discardWrites('/api/me/assessments/assignment');setExpired(true);return;}}setAssessment({...state,done:false});notify(e.message);return; }
    if (!assigned) {
      try { await completeRegistration(); }
      catch(e) { notify(e.message); }
    }
    if (assigned) {
      try {
        await sendMessage(
          String(state.offerId || ""),
          `Тестовое задание завершено. Сохранено ${Object.values(state.answers).filter(Boolean).length} решений.`,
        );
      } catch (error) {
        notify("Решения сохранены. Сообщение не отправилось: " + error.message);
      }
      notify("Решения сохранены");
    }
    try {
      await flushWrites();
      await reloadWorkspace();
    } catch (e) {
      notify(e.message);
      return;
    }
    navigate(
      assigned
        ? "/candidate/chat/" + (state.offerId || 1)
        : "/candidate/result",
    );
  }
  useEffect(() => {
    if (!assessment && source.length) setAssessment(state);
    const id = setInterval(
      () =>
        setSeconds(
          Math.max(
            0,
            duration - Math.floor((Date.now() - state.startedAt) / 1000),
          ),
        ),
      1000,
    );
    return () => clearInterval(id);
  }, [state.startedAt,duration]);
  useEffect(() => {
    if(assigned && ((!state.done && seconds===0) || state.result?.status==='expired')){
      setExpired(true);
      if(!expiryRequested.current){expiryRequested.current=true;discardWrites('/api/me/assessments/assignment');api('/api/offers/'+state.offerId+'/assignment').then(()=>reloadWorkspace()).catch(()=>{});}
    } else if (!assigned && seconds===0 && !state.done) finish();
  }, [seconds,state.result?.status]);
  if(assigned && (expired || state.result?.status==='expired'))return <section className="card"><h1>Время истекло — тестовое не пройдено</h1><p>Попытка завершена. Отправка решения и изменения больше недоступны.</p><Button onClick={()=>navigate('/candidate/tasks')}>К заданиям компаний</Button></section>;
  if(assigned && state.done)return <section className="card"><h1>Решения отправлены</h1><p>Работодатель получил ваше тестовое. Повторная отправка недоступна.</p><Button onClick={()=>navigate('/candidate/tasks')}>К заданиям компаний</Button></section>;
  if (!task)
    return (
      <Empty
        title="Задание не найдено"
        description="Откройте тестовое задание из переписки."
      />
    );
  return (
    <>
      <PageTitle
        title={
          assigned
            ? "Тестовое задание от работодателя"
            : "Тест на предварительный грейд"
        }
        subtitle="Решайте задачи самостоятельно. Ответы сохраняются в аккаунте."
        label={`${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")} ОСТАЛОСЬ`}
      />
      <div className="assessment-layout">
        <aside className="card">
          <h3>Задания / {source.length}</h3>
          <div className="question-grid">
            {source.map((t, i) => (
              <button
                key={t.id}
                className={
                  (index === i ? "selected " : "") +
                  (state.answers[i] ? "answered" : "")
                }
                onClick={() => setAssessment({ ...state, index: i })}
              >
                {i + 1}
              </button>
            ))}
          </div>
          <p className="mono muted">
            Ответов: {Object.values(state.answers).filter(Boolean).length} /{" "}
            {source.length}
          </p>
          {unchecked&&<p className="muted">Перед отправкой пройдите все тесты каждого алгоритма. После изменения кода запустите проверку снова.</p>}
          <Button
            disabled={unchecked||invalidRepo}
            onClick={() =>
              setModal({
                title: "Завершить тест?",
                body: (
                  <>
                    <p>
                      Сохранено{" "}
                      {Object.values(state.answers).filter(Boolean).length}{" "}
                      ответов.{" "}
                      {assigned
                        ? "Решение будет сохранено в аккаунте."
                        : "Ответы будут отправлены на проверку."}
                    </p>
                    <Button
                      onClick={() => {
                        finish();
                        setModal(null);
                      }}
                    >
                      {assigned
                        ? "Отправить решение"
                        : "Завершить и посмотреть результат"}
                    </Button>
                  </>
                ),
              })
            }
          >
            Завершить тест
          </Button>
        </aside>
        <div>
          <section className="card assessment-question">
            <span className="mono accent-text">
              ЗАДАНИЕ {index + 1} / {source.length}
            </span>
            <h2>{task.title}</h2>
            <p className="preserve">{task.condition}</p>
            {task.public?.code && <pre className="fsp-result">{task.public.code}</pre>}
            {task.public?.schema && <pre className="fsp-result">{JSON.stringify(task.public.schema, null, 2)}</pre>}
            {(task.kind?.startsWith('quiz') || task.kind === 'predict_output') ? <div className="fsp-options">{task.options.map((option, n) => {
              const value = String(typeof option === 'string' ? option : option.id ?? option.value ?? n);
              const label = typeof option === 'string' ? option : option.text ?? option.label ?? value;
              let selected = [];
              try { selected = JSON.parse(state.answers[index] || '[]'); } catch {}
              const multi = task.kind === 'quiz_multi';
              return <label key={value}><input type={multi ? 'checkbox' : 'radio'} name={'question-'+task.id} checked={multi ? selected.includes(value) : state.answers[index] === value} onChange={() => setAssessment({...state, answers: {...state.answers, [index]: multi ? JSON.stringify(selected.includes(value) ? selected.filter(x=>x!==value) : [...selected,value]) : value}})} /> {label}</label>;
            })}</div> : (assigned&&task.practice_id?<p className="muted">Решите алгоритм и запустите проверку во встроенном редакторе.</p>:assigned?<GithubAttachment key={task.id} value={state.answers[index] || ''} onChange={value => setAssessment({...state,answers:{...state.answers,[index]:value}})}/>:<Field label="Ваше решение" area value={state.answers[index] || ''} onChange={value => setAssessment({...state,answers:{...state.answers,[index]:value}})} placeholder="Введите решение"/>)}{assigned&&!task.practice_id&&<p className="muted">Для объёмного проекта отправьте ссылку на публичный репозиторий GitHub вместо текста. Можно прикрепить ссылку на выбранную ветку; итоговую оценку ставит работодатель.</p>}
            <div className="actions">
              <Button
                secondary
                disabled={index === 0}
                onClick={() => setAssessment({ ...state, index: index - 1 })}
              >
                Предыдущее
              </Button>
              <Button
                disabled={index===source.length-1&&(unchecked||invalidRepo)}
                onClick={() => index===source.length-1 ? finish() : setAssessment({ ...state, index: index + 1 })}
              >
                {index===source.length-1 ? 'Завершить тест' : 'Следующее'}
                <Icon name="arrow" />
              </Button>
            </div>
          </section>
          {(task.practice_id || task.kind === "code_function") && (
          <CodeWorkspace
            key={(assigned ? "assignment" : "grade") + index}
            practiceId={task.practice_id}
            checkUrl={assigned&&task.practice_id?'/api/practice/company/'+state.offerId+'/'+task.id+'/check':undefined}
            onResult={result=>setChecks(current=>({...current,[index]:result}))}
            initialCode={state.answers[index]}
            initialLanguage={checks[index]?.language_id}
            theme={theme}
            storageKey={
              (assigned
                ? "endpoint-assignment-code-" + state.offerId + "-"
                : "endpoint-grade-code-") + task.id
            }
            onCodeChange={(code) =>
              setAssessment((current) => ({
                ...current,
                answers: { ...current.answers, [index]: code },
              }))
            }
          />
          )}
        </div>
      </div>
    </>
  );
}
createRoot(document.getElementById("root")).render(
  <AuthRoot>{(props) => <App key={props.authUser.id} {...props} />}</AuthRoot>,
);













