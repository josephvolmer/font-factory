const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron')
const path = require('path')
const { Backend } = require('./backend')

const isDev = !app.isPackaged

let win = null
let backend = null

function createWindow() {
  win = new BrowserWindow({
    width: 1500,
    height: 980,
    minWidth: 1100,
    minHeight: 700,
    center: true,
    show: false, // revealed on ready-to-show, so there is no white flash
    backgroundColor: '#0b0b0e',
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  win.once('ready-to-show', () => {
    win.show()
    win.focus()
    // Terminal-launched Electron does not always get activation, so ask the app
    // itself to come forward rather than relying on the shell that spawned it.
    app.focus({ steal: true })
  })

  if (isDev) {
    win.loadURL('http://localhost:5180')
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  win.on('closed', () => {
    win = null
  })
}

app.whenReady().then(() => {
  backend = new Backend({
    onLog: (line) => win?.webContents.send('backend:log', line),
  })
  backend.start()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  backend?.stop()
})

// Every renderer call funnels through one channel: the backend already speaks a
// method/params protocol, so adding a pipeline method needs no change here.
ipcMain.handle('backend:call', async (_e, method, params) => {
  try {
    const result = await backend.call(method, params)
    return { ok: true, result }
  } catch (err) {
    return { ok: false, error: String(err.message || err) }
  }
})

ipcMain.handle('dialog:openSheet', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog(win, {
    title: 'Choose a glyph sheet',
    properties: ['openFile'],
    filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp', 'tif', 'tiff'] }],
  })
  return canceled ? null : filePaths[0]
})

ipcMain.handle('dialog:saveFile', async (_e, { defaultPath, filters }) => {
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    defaultPath,
    filters,
  })
  return canceled ? null : filePath
})

ipcMain.handle('shell:showItem', async (_e, target) => {
  shell.showItemInFolder(target)
})
