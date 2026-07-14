const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('fontfactory', {
  call: (method, params) => ipcRenderer.invoke('backend:call', method, params),
  openSheet: () => ipcRenderer.invoke('dialog:openSheet'),
  saveFile: (opts) => ipcRenderer.invoke('dialog:saveFile', opts),
  showItem: (p) => ipcRenderer.invoke('shell:showItem', p),
  onLog: (cb) => {
    const handler = (_e, line) => cb(line)
    ipcRenderer.on('backend:log', handler)
    return () => ipcRenderer.removeListener('backend:log', handler)
  },
})
