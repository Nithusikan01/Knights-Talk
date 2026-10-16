/* Text-to-speech in the UI, so the player hears the game on the machine they are sitting at. */
(function () {
    class Speaker {
        constructor() {
            this.supported = 'speechSynthesis' in window;
            this.voices = [];
            this.voiceURI = '';
            this.rate = 1;
            this.volume = 1;
            this.enabled = true;
            this.queue = [];
            this.busy = false;
            this.onBusyChange = () => {};
            this.onVoicesChange = () => {};
            if (this.supported) {
                this.refreshVoices();
                window.speechSynthesis.addEventListener('voiceschanged', () => this.refreshVoices());
            }
        }

        refreshVoices() {
            this.voices = window.speechSynthesis.getVoices();
            this.onVoicesChange(this.voices);
        }

        get available() {
            return this.supported && this.voices.length > 0;
        }

        pickVoice() {
            if (this.voiceURI) {
                const chosen = this.voices.find((v) => v.voiceURI === this.voiceURI);
                if (chosen) return chosen;
            }
            return this.voices.find((v) => /^en/i.test(v.lang) && v.default)
                || this.voices.find((v) => /^en/i.test(v.lang))
                || null;
        }

        say(text) {
            if (!this.enabled || !this.supported || !text) return;
            this.queue.push(text);
            this.pump();
        }

        pump() {
            if (this.busy || this.queue.length === 0) return;
            const utterance = new SpeechSynthesisUtterance(this.queue.shift());
            const voice = this.pickVoice();
            if (voice) utterance.voice = voice;
            utterance.lang = voice ? voice.lang : 'en-US';
            utterance.rate = this.rate;
            utterance.volume = this.volume;
            const done = () => {
                clearTimeout(watchdog);
                if (!this.busy) return;
                this.busy = false;
                this.onBusyChange(false);
                this.pump();
            };
            // Some platforms never fire "end"; never let the queue wedge.
            const budget = this.voices.length ? 3000 + utterance.text.length * 120 : 1500;
            const watchdog = setTimeout(done, budget);
            utterance.onend = done;
            utterance.onerror = done;
            this.busy = true;
            this.onBusyChange(true);
            window.speechSynthesis.speak(utterance);
        }

        stop() {
            this.queue = [];
            if (this.supported) window.speechSynthesis.cancel();
        }
    }

    window.Speaker = Speaker;
})();
