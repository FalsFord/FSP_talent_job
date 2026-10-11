import React, { useState, useEffect } from "react";
import {
  Sun,
  Moon,
  ArrowRight,
  Eye,
  EyeOff,
  ShieldCheck,
  Code2,
  BriefcaseBusiness,
  UserRound,
} from "lucide-react";
import { api, setAuth, getAuthUser, refreshSession, flushWrites } from "./api";
import "./style.css";

export default function AuthRoot({ children }) {
  const [user, setUser] = useState(null),
    [workspace, setWorkspace] = useState(null),
    [loading, setLoading] = useState(true),
    [failure, setFailure] = useState("");
  async function load() {
    const id = getAuthUser()?.id;
    const data = await api("/api/workspace");
    if (getAuthUser()?.id !== id) return data;
    setWorkspace(data);
    setUser(data.user);
    return data;
  }
  async function bootstrap() {
    setLoading(true);
    setFailure("");
    try {
      if (document.cookie.includes("endpoint_csrf=")) {
        await refreshSession();
        await load();
      }
    } catch (e) {
      if (e.status !== 401 && e.status !== 403) setFailure(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    bootstrap();
    const expired = () => {
      setAuth(null);
      setUser(null);
      setWorkspace(null);
    };
    addEventListener("auth-expired", expired);
    return () => removeEventListener("auth-expired", expired);
  }, []);
  useEffect(() => {
    if (!user) return;
    const refresh = () =>
      load().catch((e) => {
        if (e.status !== 401) console.warn(e.message);
      });
    addEventListener("workspace-refresh", refresh);
    addEventListener("focus", refresh);
    addEventListener("notifications-changed", refresh);
    const refreshCandidateTasks = () => {
      if (/^#\/candidate\/(tasks|notifications|inbox)(\/|$)/.test(location.hash)) refresh();
    };
    addEventListener("hashchange", refreshCandidateTasks);
    const timer = setInterval(refresh, 10000);
    return () => {
      removeEventListener("workspace-refresh", refresh);
      removeEventListener("focus", refresh);
      removeEventListener("notifications-changed", refresh);
      removeEventListener("hashchange", refreshCandidateTasks);
      clearInterval(timer);
    };
  }, [user?.id]);
  async function authenticated(result) {
    setAuth(result);
    const data = await load();
    location.hash =
      data.user.role === "admin" ? "/admin/services" : data.user.role === "employer"
        ? "/employer/dashboard"
        : data.profile.complete
          ? "/candidate/inbox"
          : "/candidate/start";
  }
  async function logout() {
    await flushWrites();
    await api("/api/auth/logout", { method: "POST" });
    setAuth(null);
    setUser(null);
    setWorkspace(null);
    location.hash = "/auth/login";
  }
  if (loading)
    return (
      <div className="auth-loading">
        <span className="spinner" />
        <p>Открываем EndPoint…</p>
      </div>
    );
  if (failure)
    return (
      <div className="auth-loading">
        <h2>Сервер недоступен</h2>
        <p>{failure}</p>
        <button className="pill primary" onClick={bootstrap}>
          Повторить
        </button>
      </div>
    );
  return user && workspace ? (
    children({
      authUser: user,
      workspace,
      onLogout: logout,
      reloadWorkspace: load,
    })
  ) : (
    <AuthScreen onAuthenticated={authenticated} />
  );
}
function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState(
      location.hash.includes("register") ? "register" : "login",
    ),
    [role, setRole] = useState("candidate"),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [confirmation, setConfirmation] = useState(""),
    [name, setName] = useState(""),
    [consent, setConsent] = useState(false),
    [visible, setVisible] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [theme, setTheme] = useState(() =>
    localStorage.getItem("endpoint-theme")
      ? JSON.parse(localStorage.getItem("endpoint-theme"))
      : "light",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    localStorage.setItem("endpoint-theme", JSON.stringify(theme));
  }, [theme]);
  function switchMode(next) {
    setMode(next);
    setError("");
    setPassword("");
    setConfirmation("");
    location.hash = "/auth/" + next;
  }
  async function submit(e) {
    e.preventDefault();
    setError("");
    if (mode === "register" && password !== confirmation) {
      setError("Пароли не совпадают.");
      return;
    }
    setBusy(true);
    try {
      const data = await api("/api/auth/" + mode, {
        method: "POST",
        body:
          mode === "register"
            ? { name, email, password, role, consent_personal_data: consent }
            : { email, password },
      });
      if (data.verification_required) { setError("Подтвердите email по ссылке из письма, затем войдите."); return; }
      await onAuthenticated(data);
    } catch (e) {
      setError(
        e.status === 422
          ? "Проверьте email и пароль: пароль должен содержать от 10 до 128 символов."
          : e.message,
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <header className="site-header auth-header">
        <a
          className="logo"
          href="#/auth/login"
          onClick={() => switchMode("login")}
        >
          EndPoint.
        </a>
        <span className="mono muted">ВАША СЛЕДУЮЩАЯ КОМАНДА</span>
        <button
          className="theme-button"
          aria-label={
            theme === "light" ? "Включить тёмную тему" : "Включить светлую тему"
          }
          onClick={() => setTheme(theme === "light" ? "dark" : "light")}
        >
          {theme === "light" ? <Moon size={19} /> : <Sun size={19} />}
        </button>
      </header>
      <main className="auth-page">
        <section className="card auth-story">
          <div className="auth-orb" />
          <span className="mono accent-text">ОПЫТ · ЛЮДИ · ВОЗМОЖНОСТИ</span>
          <h1>
            Следующий шаг
            <br />
            начинается с вас.
          </h1>
          <p>
            Ваша команда или работа, которая подходит вам. Знакомьтесь,
            обсуждайте задачи и создавайте новое вместе.
          </p>
          <div className="auth-benefits">
            <div>
              <UserRound />
              <span>Профиль, который расскажет о вашем опыте</span>
            </div>
            <div>
              <BriefcaseBusiness />
              <span>Вакансии с понятными условиями</span>
            </div>
            <div>
              <Code2 />
              <span>Код, тестовые задания и диалог с командой</span>
            </div>
          </div>
          <div className="auth-security">
            <ShieldCheck size={18} />
            <span>
              Ваши данные хранятся в аккаунте. Контакты и резюме доступны
              работодателю после согласия на общение.
            </span>
          </div>
        </section>
        <section className="card auth-form-card">
          <div className="auth-tabs">
            <button
              className={mode === "login" ? "selected" : ""}
              onClick={() => switchMode("login")}
            >
              Вход
            </button>
            <button
              className={mode === "register" ? "selected" : ""}
              onClick={() => switchMode("register")}
            >
              Регистрация
            </button>
          </div>
          <h2>
            {mode === "login"
              ? "Рады видеть вас снова"
              : "Создайте ваш аккаунт"}
          </h2>
          <p className="muted">
            {mode === "login"
              ? "Войдите, чтобы продолжить свой путь в EndPoint."
              : "Выберите роль и расскажите, как к вам обращаться."}
          </p>
          <form onSubmit={submit}>
            {mode === "register" && (
              <>
                <div className="role-choices">
                  <button
                    type="button"
                    aria-pressed={role === "candidate"}
                    className={role === "candidate" ? "chosen" : ""}
                    onClick={() => setRole("candidate")}
                  >
                    <UserRound size={19} />
                    Соискатель
                  </button>
                  <button
                    type="button"
                    aria-pressed={role === "employer"}
                    className={role === "employer" ? "chosen" : ""}
                    onClick={() => setRole("employer")}
                  >
                    <BriefcaseBusiness size={19} />
                    Работодатель
                  </button>
                </div>
                <label className="field">
                  <span>Как к вам обращаться</span>
                  <input
                    required
                    minLength={1}
                    maxLength={100}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                    placeholder="Ваше имя"
                  />
                </label>
              </>
            )}
            <label className="field">
              <span>Электронная почта</span>
              <input
                required
                type="email"
                maxLength={320}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                placeholder="you@example.com"
              />
            </label>
            <label className="field">
              <span>Пароль</span>
              <div className="password-field">
                <input
                  required
                  type={visible ? "text" : "password"}
                  minLength={mode === "register" ? 10 : 1}
                  maxLength={128}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={
                    mode === "register" ? "new-password" : "current-password"
                  }
                  placeholder={
                    mode === "register"
                      ? "Не менее 10 символов"
                      : "Введите пароль"
                  }
                />
                <button
                  type="button"
                  aria-label={visible ? "Скрыть пароль" : "Показать пароль"}
                  onClick={() => setVisible(!visible)}
                >
                  {visible ? <EyeOff size={19} /> : <Eye size={19} />}
                </button>
              </div>
            </label>
            {mode === "register" && (
              <label className="field">
                <span>Повторите пароль</span>
                <input
                  required
                  type={visible ? "text" : "password"}
                  minLength={10}
                  maxLength={128}
                  value={confirmation}
                  onChange={(e) => setConfirmation(e.target.value)}
                  autoComplete="new-password"
                  placeholder="Ещё раз, для проверки"
                />
              </label>
            )}
            {mode === "register" && <label className="field"><span><input type="checkbox" required checked={consent} onChange={e => setConsent(e.target.checked)} /> Согласен на обработку персональных данных</span></label>}
            {error && (
              <div className="auth-error" role="alert">
                {error}
              </div>
            )}
            <button
              className="pill primary auth-submit"
              type="submit"
              disabled={busy}
            >
              {busy
                ? "Подождите…"
                : mode === "login"
                  ? "Войти в аккаунт"
                  : "Создать аккаунт"}
              <ArrowRight size={18} />
            </button>
          </form>
          <p className="auth-alternate muted">
            {mode === "login" ? "Ещё нет аккаунта?" : "Уже есть аккаунт?"}{" "}
            <button
              className="text-button"
              onClick={() =>
                switchMode(mode === "login" ? "register" : "login")
              }
            >
              {mode === "login" ? "Зарегистрироваться" : "Войти"}
            </button>
          </p>
          <div className="auth-demo">
            <span className="mono muted">ЛОКАЛЬНЫЕ ТЕСТОВЫЕ АККАУНТЫ</span>
            <button
              onClick={() => {
                setEmail("candidate@example.com");
                switchMode("login");
              }}
            >
              Соискатель · candidate@example.com
            </button>
            <button
              onClick={() => {
                setEmail("employer@example.com");
                switchMode("login");
              }}
            >
              Работодатель · employer@example.com
            </button>
            <p className="mono muted">
              Пароли находятся в backend/demo-accounts.md вашего проекта.
            </p>
          </div>
        </section>
      </main>
      <footer className="site-footer">
        <a href="#/auth/login">EndPoint.</a>
        <span>Знакомства, с которых начинается будущее.</span>
      </footer>
    </>
  );
}
export function PasswordDialog({ onChanged }) {
  const [current, setCurrent] = useState(""),
    [next, setNext] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await flushWrites();
      await api("/api/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      setAuth(null);
      onChanged();
      window.dispatchEvent(new Event("auth-expired"));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <p className="muted">
        После смены пароля потребуется войти снова на всех устройствах.
      </p>
      <label className="field">
        <span>Текущий пароль</span>
        <input
          required
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
      </label>
      <label className="field">
        <span>Новый пароль</span>
        <input
          required
          type="password"
          autoComplete="new-password"
          minLength={10}
          maxLength={128}
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
      </label>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      <button className="pill primary" disabled={busy}>
        Сменить пароль
      </button>
    </form>
  );
}
