import { app, BrowserWindow, dialog, ipcMain, protocol, net } from "electron";
import { spawn, ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { join, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { createInterface } from "node:readline";

protocol.registerSchemesAsPrivileged([
  {
    scheme: "nodeglass",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
    },
  },
]);
let child: ChildProcess | undefined;
let window: BrowserWindow | undefined;
let closing = false;
let connection: { url: string; token: string };
const devOrigin = "http://127.0.0.1:5173";
const origin = app.isPackaged ? "nodeglass://app" : devOrigin;

function trusted(event: Electron.IpcMainInvokeEvent) {
  const url = event.senderFrame?.url;
  if (
    !window ||
    event.sender !== window.webContents ||
    !url ||
    new URL(url).origin !== new URL(origin).origin ||
    !url.startsWith(origin + "/")
  ) {
    throw new Error("Untrusted IPC sender");
  }
}

async function backend() {
  if (!app.isPackaged && process.env.NODEGLASS_BACKEND_URL) {
    const url = new URL(process.env.NODEGLASS_BACKEND_URL);
    if (
      url.hostname !== "127.0.0.1" ||
      url.protocol !== "http:" ||
      !process.env.NODEGLASS_TOKEN
    )
      throw new Error("Invalid development backend configuration");
    return { url: url.origin, token: process.env.NODEGLASS_TOKEN };
  }
  const token = randomBytes(32).toString("hex");
  const root = resolve(__dirname, "../..");
  const executable = app.isPackaged
    ? join(
        process.resourcesPath,
        "backend",
        process.platform === "win32"
          ? "nodeglass-backend.exe"
          : "nodeglass-backend",
      )
    : process.env.NODEGLASS_PYTHON ||
      join(
        root,
        ".venv",
        process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
      );
  child = spawn(executable, app.isPackaged ? [] : ["-m", "backend.entry"], {
    cwd: app.isPackaged ? app.getPath("userData") : root,
    env: {
      ...process.env,
      NODEGLASS_TOKEN: token,
      NODEGLASS_DATA_DIR: app.getPath("userData"),
      NODEGLASS_ORIGIN: origin,
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  // Backend diagnostics never include the launch token.
  child.stderr?.on("data", (data) =>
    console.error(String(data).replaceAll(token, "[redacted]")),
  );
  const port = await new Promise<number>((accept, reject) => {
    const timer = setTimeout(
      () => reject(new Error("Backend startup timed out")),
      20000,
    );
    const lines = createInterface({ input: child!.stdout! });
    lines.once("line", (line) => {
      clearTimeout(timer);
      try {
        const data = JSON.parse(line);
        if (
          data.protocol !== 1 ||
          !Number.isInteger(data.port) ||
          data.port < 1 ||
          data.port > 65535
        )
          throw new Error("Invalid backend handshake");
        accept(data.port);
      } catch (error) {
        reject(error);
      }
    });
    child!.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child!.once("exit", () => {
      clearTimeout(timer);
      reject(new Error("Backend exited during startup"));
    });
  });
  child.once("exit", () => {
    if (!closing)
      dialog.showErrorBox(
        "Backend stopped",
        "The local analysis server stopped. Restart Nodeglass to reconnect.",
      );
  });
  return { url: `http://127.0.0.1:${port}`, token };
}

app.whenReady().then(async () => {
  try {
    if (app.isPackaged) {
      const root = resolve(__dirname, "../dist");
      protocol.handle("nodeglass", (request) => {
        const url = new URL(request.url);
        const path = resolve(
          root,
          "." +
            decodeURIComponent(
              url.pathname === "/" ? "/index.html" : url.pathname,
            ),
        );
        if (url.host !== "app" || !path.startsWith(root + sep))
          return new Response("Forbidden", { status: 403 });
        return net.fetch(pathToFileURL(path).toString());
      });
    }
    connection = await backend();
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try {
        const response = await fetch(connection.url + "/health", {
          headers: { Authorization: `Bearer ${connection.token}` },
        });
        if (response.ok) {
          ready = true;
          break;
        }
      } catch {
        /* wait for uvicorn */
      }
      await new Promise((r) => setTimeout(r, 100));
    }
    if (!ready) throw new Error("Backend health check failed");
    ipcMain.handle("connection", (event) => {
      trusted(event);
      return connection;
    });
    ipcMain.handle("choose-repository", async (event) => {
      trusted(event);
      const selected = await dialog.showOpenDialog(window!, {
        properties: ["openDirectory"],
      });
      if (selected.canceled) return null;
      const response = await fetch(connection.url + "/api/projects/open", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${connection.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ path: selected.filePaths[0] }),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.detail || "Could not open repository");
      return result;
    });
    window = new BrowserWindow({
      width: 1450,
      height: 940,
      minWidth: 1000,
      minHeight: 650,
      backgroundColor: "#101216",
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        preload: join(__dirname, "preload.js"),
      },
    });
    window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    window.webContents.on("will-navigate", (event, url) => {
      if (url !== origin + "/") event.preventDefault();
    });
    window.webContents.on("will-attach-webview", (event) =>
      event.preventDefault(),
    );
    await window.loadURL(origin + "/");
  } catch (error) {
    dialog.showErrorBox("Nodeglass could not start", String(error));
    app.quit();
  }
});
app.on("window-all-closed", () => app.quit());
app.on("before-quit", (event) => {
  if (closing) return;
  closing = true;
  if (child && child.exitCode === null && child.signalCode === null) {
    event.preventDefault();
    const processToStop = child;
    const timer = setTimeout(() => processToStop.kill("SIGKILL"), 3000);
    processToStop.once("exit", () => {
      clearTimeout(timer);
      app.quit();
    });
    processToStop.kill("SIGTERM");
  }
});
