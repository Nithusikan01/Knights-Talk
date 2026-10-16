const { contextBridge, ipcRenderer } = require('electron');

// The only door between the page and the system: JSON commands out, JSON events in.
contextBridge.exposeInMainWorld('knights', {
    send: (command) => ipcRenderer.send('backend-send', command),
    onEvent: (callback) => {
        ipcRenderer.on('backend-event', (_event, payload) => callback(payload));
    },
    restartBackend: () => ipcRenderer.send('backend-restart'),
});
