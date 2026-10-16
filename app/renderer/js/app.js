/* Knights Talk UI: wires the backend events to the board, the log, voice input and speech output. */
(function () {
    const $ = (id) => document.getElementById(id);
    const api = window.knights;
    const { pieceImage } = window.ChessNames;

    // ---- preferences (remembered between runs when storage is available) -------------------
    const prefs = {
        voiceURI: '', rate: 1, volume: 1, sensitivity: 3, contrast: false, speakMoves: true,
        level: 8, color: 'white', mic: true,
    };
    try { Object.assign(prefs, JSON.parse(localStorage.getItem('knights-talk-prefs') || '{}')); } catch (e) { /* ignore */ }
    function savePrefs() {
        try { localStorage.setItem('knights-talk-prefs', JSON.stringify(prefs)); } catch (e) { /* ignore */ }
    }

    const LEVELS = ['Beginner', 'Beginner', 'Beginner', 'Beginner', 'Casual', 'Casual', 'Casual', 'Casual', 'Club', 'Club',
        'Club', 'Club', 'Strong', 'Strong', 'Strong', 'Strong', 'Expert', 'Expert', 'Master', 'Master', 'Maximum'];
    const levelName = (n) => `${n} – ${LEVELS[n]}`;

    const speaker = new window.Speaker();
    const app = { state: null, thinking: false, recognizing: false, micWanted: prefs.mic, result: null, backendDown: false };

    // ---- log ------------------------------------------------------------------------------------
    function log(text, kind) {
        const item = document.createElement('div');
        item.className = `bubble ${kind}`;
        item.textContent = text;
        $('log').appendChild(item);
        while ($('log').childElementCount > 80) $('log').firstChild.remove();
        $('log').scrollTop = $('log').scrollHeight;
    }

    function say(text, { log: doLog = true, force = false } = {}) {
        if (doLog) log(text, 'system');
        if (force || prefs.speakMoves) speaker.say(text);
    }

    function banner(text, action) {
        const el = $('banner');
        el.textContent = '';
        document.body.classList.toggle('has-banner', !!text);
        if (!text) { el.hidden = true; return; }
        const span = document.createElement('span');
        span.textContent = text;
        el.appendChild(span);
        if (action) {
            const b = document.createElement('button');
            b.className = 'ghost';
            b.textContent = action.label;
            b.addEventListener('click', action.run);
            el.appendChild(b);
        }
        el.hidden = false;
    }

    // ---- status pill / mic ----------------------------------------------------------------------
    function refreshStatus() {
        const s = app.state;
        let state = 'idle', text = 'Ready';
        if (app.backendDown) { state = 'error'; text = 'Engine offline'; }
        else if (app.thinking) { state = 'busy'; text = 'Stockfish is thinking…'; }
        else if (app.recognizing) { state = 'busy'; text = 'Understanding you…'; }
        else if (!s || !s.active) { text = s && s.result ? 'Game over' : 'Say “start game”'; }
        else if (s.turn === s.playerColor) { state = 'turn'; text = 'Your move'; }
        $('statusPill').dataset.state = state;
        $('statusText').textContent = text;
        refreshMic();
    }

    function pauseVoice() {
        voice.paused = speaker.busy || app.thinking || app.recognizing;
    }

    function refreshMic(micState) {
        if (micState) app.micState = micState;
        const on = voice.running;
        const state = !on ? 'off' : voice.speaking ? 'hearing' : voice.paused ? 'paused' : 'listening';
        const copy = {
            off: ['Microphone off', 'Press M or click to start hands-free listening'],
            listening: ['Listening…', 'Say your move, for example “e 2 to e 4”'],
            hearing: ['Hearing you…', 'Pause when you are finished'],
            paused: ['Please wait', 'Listening resumes after the reply'],
        }[state];
        $('micTitle').textContent = copy[0];
        $('micHint').textContent = copy[1];
        $('micButton').dataset.state = state;
        $('micButton').setAttribute('aria-pressed', on ? 'true' : 'false');
        $('micButton').setAttribute('aria-label', on ? 'Microphone on. Press to stop listening' : 'Microphone off. Press to start listening');
    }

    const voice = new window.VoiceInput({
        onUtterance: (pcm, rate) => {
            app.recognizing = true;
            clearTimeout(app.recognizeTimer);
            app.recognizeTimer = setTimeout(() => { app.recognizing = false; pauseVoice(); refreshStatus(); }, 20000);
            pauseVoice();
            refreshStatus();
            api.send({ cmd: 'audio', pcm, rate });
        },
        onLevel: (level) => $('micRing').style.setProperty('--level', level.toFixed(2)),
        onState: () => refreshMic(),
        onError: (err) => {
            app.micWanted = false;
            const denied = err && (err.name === 'NotAllowedError' || err.name === 'SecurityError');
            const missing = err && err.name === 'NotFoundError';
            const msg = denied
                ? 'Microphone access was blocked. Allow the microphone for Knights Talk in your system settings, or type your moves.'
                : missing ? 'No microphone was found. You can type your moves instead.'
                    : 'The microphone could not be started. You can type your moves instead.';
            banner(msg, { label: 'Try again', run: () => { banner(''); toggleMic(true); } });
            say(msg);
            refreshMic();
        },
    });
    voice.sensitivity = prefs.sensitivity;

    async function toggleMic(force) {
        const want = typeof force === 'boolean' ? force : !voice.running;
        app.micWanted = prefs.mic = want;
        savePrefs();
        if (want) { await voice.start(); } else { voice.stop(); }
        pauseVoice();
        refreshMic();
    }

    speaker.onBusyChange = () => {
        // Wait a beat after speech ends so the tail of our own voice isn't picked up.
        if (speaker.busy) { pauseVoice(); } else { setTimeout(pauseVoice, 450); }
        refreshMic();
    };

    // ---- rendering --------------------------------------------------------------------------------
    const board = new window.Board($('board'), {
        onMove: (from, to, promotion) => api.send({ cmd: 'move', from, to, promotion }),
        onAnnounce: (text) => { $('srAnnounce').textContent = text; },
        promotionPicker: $('promotionPicker'),
    });

    function renderCaptured(container, symbols) {
        container.textContent = '';
        let last = '';
        symbols.forEach((s) => {
            const img = document.createElement('img');
            img.src = pieceImage(s);
            img.alt = '';
            if (s.toLowerCase() === last) img.className = 'stacked';
            last = s.toLowerCase();
            container.appendChild(img);
        });
        container.setAttribute('aria-label', symbols.length ? `${symbols.length} pieces captured` : 'Nothing captured yet');
    }

    function renderState(s) {
        app.state = s;
        board.render(s);
        const mine = s.playerColor === 'white';
        // Pieces *you* captured are the other colour's pieces: byWhite holds black pieces.
        renderCaptured($('capturedByYou'), mine ? s.captured.byWhite : s.captured.byBlack);
        renderCaptured($('capturedByOpponent'), mine ? s.captured.byBlack : s.captured.byWhite);
        const ahead = mine ? s.balance : -s.balance;
        $('advYou').textContent = ahead > 0 ? `+${ahead}` : '';
        $('advOpponent').textContent = ahead < 0 ? `+${-ahead}` : '';
        $('colorBadge').textContent = s.playerColor;
        $('levelBadge').textContent = `Level ${s.level}`;

        const moves = $('moves');
        moves.textContent = '';
        for (let i = 0; i < s.history.length; i += 2) {
            const li = document.createElement('li');
            const w = document.createElement('span'); w.textContent = s.history[i];
            const b = document.createElement('span'); b.textContent = s.history[i + 1] || '';
            li.append(w, b);
            moves.appendChild(li);
        }
        moves.scrollTop = moves.scrollHeight;

        if (s.active) $('resultOverlay').hidden = true;
        const inGame = s.active || (s.result && s.history.length);
        $('startOverlay').hidden = !!inGame;
        ['hintButton', 'undoButton', 'drawButton', 'resignButton'].forEach((id) => { $(id).disabled = !s.active; });
        $('readButton').disabled = !s.active;
        refreshStatus();
    }

    function showResult(r) {
        app.result = r;
        $('resultIcon').textContent = r.outcome === 'win' ? '🏆' : r.outcome === 'draw' ? '🤝' : '♚';
        $('resultOverlay').dataset.outcome = r.outcome;
        $('resultHeadline').textContent = r.headline;
        const reason = r.reason === 'agreement' ? 'by agreement' : `by ${r.reason}`;
        $('resultDetail').textContent = r.outcome === 'draw' ? `Draw ${reason}.` : (r.reason === 'resignation' && r.outcome === 'loss' ? 'You resigned.' : `${r.outcome === 'win' ? 'You won' : 'Stockfish won'} ${reason}.`);
        $('resultScore').textContent = r.score;
        $('resultOverlay').hidden = false;
        $('playAgainButton').focus();
    }

    // ---- events from the backend ------------------------------------------------------------------
    api.onEvent((event) => {
        switch (event.type) {
            case 'state':
                renderState(event);
                break;
            case 'speak':
                say(event.message);
                break;
            case 'transcript':
                clearTimeout(app.recognizeTimer);
                app.recognizing = false;
                pauseVoice();
                if (event.heard && event.text) log(event.text, 'user');
                refreshStatus();
                break;
            case 'thinking':
                app.thinking = event.on;
                pauseVoice();
                refreshStatus();
                break;
            case 'game_over':
                // Show the dialog once the reply has been spoken, but never later than a few seconds.
                setTimeout(() => showResult(event), 400);
                break;
            case 'mic':
                if (event.on === false) toggleMic(false);
                break;
            case 'error':
                log(event.message, 'error');
                break;
            case 'backend_down':
                app.backendDown = true;
                app.thinking = false;
                refreshStatus();
                banner(event.message, { label: 'Restart engine', run: restartBackend });
                say(event.message + ' Use the restart button.', { force: true });
                break;
        }
    });

    function restartBackend() {
        app.backendDown = false;
        banner('');
        api.restartBackend();
        setTimeout(() => api.send({ cmd: 'hello' }), 400);
        refreshStatus();
    }

    // ---- user actions -------------------------------------------------------------------------------------
    function newGame(color) {
        $('resultOverlay').hidden = true;
        if (color) prefs.color = color;
        savePrefs();
        api.send({ cmd: 'new_game', color: prefs.color, level: prefs.level });
    }

    function sendText(text) {
        const clean = text.trim();
        if (!clean) return;
        log(clean, 'user');
        // Typed "new game" commands should honour the options on screen.
        api.send({ cmd: 'text', text: clean });
    }

    $('commandForm').addEventListener('submit', (e) => {
        e.preventDefault();
        sendText($('moveInput').value);
        $('moveInput').value = '';
    });
    $('startButton').addEventListener('click', () => {
        prefs.color = document.querySelector('input[name="color"]:checked').value;
        newGame();
    });
    $('playAgainButton').addEventListener('click', () => newGame());
    $('closeResultButton').addEventListener('click', () => { $('resultOverlay').hidden = true; });
    $('newButton').addEventListener('click', () => {
        const s = app.state;
        if (s && s.active && !confirm('Abandon the current game and start a new one?')) return;
        newGame();
    });
    $('hintButton').addEventListener('click', () => api.send({ cmd: 'hint' }));
    $('undoButton').addEventListener('click', () => api.send({ cmd: 'undo' }));
    $('readButton').addEventListener('click', () => api.send({ cmd: 'read_board' }));
    $('drawButton').addEventListener('click', () => api.send({ cmd: 'draw' }));
    $('resignButton').addEventListener('click', () => {
        if (confirm('Resign this game?')) api.send({ cmd: 'resign' });
    });
    $('micButton').addEventListener('click', () => toggleMic());
    $('micButton').addEventListener('click', () => $('micButton').blur());

    const levelSlider = $('levelSlider');
    levelSlider.value = prefs.level;
    $('levelLabel').textContent = levelName(prefs.level);
    levelSlider.addEventListener('input', () => {
        prefs.level = Number(levelSlider.value);
        $('levelLabel').textContent = levelName(prefs.level);
        savePrefs();
    });
    document.querySelectorAll('input[name="color"]').forEach((r) => { r.checked = r.value === prefs.color; });

    // ---- dialogs -----------------------------------------------------------------------------------------------
    function openDialog(overlay, focusId) {
        overlay.hidden = false;
        overlay.dataset.opener = document.activeElement ? document.activeElement.id : '';
        $(focusId).focus();
    }
    function closeDialog(overlay) {
        overlay.hidden = true;
        const opener = $(overlay.dataset.opener || '');
        if (opener) opener.focus();
    }
    $('settingsButton').addEventListener('click', () => openDialog($('settingsOverlay'), 'closeSettingsButton'));
    $('closeSettingsButton').addEventListener('click', () => closeDialog($('settingsOverlay')));
    $('helpButton').addEventListener('click', () => openDialog($('helpOverlay'), 'closeHelpButton'));
    $('closeHelpButton').addEventListener('click', () => closeDialog($('helpOverlay')));

    function fillVoices() {
        const select = $('voiceSelect');
        select.textContent = '';
        const auto = new Option('Automatic (English)', '');
        select.add(auto);
        speaker.voices.forEach((v) => select.add(new Option(`${v.name} (${v.lang})`, v.voiceURI)));
        select.value = prefs.voiceURI;
        if (select.value !== prefs.voiceURI) select.value = '';
        checkTts();
    }

    // Voices load asynchronously; judge "none" only after giving the system a moment.
    function checkTts() {
        const noVoice = speaker.voices.length === 0;
        if (noVoice && !app.ttsBanner && app.ttsChecked) {
            app.ttsBanner = true;
            banner('No text-to-speech voice was found on this computer, so replies can only be read on screen. ' +
                'On Linux install “speech-dispatcher” and “espeak-ng”, then restart Knights Talk.');
        } else if (!noVoice && app.ttsBanner) {
            app.ttsBanner = false;
            banner('');
        }
    }
    speaker.onVoicesChange = fillVoices;

    function bindSlider(id, outId, key, apply, format) {
        const el = $(id);
        el.value = prefs[key];
        const show = () => { $(outId).textContent = format(Number(el.value)); };
        show();
        el.addEventListener('input', () => { prefs[key] = Number(el.value); apply(prefs[key]); show(); savePrefs(); });
        apply(prefs[key]);
    }
    bindSlider('rateSlider', 'rateOut', 'rate', (v) => { speaker.rate = v; }, (v) => `${v.toFixed(1)}×`);
    bindSlider('volumeSlider', 'volumeOut', 'volume', (v) => { speaker.volume = v; }, (v) => `${Math.round(v * 100)}%`);
    bindSlider('sensSlider', 'sensOut', 'sensitivity', (v) => { voice.sensitivity = v; },
        (v) => ['', 'Low', 'Fairly low', 'Normal', 'High', 'Very high'][v]);
    $('voiceSelect').addEventListener('change', (e) => { prefs.voiceURI = e.target.value; speaker.voiceURI = prefs.voiceURI; savePrefs(); });
    speaker.voiceURI = prefs.voiceURI;
    $('contrastToggle').checked = prefs.contrast;
    $('contrastToggle').addEventListener('change', (e) => { prefs.contrast = e.target.checked; applyContrast(); savePrefs(); });
    function applyContrast() { document.body.classList.toggle('high-contrast', prefs.contrast); }
    applyContrast();
    $('speakMovesToggle').checked = prefs.speakMoves;
    $('speakMovesToggle').addEventListener('change', (e) => { prefs.speakMoves = e.target.checked; savePrefs(); });
    $('testVoiceButton').addEventListener('click', () => {
        speaker.stop();
        speaker.say('This is how Knights Talk will sound. Knight to f 3.');
    });

    // ---- keyboard shortcuts --------------------------------------------------------------------------------------
    document.addEventListener('keydown', (e) => {
        const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)
            && document.activeElement.type !== 'range' && document.activeElement.type !== 'radio'
            && document.activeElement.type !== 'checkbox';
        if (e.key === 'Escape') {
            speaker.stop();
            ['settingsOverlay', 'helpOverlay'].forEach((id) => { if (!$(id).hidden) closeDialog($(id)); });
            if (!$('resultOverlay').hidden) $('resultOverlay').hidden = true;
            board.hidePicker();
            return;
        }
        if (e.key === 'F1') { e.preventDefault(); $('helpButton').click(); return; }
        if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
        if (e.key === '/') { e.preventDefault(); $('moveInput').focus(); }
        else if (e.key === 'm' || e.key === 'M') { toggleMic(); }
        else if (e.key === 'Enter' && document.activeElement.tagName !== 'BUTTON') {
            if (!$('resultOverlay').hidden) $('playAgainButton').click();
            else if (!$('startOverlay').hidden) $('startButton').click();
        }
    });

    // ---- start-up ----------------------------------------------------------------------------------------------------
    api.send({ cmd: 'hello' });
    $('startButton').focus();
    refreshStatus();
    setTimeout(() => { app.ttsChecked = true; checkTts(); }, 2500);
    setTimeout(() => {
        say('Welcome to Knights Talk. Say start game, or press Enter, to begin. Say help at any time to hear your options.',
            { force: true });
    }, 600);
    if (prefs.mic) toggleMic(true);
})();
