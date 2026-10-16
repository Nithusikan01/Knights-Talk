/*
 * Hands-free microphone capture in the UI.
 *
 * Listens continuously, detects when the player starts and stops talking (simple
 * energy-based voice activity detection), and hands each utterance over as
 * 16 kHz mono 16-bit PCM so the backend can run speech recognition on it.
 * Nothing here needs a microphone on the machine that runs the backend.
 */
(function () {
    const TARGET_RATE = 16000;
    const FRAME = 2048;            // samples per processing block
    const PRE_ROLL_S = 0.35;       // audio kept from before speech was detected
    const END_SILENCE_S = 0.8;     // silence that ends an utterance
    const MIN_SPEECH_S = 0.25;
    const MAX_UTTERANCE_S = 10;

    function downsample(float32, fromRate, toRate) {
        if (fromRate === toRate) return float32;
        const ratio = fromRate / toRate;
        const length = Math.floor(float32.length / ratio);
        const out = new Float32Array(length);
        for (let i = 0; i < length; i++) {
            const start = Math.floor(i * ratio);
            const end = Math.min(float32.length, Math.floor((i + 1) * ratio));
            let sum = 0;
            for (let j = start; j < end; j++) sum += float32[j];
            out[i] = sum / Math.max(1, end - start);
        }
        return out;
    }

    function toBase64Pcm16(float32) {
        const pcm = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
            const s = Math.max(-1, Math.min(1, float32[i]));
            pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        const bytes = new Uint8Array(pcm.buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i += 0x8000) {
            binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        }
        return btoa(binary);
    }

    class VoiceInput {
        constructor({ onUtterance, onLevel, onState, onError }) {
            this.onUtterance = onUtterance;
            this.onLevel = onLevel || (() => {});
            this.onState = onState || (() => {});
            this.onError = onError || (() => {});
            this.sensitivity = 3;   // 1 (needs loud speech) .. 5 (picks up quiet speech)
            this.paused = false;    // set while the app is speaking / waiting
            this.running = false;
            this.reset();
        }

        reset() {
            this.preRoll = [];
            this.chunks = [];
            this.speaking = false;
            this.loudRun = 0;
            this.silentSamples = 0;
            this.speechSamples = 0;
            this.totalSamples = 0;
            this.noiseFloor = 0.004;
        }

        async start() {
            if (this.running) return;
            try {
                this.stream = await navigator.mediaDevices.getUserMedia({
                    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
                });
            } catch (err) {
                this.onError(err);
                return;
            }
            this.context = new (window.AudioContext || window.webkitAudioContext)();
            if (this.context.state === 'suspended') await this.context.resume();
            this.source = this.context.createMediaStreamSource(this.stream);
            // ScriptProcessor is deprecated but works everywhere, including file:// pages in Electron.
            this.processor = this.context.createScriptProcessor(FRAME, 1, 1);
            this.mute = this.context.createGain();
            this.mute.gain.value = 0;           // keep the graph alive without echoing the mic
            this.processor.onaudioprocess = (e) => this.process(e.inputBuffer.getChannelData(0));
            this.source.connect(this.processor);
            this.processor.connect(this.mute);
            this.mute.connect(this.context.destination);
            this.reset();
            this.running = true;
            this.onState('listening');
        }

        stop() {
            if (!this.running) return;
            this.running = false;
            try { this.processor.disconnect(); this.source.disconnect(); } catch (e) { /* already gone */ }
            this.stream.getTracks().forEach((t) => t.stop());
            this.context.close();
            this.reset();
            this.onLevel(0);
            this.onState('off');
        }

        threshold() {
            // Higher sensitivity -> lower multiplier over the measured background noise.
            const multiplier = [0, 6, 4.5, 3.5, 2.8, 2.2][this.sensitivity];
            return Math.max(0.006 + (5 - this.sensitivity) * 0.003, this.noiseFloor * multiplier);
        }

        process(input) {
            const rate = this.context.sampleRate;
            let sum = 0;
            for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
            const rms = Math.sqrt(sum / input.length);
            this.onLevel(Math.min(1, rms * 8));

            if (this.paused) {
                // Don't hear our own voice; drop anything half-captured.
                if (this.speaking || this.chunks.length) this.discard();
                this.preRoll = [];
                return;
            }

            const block = new Float32Array(input);
            const loud = rms > this.threshold();

            if (!this.speaking) {
                if (!loud) this.noiseFloor = this.noiseFloor * 0.95 + rms * 0.05;
                this.preRoll.push(block);
                const keep = Math.ceil((PRE_ROLL_S * rate) / FRAME);
                while (this.preRoll.length > keep) this.preRoll.shift();
                this.loudRun = loud ? this.loudRun + 1 : 0;
                if (this.loudRun >= 2) {
                    this.speaking = true;
                    this.chunks = this.preRoll.slice();
                    this.preRoll = [];
                    this.silentSamples = 0;
                    this.speechSamples = 0;
                    this.totalSamples = this.chunks.length * FRAME;
                    this.onState('hearing');
                }
                return;
            }

            this.chunks.push(block);
            this.totalSamples += block.length;
            if (loud) {
                this.silentSamples = 0;
                this.speechSamples += block.length;
            } else {
                this.silentSamples += block.length;
            }
            const endedBySilence = this.silentSamples >= END_SILENCE_S * rate;
            const tooLong = this.totalSamples >= MAX_UTTERANCE_S * rate;
            if (endedBySilence || tooLong) this.finish(rate);
        }

        discard() {
            this.speaking = false;
            this.chunks = [];
            this.loudRun = 0;
            if (this.running) this.onState('listening');
        }

        finish(rate) {
            const spoken = this.speechSamples / rate;
            const chunks = this.chunks;
            this.discard();
            if (spoken < MIN_SPEECH_S) return;     // a click or cough, not a command
            const merged = new Float32Array(chunks.length * FRAME);
            chunks.forEach((c, i) => merged.set(c, i * FRAME));
            const pcm = toBase64Pcm16(downsample(merged, rate, TARGET_RATE));
            this.onUtterance(pcm, TARGET_RATE);
        }
    }

    window.VoiceInput = VoiceInput;
})();
