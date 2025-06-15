const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let backendProcess;

function createWindow() {
    const win = new BrowserWindow({
        width: 800,
        height: 600,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
        },
        icon: path.join(__dirname, 'assets', 'logo.ico'),
        autoHideMenuBar: true, // Automatically hide the menu bar
    });

    win.loadFile('index.html');

    Windows
    const backendPath = path.join(__dirname,'chess_backend_', 'chess_backend.exe');
    backendProcess = spawn(backendPath);

    // //Linux
    // const backendPath = path.join(__dirname,'chess_backend_', 'chess_backend');
    // backendProcess = spawn(backendPath);

    // // Path to the Python script
    // const pythonScriptPath = path.join(__dirname,'backend', 'app.py');
    // backendProcess = spawn('python', [pythonScriptPath]);

    backendProcess.stdout.on('data', (data) => {
        const message = JSON.parse(data.toString());
        if (message.type === 'speak') {
            console.log(`System says: ${message.message}`);
            win.webContents.send('backend-message', message);
        } else if (message.type === 'board') {
            console.log(`Updated board: \n${message.board}`);
            win.webContents.send('board-update', message.board);
        }
    });

    backendProcess.stderr.on('data', (data) => {
        console.error(`Backend error: ${data}`);
    });

    backendProcess.on('close', (code) => {
        console.log(`Backend process exited with code ${code}`);
    });

    // Listen for the player's move from the renderer process.
    ipcMain.on('player-move', (event, move) => {
        // Send the move to the backend process.
        if (backendProcess) {
            backendProcess.stdin.write(`${move}\n`)
        }
    });
}

app.whenReady().then(createWindow);

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('before-quit', () => {
    if (backendProcess) {
        backendProcess.kill();
    }
});
