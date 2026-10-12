import express from "express";
import path from "node:path";
import { Readable } from "node:stream";
import { fileURLToPath } from "node:url";
import { createServer } from "node:http";
import httpProxy from "http-proxy";
const app = express();
const apiBase = (process.env.API_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);
const server = createServer(app);
const websocketProxy = httpProxy.createProxyServer({
  target: apiBase.replace(/^http/, "ws"),
  ws: true,
  changeOrigin: true,
});
websocketProxy.on("error", (_error, _request, socket) => {
  if (socket && !socket.destroyed) socket.destroy();
});
app.use("/api", async (req, res) => {
  try {
    const headers = new Headers();
    for (const key of [
      "authorization",
      "cookie",
      "origin",
      "content-type",
      "x-csrf-token",
      "idempotency-key",
      "x-request-id",
    ])
      if (req.headers[key]) headers.set(key, req.headers[key]);
    const response = await fetch(apiBase + req.originalUrl, {
      method: req.method,
      headers,
      ...(!["GET", "HEAD"].includes(req.method)
        ? { body: req, duplex: "half" }
        : {}),
      signal: AbortSignal.timeout(90000),
      redirect: "manual",
    });
    res.status(response.status);
    for (const [key, value] of response.headers)
      if (
        ![
          "set-cookie",
          "content-encoding",
          "content-length",
          "transfer-encoding",
          "connection",
        ].includes(key)
      )
        res.setHeader(key, value);
    const cookies = response.headers.getSetCookie();
    if (cookies.length) res.setHeader("Set-Cookie", cookies);
    if (response.body) Readable.fromWeb(response.body).pipe(res);
    else res.end();
  } catch {
    if (!res.headersSent)
      res.status(503).json({
        detail: "Сервер EndPoint недоступен. Запустите backend/start.ps1.",
      });
    else res.end();
  }
});
const directory = path.dirname(fileURLToPath(import.meta.url));
app.use(express.static(path.join(directory, "dist")));
app.get("/{*path}", (_req, res) =>
  res.sendFile(path.join(directory, "dist/index.html")),
);
server.on("upgrade", (request, socket, head) => {
  if (!request.url?.startsWith("/ws/offers/")) {
    socket.destroy();
    return;
  }
  socket.on("error", () => {});
  websocketProxy.ws(request, socket, head);
});
server.listen(process.env.PORT || 3001, "127.0.0.1", () =>
  console.log("EndPoint: http://127.0.0.1:" + (process.env.PORT || 3001)),
);
