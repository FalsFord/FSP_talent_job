import React, { useEffect, useRef, useState } from "react";
let accessToken = "",
  currentUser = null,
  refreshing = null;
const writes = new Map();
const offerSockets = new Map();
export function getAuthUser() {
  return currentUser;
}
export function setAuth(result) {
  if (!result || (currentUser && currentUser.id !== result.user.id)) {
    for (const entry of writes.values()) clearTimeout(entry.timer);
    writes.clear();
  }
  const tokenChanged = accessToken !== (result?.access_token || "");
  accessToken = result?.access_token || "";
  currentUser = result?.user || null;
  if (tokenChanged)
    for (const entry of offerSockets.values())
      if (entry.socket?.readyState === WebSocket.OPEN)
        entry.socket.close(4001, "Session renewed");
}
function csrf() {
  return decodeURIComponent(
    document.cookie
      .split("; ")
      .find((c) => c.startsWith("endpoint_csrf="))
      ?.split("=")
      .slice(1)
      .join("=") || "",
  );
}
export async function refreshSession() {
  if (!refreshing)
    refreshing = (async () => {
      const r = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrf() },
      });
      if (!r.ok) {
        if (r.status === 401 || r.status === 403) setAuth(null);
        const error = Error(
          r.status === 401 || r.status === 403
            ? "Войдите в аккаунт"
            : "Сервер временно недоступен",
        );
        error.status = r.status;
        throw error;
      }
      const data = await r.json();
      setAuth(data);
      return data;
    })().finally(() => {
      refreshing = null;
    });
  return refreshing;
}
function message(data) {
  if (Array.isArray(data?.detail))
    return data.detail.map((e) => e.msg).join(". ");
  return data?.detail || data?.error || "Не удалось выполнить запрос";
}
export async function api(path, options = {}, retried = false) {
  const headers = new Headers(options.headers || {});
  if (accessToken) headers.set("Authorization", "Bearer " + accessToken);
  let body = options.body;
  if (body !== undefined && !(body instanceof FormData)) {
    body = JSON.stringify(body);
    headers.set("Content-Type", "application/json");
  }
  if (path.startsWith("/api/auth/")) headers.set("X-CSRF-Token", csrf());
  const response = await fetch(path, {
    ...options,
    body,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 401 && !retried && !path.startsWith("/api/auth/")) {
    try {
      await refreshSession();
      return api(path, options, true);
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        window.dispatchEvent(new Event("auth-expired"));
        throw Error("Сессия истекла. Войдите снова.");
      }
      throw error;
    }
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const error = Error(message(data));
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return options.blob ? response.blob() : response.json();
}
export function revalidate() {
  window.dispatchEvent(new Event("workspace-refresh"));
}
export function queueSave(path, value) {
  let entry = writes.get(path);
  if (!entry) {
    entry = { timer: null, pending: null, inflight: null };
    writes.set(path, entry);
  }
  entry.pending = value;
  clearTimeout(entry.timer);
  entry.timer = setTimeout(() => drain(path, entry).catch(() => {}), 600);
}
async function drain(path, entry) {
  clearTimeout(entry.timer);
  if (entry.inflight) {
    await entry.inflight;
    return entry.pending !== null ? drain(path, entry) : undefined;
  }
  if (entry.pending === null) return;
  const body = entry.pending;
  entry.pending = null;
  entry.inflight = api(path, { method: "PUT", body }).catch((error) => {
    if (entry.pending === null) entry.pending = body;
    window.dispatchEvent(
      new CustomEvent("api-save-error", { detail: error.message }),
    );
    throw error;
  });
  try {
    await entry.inflight;
  } finally {
    entry.inflight = null;
  }
  if (entry.pending !== null) return drain(path, entry);
}
export async function flushWrites(paths) {
  const selected=paths ? new Set(Array.isArray(paths)?paths:[paths]) : null;
  await Promise.all([...writes].filter(([path])=>!selected || selected.has(path)).map(([path, entry]) => drain(path, entry)));
}
export function discardWrites(path) {
  const entry=writes.get(path);
  if(entry){clearTimeout(entry.timer);entry.pending=null;writes.delete(path);}
}
export function useRemoteState(initial, path, {preserveEdits=false} = {}) {
  const [state, setState] = useState(initial),
    ref = useRef(initial);
  const edited=useRef(false);
  useEffect(() => {
    const entry = path && writes.get(path);
    if (!entry?.inflight && entry?.pending == null) {
      if(preserveEdits && edited.current && initial?.id===ref.current?.id)return;
      edited.current=false;
      ref.current = initial;
      setState(initial);
    }
  }, [initial, path, preserveEdits]);
  function set(value, options = {}) {
    const next = typeof value === "function" ? value(ref.current) : value;
    ref.current = next;
    edited.current=options.persist!==false;
    setState(next);
    if (path && next !== null && options.persist !== false) queueSave(path, next);
    return next;
  }
  return [state, set];
}
export function useMessages(initial,deletedUntil={}) {
  const [messages, set] = useState(initial),
    ref = useRef(initial),
    pending = useRef(0);
  useEffect(() => {
    const merged = { ...ref.current };
    for (const [key, list] of Object.entries(initial || {})) {
      const byId = new Map(
        (merged[key] || []).map((message) => [message.id, message]),
      );
      for (const message of list)
        byId.set(message.id, { ...byId.get(message.id), ...message });
      merged[key] = [...byId.values()].sort(
        (a, b) => Number(a.id) - Number(b.id),
      );
    }
    for (const key of Object.keys(merged)) {
      const cutoff=deletedUntil[key.slice(key.indexOf('-')+1)] || 0;
      merged[key]=merged[key].filter(message=>Number(message.id)>cutoff);
    }
    ref.current = merged;
    set(merged);
  }, [initial,JSON.stringify(deletedUntil)]);
  function update(value) {
    const prev = ref.current,
      next = typeof value === "function" ? value(prev) : value;
    ref.current = next;
    set(next);
    return next;
  }
  return [messages, update];
}

function notifySocket(entry, status) {
  entry.status = status;
  for (const listener of entry.listeners) listener.onStatus?.(status);
}
function connectOfferSocket(entry) {
  if (
    !accessToken ||
    entry.stopping ||
    entry.socket?.readyState === WebSocket.CONNECTING ||
    entry.socket?.readyState === WebSocket.OPEN
  )
    return;
  clearTimeout(entry.closeTimer);
  entry.socket = null;
  const address = new URL(`/ws/offers/${entry.offerId}`, location.href);
  address.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  let socket;
  try {
    socket = new WebSocket(address, [
      "endpoint.chat.v1",
      "endpoint.bearer." + accessToken,
    ]);
  } catch (error) {
    notifySocket(entry, "disconnected");
    return;
  }
  entry.socket = socket;
  entry.stopping = false;
  notifySocket(entry, "connecting");
  socket.onopen = () => {
    notifySocket(entry, "connected");
    for (const pending of entry.pending.values())
      if (!pending.sent) {
        socket.send(
          JSON.stringify({
            type: "message",
            text: pending.text,
            client_message_id: pending.id,
          }),
        );
        pending.sent = true;
      }
  };
  socket.onmessage = (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }
    if (payload.type === "message" && payload.message) {
      const item = payload.message;
      for (const listener of entry.listeners) listener.onMessage?.(item);
      const pending =
        payload.client_message_id &&
        entry.pending.get(payload.client_message_id);
      if (pending) {
        clearTimeout(pending.timer);
        entry.pending.delete(pending.id);
        pending.resolve(item);
      }
      return;
    }
    if (payload.type === "error") {
      const pending =
        payload.client_message_id &&
        entry.pending.get(payload.client_message_id);
      if (pending) {
        clearTimeout(pending.timer);
        entry.pending.delete(pending.id);
        pending.reject(Error(payload.message));
      } else
        for (const listener of entry.listeners)
          listener.onError?.(payload.message);
    }
  };
  socket.onclose = async (event) => {
    if (entry.socket !== socket) return;
    entry.socket = null;
    for (const pending of entry.pending.values()) pending.sent = false;
    if (entry.stopping || !accessToken) {
      for (const pending of entry.pending.values()) {
        clearTimeout(pending.timer);
        pending.reject(Error("Сессия чата завершена."));
      }
      entry.pending.clear();
      notifySocket(entry, "disconnected");
      return;
    }
    if (event.code === 4403) {
      notifySocket(entry, "disconnected");
      for (const listener of entry.listeners)
        listener.onError?.("Нет доступа к этой переписке.");
      return;
    }
    notifySocket(entry, "reconnecting");
    if (event.code === 4401) {
      try {
        await refreshSession();
      } catch (error) {
        if (error.status === 401 || error.status === 403)
          window.dispatchEvent(new Event("auth-expired"));
      }
    }
    if (entry.listeners.size || entry.pending.size)
      setTimeout(
        () => connectOfferSocket(entry),
        event.code === 4401 ? 100 : 1000,
      );
    else notifySocket(entry, "disconnected");
  };
  socket.onerror = () => {
    for (const listener of entry.listeners)
      listener.onError?.("Соединение с чатом прервано.");
  };
}
function offerSocket(offerId) {
  let entry = offerSockets.get(offerId);
  if (!entry) {
    entry = {
      offerId,
      socket: null,
      listeners: new Set(),
      pending: new Map(),
      status: "disconnected",
      stopping: false,
      closeTimer: null,
    };
    offerSockets.set(offerId, entry);
  }
  connectOfferSocket(entry);
  return entry;
}
export function useOfferChat(offerId, enabled, { onMessage, onError } = {}) {
  const [status, setStatus] = useState("disconnected");
  useEffect(() => {
    if (!enabled || !offerId || !accessToken) {
      setStatus("disconnected");
      return;
    }
    const entry = offerSocket(String(offerId)),
      listener = { onMessage, onError, onStatus: setStatus };
    entry.listeners.add(listener);
    setStatus(entry.status);
    connectOfferSocket(entry);
    return () => {
      entry.listeners.delete(listener);
      if (!entry.listeners.size && !entry.pending.size)
        entry.closeTimer = setTimeout(() => {
          if (!entry.listeners.size && !entry.pending.size) {
            entry.stopping = true;
            entry.socket?.close(1000, "Chat closed");
            offerSockets.delete(entry.offerId);
          }
        }, 10000);
    };
  }, [offerId, enabled]);
  return status;
}
export function sendChatMessage(offerId, text) {
  if (!accessToken) return Promise.reject(Error("Войдите в аккаунт"));
  const entry = offerSocket(String(offerId)),
    id = crypto.randomUUID();
  return new Promise((resolve, reject) => {
    const pending = {
      id,
      text: text.trim(),
      resolve,
      reject,
      sent: false,
      timer: setTimeout(() => {
        entry.pending.delete(id);
        reject(
          Error("Чат не ответил. Проверьте соединение и повторите отправку."),
        );
      }, 30000),
    };
    entry.pending.set(id, pending);
    connectOfferSocket(entry);
    if (entry.socket?.readyState === WebSocket.OPEN) {
      entry.socket.send(
        JSON.stringify({
          type: "message",
          text: pending.text,
          client_message_id: id,
        }),
      );
      pending.sent = true;
    }
  });
}
export async function openPrivateFile(path, filename) {
  const blob = await api(path, { blob: true });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

export async function previewPrivateFile(path) {
  const tab=window.open('about:blank','_blank');
  try { const blob=await api(path,{blob:true});const url=URL.createObjectURL(blob);if(tab){tab.location.href=url;}else{URL.revokeObjectURL(url);throw new Error('Разрешите открытие новой вкладки для просмотра резюме');}setTimeout(()=>URL.revokeObjectURL(url),300000); }
  catch(error){tab?.close();throw error;}
}
export function PrivateImage({ src, alt, ...rest }) {
  const [url, setUrl] = useState(src?.startsWith("/api/") ? "" : src);
  useEffect(() => {
    let alive = true,
      objectUrl;
    setUrl(src?.startsWith("/api/") ? "" : src);
    if (src?.startsWith("/api/"))
      api(src, { blob: true })
        .then((blob) => {
          objectUrl = URL.createObjectURL(blob);
          if (alive) setUrl(objectUrl);
        })
        .catch(() => {});
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);
  return React.createElement("img", {
    src: url || "/assets/figma/b08f2.png",
    alt,
    ...rest,
  });
}
