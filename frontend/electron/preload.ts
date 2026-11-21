import { contextBridge, ipcRenderer } from "electron";
contextBridge.exposeInMainWorld("nodeglass", {
  connection: () => ipcRenderer.invoke("connection"),
  chooseRepository: () => ipcRenderer.invoke("choose-repository"),
});
