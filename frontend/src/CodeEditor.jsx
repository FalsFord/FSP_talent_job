import StyledSelect from './StyledSelect';
import { api, queueSave, getAuthUser } from "./api";
import React, { useState, useEffect, useRef } from "react";

import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import TypeScriptWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker";
import {
  Code2,
  Files,
  Search,
  Settings,
  Play,
  ChevronRight,
  ChevronDown,
  Terminal,
  Check,
  Clock,
  MemoryStick,
  RotateCcw,
  Download,
  PanelLeft,
  Square,
  ExternalLink,
  Braces,
  Command,
} from "lucide-react";

self.MonacoEnvironment = {
  getWorker: (_, label) =>
    label === "typescript" || label === "javascript"
      ? new TypeScriptWorker()
      : new EditorWorker(),
};
loader.config({ monaco });
const languages = [
  {
    id: 63,
    name: "JavaScript",
    mode: "javascript",
    file: "main.js",
    tag: "JS",
    code: '// Welcome to your workspace.\n// Write something great.\n\nfunction greet(name) {\n  return `Hello, ${name}!`;\n}\n\nconst message = greet("world");\nconsole.log(message);\n\n// Try running your code with Ctrl + Enter.\n',
  },
  {
    id: 71,
    name: "Python",
    mode: "python",
    file: "main.py",
    tag: "PY",
    code: '# Welcome to your workspace.\n\ndef greet(name):\n    return f"Hello, {name}!"\n\nprint(greet("world"))\n',
  },
  {
    id: 54,
    name: "C++",
    mode: "cpp",
    file: "main.cpp",
    tag: "C++",
    code: '#include <iostream>\n\nint main() {\n    std::cout << "Hello, world!" << std::endl;\n    return 0;\n}\n',
  },
  {
    id: 62,
    name: "Java",
    mode: "java",
    file: "Main.java",
    tag: "JAVA",
    code: 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, world!");\n    }\n}\n',
  },
];
function readSaved(storageKey) {
  try {
    return JSON.parse(localStorage.getItem(storageKey) || "{}");
  } catch {
    return {};
  }
}
export default function CodeEditor({
  theme,
  storageKey = "codespace",
  onCodeChange,
  practiceId,
  checkUrl,
  onResult,
  initialCode,
  initialLanguage,
}) {
  const [saved] = useState({}),
    [language, setLanguage] = useState(
      languages.find((x) => x.id === saved.language) || languages[0],
    );
  const [codes, setCodes] = useState(saved.codes || {}),
    [stdin, setStdin] = useState(saved.stdin || ""),
    [tab, setTab] = useState("output"),
    [result, setResult] = useState(null),
    [error, setError] = useState(""),
    [running, setRunning] = useState(false),
    [configured, setConfigured] = useState(null),
    [sidebar, setSidebar] = useState(true),
    [settings, setSettings] = useState(false),
    [fontSize, setFontSize] = useState(14),
    [position, setPosition] = useState({ lineNumber: 1, column: 1 });
  const editor = useRef(),
    runRef = useRef(),
    controller = useRef();
  const [loaded, setLoaded] = useState(false);
  const code = codes[language.id] ?? language.code;
  useEffect(() => {
    let alive = true;
    setLoaded(false);
    api("/api/me/drafts/" + encodeURIComponent(storageKey))
      .then((data) => {
        if (!alive) return;
        const fallbackLanguage=languages.find(l=>l.id===initialLanguage) || languages[0];
        setCodes(data.codes && Object.keys(data.codes).length ? data.codes : initialCode ? {[fallbackLanguage.id]:initialCode} : {});
        setStdin(data.stdin || "");
        setLanguage(
          languages.find((l) => l.id === data.language) || fallbackLanguage,
        );
        setLoaded(true);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [storageKey]);
  useEffect(() => {
    let alive = true;
    const check = () =>
      api("/api/config")
        .then((d) => {
          if (alive) setConfigured(d.connected === true);
        })
        .catch(() => {
          if (alive) setConfigured(false);
        });
    check();
    const id = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(id);
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (loaded)
      queueSave("/api/me/drafts/" + encodeURIComponent(storageKey), {
        language: language.id,
        codes,
        stdin,
      });
  }, [language, codes, stdin, loaded, storageKey]);
  async function run() {
    if (running) return;
    setError("");
    setResult(null);
    setTab("output");
    if (!configured) {
      setError(
        "Среда выполнения временно недоступна. Повторите попытку позже.",
      );
      return;
    }
    setRunning(true);
    const abort = new AbortController();
    controller.current = abort;
    try {
      async function request(url, options) {
        return api(url, { ...options, signal: abort.signal });
      }
      if (practiceId || checkUrl) {
        const data = await request(checkUrl||'/api/practice/'+practiceId+'/check', {method:'POST', body:{source_code:code, language_id:language.id}});
        setResult(data);
        onCodeChange?.(code);
        onResult?.({...data,source_code:code});
        return;
      }
      const { token } = await request("/api/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: {
          source_code: code,
          language_id: language.id,
          stdin,
        },
      });
      if (!token) throw Error("Не удалось запустить код");
      const deadline = Date.now() + 60000;
      while (Date.now() < deadline) {
        const data = await request("/api/submissions/" + token);
        if (data.status?.id > 2) {
          setResult(data);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 800));
        if (abort.signal.aborted)
          throw new DOMException("Aborted", "AbortError");
      }
      throw Error("Время ожидания результата истекло. Попробуйте ещё раз.");
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      if (controller.current === abort) setRunning(false);
    }
  }
  runRef.current = run;
  function download() {
    const url = URL.createObjectURL(new Blob([code], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = language.file;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="code-workspace">
      <header>
        <a className="brand" href="/">
          <span className="brand-icon">
            <Code2 size={20} />
          </span>
          code<span>space</span>
          <small>WORKSPACE</small>
        </a>
        <div className="header-center">
          <span className="dot" /> Personal workspace <ChevronDown size={13} />
        </div>
        <span className="docs">{practiceId ? 'Проверка решения' : 'Редактор кода'}</span>
        <div className="avatar">A</div>
      </header>
      <div className="shell">
        <nav className="activity">
          <button
            className={sidebar ? "active" : ""}
            title="Проводник"
            onClick={() => setSidebar(!sidebar)}
          >
            <Files />
          </button>
          <button
            title="Поиск в коде"
            onClick={() => {
              editor.current?.focus();
              editor.current?.getAction("actions.find").run();
            }}
          >
            <Search />
          </button>
          <button title="Показать вывод" onClick={() => setTab("output")}>
            <Terminal />
          </button>
          <div className="activity-bottom">
            <button title="Настройки" onClick={() => setSettings(!settings)}>
              <Settings />
            </button>
            <span className="mini-avatar">A</span>
          </div>
        </nav>
        {sidebar && (
          <aside>
            <div className="aside-title">
              EXPLORER <span>···</span>
            </div>
            <div className="folder">
              <ChevronDown size={14} /> MY WORKSPACE{" "}
              <span className="subtle">1</span>
            </div>
            <button
              className="file selected"
              onClick={() => editor.current?.focus()}
            >
              <span className="file-tag">{language.tag}</span>
              {language.file}
              <span className="file-dot" />
            </button>
            <div className="workspace-note">
              <div className="note-icon">
                <Braces size={20} />
              </div>
              <b>Место для ваших идей</b>
              <p>Пишите, запускайте и экспериментируйте с кодом.</p>
              <span>
                POWERED BY JUDGE0 <span className="dot" />
              </span>
            </div>
            <div className="aside-footer">
              <ChevronRight size={14} /> OUTLINE
            </div>
          </aside>
        )}
        <main>
          <div className="workspace-toolbar">
            <div>
              <span className="eyebrow">PLAYGROUND</span>
              <h1>Давайте напишем что-нибудь.</h1>
              <p>Ваш код. Ваши идеи. Один запуск до результата.</p>
            </div>
            <span className="session">
              <span className="dot" /> Автосохранение
            </span>
          </div>
          <section className="editor-panel">
            <div className="editor-toolbar">
              <div className="editor-file">
                <span className="file-tag">{language.tag}</span>
                {language.file}
                <span className="file-dot" />
              </div>
              <div className="editor-actions">
                <StyledSelect
                  aria-label="Язык программирования"
                  value={language.id}
                  onChange={(e) => {
                    setLanguage(
                      languages.find((x) => x.id === Number(e.target.value)),
                    );
                    setResult(null);
                    setError("");
                  }}
                >
                  {languages.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </StyledSelect>
                <button
                  className="icon-button"
                  title="Скачать файл"
                  onClick={download}
                >
                  <Download size={16} />
                </button>
                <button
                  className="icon-button"
                  title="Настройки редактора"
                  onClick={() => setSettings(true)}
                >
                  <Settings size={16} />
                </button>
                <button
                  className="run"
                  disabled={configured === null}
                  onClick={running ? () => controller.current?.abort() : run}
                >
                  {running ? (
                    <Square size={13} />
                  ) : (
                    <Play size={13} fill="currentColor" />
                  )}
                  {running ? "Остановить" : "Запустить"}
                  <kbd>Ctrl ↵</kbd>
                </button>
              </div>
            </div>
            <div className="breadcrumbs">
              workspace <ChevronRight size={12} />
              {language.file} <ChevronRight size={12} />
              <span>{language.name}</span>
            </div>
            <div className="editor">
              <Editor
                path={getAuthUser().id + "/" + storageKey + "/" + language.file}
                language={language.mode}
                value={code}
                theme={theme === "dark" ? "endpoint-dark" : "endpoint-light"}
                onChange={(v) => {
                  setCodes((c) => ({ ...c, [language.id]: v ?? "" }));
                  onCodeChange?.(v ?? "");
                }}
                beforeMount={(m) => {
                  m.editor.defineTheme("endpoint-dark", {
                    base: "vs-dark",
                    inherit: true,
                    rules: [
                      { token: "comment", foreground: "808089" },
                      { token: "keyword", foreground: "DC9BEF" },
                    ],
                    colors: {
                      "editor.background": "#191919",
                      "editor.lineHighlightBackground": "#262626",
                      "editorCursor.foreground": "#DC9BEF",
                    },
                  });
                  m.editor.defineTheme("endpoint-light", {
                    base: "vs",
                    inherit: true,
                    rules: [],
                    colors: {
                      "editor.background": "#FFFFFF",
                      "editor.lineHighlightBackground": "#F3F4F8",
                      "editorCursor.foreground": "#AD5EC2",
                    },
                  });
                }}
                onMount={(ed, m) => {
                  editor.current = ed;
                  m.editor.setTheme(
                    theme === "dark" ? "endpoint-dark" : "endpoint-light",
                  );
                  ed.addCommand(m.KeyMod.CtrlCmd | m.KeyCode.Enter, () =>
                    runRef.current(),
                  );
                  ed.onDidChangeCursorPosition((e) => setPosition(e.position));
                }}
                options={{
                  readOnly: !loaded,
                  fontSize,
                  fontFamily: '"JetBrains Mono", Consolas, monospace',
                  minimap: { enabled: false },
                  padding: { top: 16 },
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  tabSize: 2,
                  renderLineHighlight: "all",
                  smoothScrolling: true,
                  bracketPairColorization: { enabled: true },
                }}
              />
            </div>
          </section>
          <section className="console-panel">
            <div className="console-toolbar">
              <div className="tabs">
                <button
                  className={tab === "output" ? "current" : ""}
                  onClick={() => setTab("output")}
                >
                  <Terminal size={15} /> Вывод{" "}
                  {result && <span className="tab-dot" />}
                </button>
                <button
                  className={tab === "input" ? "current" : ""}
                  onClick={() => setTab("input")}
                >
                  Входные данные <span className="badge">stdin</span>
                </button>
              </div>
              <button
                className="icon-button"
                title="Очистить результат"
                onClick={() => {
                  setResult(null);
                  setError("");
                }}
              >
                <RotateCcw size={14} />
              </button>
            </div>
            {tab === "input" ? (
              <textarea
                aria-label="Входные данные stdin"
                placeholder="Данные, которые программа прочитает из стандартного ввода…"
                value={stdin}
                onChange={(e) => setStdin(e.target.value)}
              />
            ) : (
              <div className="output">
                {running ? (
                  <div className="empty">
                    <span className="spinner" />
                    <b>Код выполняется</b>
                    <p>Проверяем решение…</p>
                  </div>
                ) : error ? (
                  <pre className="error">{error}</pre>
                ) : result ? (
                  <>
                    <div
                      className={
                        "result-status " +
                        (result.status.id === 3 ? "success" : "failure")
                      }
                    >
                      <Check size={14} />
                      {result.status.description}
                      <span>
                        <Clock size={13} />
                        {result.time ?? "—"} s <MemoryStick size={13} />
                        {result.memory == null
                          ? "—"
                          : (result.memory / 1024).toFixed(1)}{" "}
                        MB
                      </span>
                    </div>
                    <pre>
                      {[
                        result.stdout,
                        result.compile_output,
                        result.stderr,
                        result.message,
                      ]
                        .filter(Boolean)
                        .join("\n") || "Программа завершилась без вывода."}
                    </pre>
                  </>
                ) : (
                  <div className="empty">
                    <div className="terminal-icon">
                      <Terminal size={22} />
                    </div>
                    <b>Здесь появится результат</b>
                    <p>Запустите код, чтобы увидеть вывод программы.</p>
                    <span>
                      <kbd>Ctrl</kbd> + <kbd>Enter</kbd> для запуска
                    </span>
                  </div>
                )}
              </div>
            )}
          </section>
          <div className="hint">
            <span>
              <Command size={13} /> Маленькая идея — начало большого проекта.
            </span>
            <span>
              UTF-8 <span>•</span> {language.name}
            </span>
          </div>
        </main>
      </div>
      <footer>
        <span>
          <Code2 size={13} /> main <span className="footer-divider" />{" "}
          <span className={"dot " + (!configured ? "muted" : "")} />
          {configured === null
            ? "Проверяем среду выполнения…"
            : configured
              ? "Среда выполнения готова"
              : "Среда выполнения недоступна"}
        </span>
        <span>
          Ln {position.lineNumber}, Col {position.column}
          <span>Spaces: 2</span>
          <span>UTF-8</span>
          <PanelLeft size={13} />
        </span>
      </footer>
      {settings && (
        <div className="modal-backdrop" onClick={() => setSettings(false)}>
          <section
            className="settings"
            role="dialog"
            aria-modal="true"
            aria-label="Настройки"
            onClick={(e) => e.stopPropagation()}
          >
            <h2>Настройки редактора</h2>
            <label>
              Размер шрифта{" "}
              <input
                type="number"
                min="10"
                max="28"
                value={fontSize}
                onChange={(e) =>
                  setFontSize(
                    Math.min(28, Math.max(10, Number(e.target.value))),
                  )
                }
              />
            </label>
            <p>Выберите комфортный размер шрифта для текущего редактора.</p>
            {storageKey === "codespace" &&
              Object.keys(readSaved("codespace")).length > 0 && (
                <button
                  className="run"
                  onClick={() => {
                    const legacy = readSaved("codespace");
                    setCodes(legacy.codes || {});
                    setStdin(legacy.stdin || "");
                    setLanguage(
                      languages.find((l) => l.id === legacy.language) ||
                        languages[0],
                    );
                    setSettings(false);
                  }}
                >
                  Импортировать старый черновик с этого устройства
                </button>
              )}
            <button className="run" onClick={() => setSettings(false)}>
              Готово
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
