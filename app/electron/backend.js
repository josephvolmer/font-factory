const { spawn } = require('child_process')
const path = require('path')
const readline = require('readline')
const { app } = require('electron')

const isDev = !app.isPackaged

/**
 * Owns the long-lived Python sidecar.
 *
 * The sidecar is kept alive rather than spawned per call because importing cv2
 * and fontTools costs a couple of seconds, and the UI re-slices on every grid
 * tweak. Requests are correlated to responses by id, so calls can overlap.
 */
class Backend {
  constructor({ onLog } = {}) {
    this.proc = null
    this.pending = new Map()
    this.nextId = 1
    this.onLog = onLog || (() => {})
    this.ready = null
  }

  scriptPath() {
    return isDev
      ? path.join(__dirname, '..', 'scripts', 'backend.py')
      : path.join(process.resourcesPath, 'scripts', 'backend.py')
  }

  pythonPath() {
    // Packaged builds ship their own interpreter; in dev, use whatever python3
    // is on PATH so the app tracks the repo's environment.
    return isDev
      ? 'python3'
      : path.join(process.resourcesPath, 'python', 'bin', 'python3')
  }

  start() {
    if (this.proc) return this.ready

    this.ready = new Promise((resolve, reject) => {
      this.proc = spawn(this.pythonPath(), ['-u', this.scriptPath()], {
        stdio: ['pipe', 'pipe', 'pipe'],
      })

      this.proc.on('error', (err) => {
        this.onLog(`backend failed to start: ${err.message}`)
        reject(err)
      })

      this.proc.on('exit', (code) => {
        this.onLog(`backend exited (${code})`)
        // Fail every in-flight call rather than leaving the UI spinning.
        for (const { reject: rj } of this.pending.values()) {
          rj(new Error('backend exited'))
        }
        this.pending.clear()
        this.proc = null
      })

      readline.createInterface({ input: this.proc.stdout }).on('line', (line) => {
        let msg
        try {
          msg = JSON.parse(line)
        } catch {
          this.onLog(line) // not a response; treat as output
          return
        }

        if (msg.event === 'ready') {
          resolve()
          return
        }

        const entry = this.pending.get(msg.id)
        if (!entry) return
        this.pending.delete(msg.id)

        if (msg.ok) entry.resolve(msg.result)
        else entry.reject(new Error(msg.error))
      })

      // The pipeline's own progress output arrives here, not on stdout, so it
      // cannot corrupt the response stream.
      readline.createInterface({ input: this.proc.stderr }).on('line', (line) => {
        this.onLog(line)
      })
    })

    return this.ready
  }

  async call(method, params) {
    await this.start()
    if (!this.proc) throw new Error('backend is not running')

    const id = this.nextId++
    const promise = new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
    })

    this.proc.stdin.write(JSON.stringify({ id, method, params }) + '\n')
    return promise
  }

  stop() {
    this.proc?.kill()
    this.proc = null
  }
}

module.exports = { Backend }
