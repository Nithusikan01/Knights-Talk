const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

let win = null;
let backend = null;
let stdoutBuffer = '';
let quitting = false;

// ---- backend process ---------------------------------------------------

function backendCommand() {
    const exe = process.platform === 'win32' ? 'chess_backend.exe' : 'chess_backend';
    // Packaged app: the PyInstaller bundle is shipped as an extra resource.
    const bundled = path.join(process.resourcesPath || '', 'backend', exe);
    if (app.isPackaged && fs.existsSync(bundled)) {
        return { cmd: bundled, args: [], cwd: path.dirname(bundled) };
    }
    // Development: run the Python source.
    const script = path.join(__dirname, 'backend', 'app.py');
    const python = process.env.KNIGHTS_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    return { cmd: python, args: [script], cwd: path.join(__dirname, 'backend') };
}

function sendToUi(event) {
    if (win && !win.isDestroyed()) win.webContents.send('backend-event', event);
}

function startBackend() {
    stdoutBuffer = '';
    const { cmd, args, cwd } = backendCommand();
    const child = spawn(cmd, args, { cwd, env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' } });
    backend = child;

    // Output arrives in arbitrary chunks: split into lines before parsing JSON.
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
        stdoutBuffer += chunk;
        let nl;
        while ((nl = stdoutBuffer.indexOf('\n')) >= 0) {
            const line = stdoutBuffer.slice(0, nl).trim();
            stdoutBuffer = stdoutBuffer.slice(nl + 1);
            if (!line) continue;
            try {
                sendToUi(JSON.parse(line));
            } catch (err) {
                console.error('Unparseable backend output:', line);
            }
        }
    });
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (data) => console.error(`Backend: ${data}`));
    child.stdin.on('error', () => { /* backend is gone; the exit handler reports it */ });

    child.on('error', (err) => {
        sendToUi({ type: 'backend_down', message: `Could not start the chess backend: ${err.message}` });
    });
    child.on('close', (code) => {
        if (backend === child) backend = null;
        if (!quitting) {
            sendToUi({ type: 'backend_down', message: `The chess backend stopped (code ${code}).` });
        }
    });
}

function stopBackend() {
    if (backend) {
        const child = backend;
        backend = null;
        try { child.stdin.write(JSON.stringify({ cmd: 'quit' }) + '\n'); } catch (e) { /* ignore */ }
        setTimeout(() => child.kill(), 500);
    }
}

ipcMain.on('backend-send', (_event, command) => {
    if (backend && backend.stdin.writable) {
        backend.stdin.write(JSON.stringify(command) + '\n');
    }
});

ipcMain.on('backend-restart', () => {
    stopBackend();
    startBackend();
});

// ---- window -------------------------------------------------------------------

function createWindow() {
    // The microphone is recorded in the UI, so allow media capture for our own pages only.
    const allowed = (permission) => permission === 'media' || permission === 'audioCapture';
    session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => callback(allowed(permission)));
    session.defaultSession.setPermissionCheckHandler((_wc, permission) => allowed(permission));

    win = new BrowserWindow({
        width: 1280,
        height: 860,
        minWidth: 900,
        minHeight: 640,
        backgroundColor: '#14161c',
        title: 'Knights Talk',
        icon: path.join(__dirname, 'assets', 'logo.ico'),
        autoHideMenuBar: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            autoplayPolicy: 'no-user-gesture-required', // speak and listen without a click first
        },
    });
    win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
    win.on('closed', () => { win = null; });
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
    app.quit();
} else {
    app.on('second-instance', () => {
        if (win) {
            if (win.isMinimized()) win.restore();
            win.focus();
        }
    });
    app.whenReady().then(() => {
        createWindow();
        startBackend();
    });
}

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => {
    quitting = true;
    stopBackend();
});
