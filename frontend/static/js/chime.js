// Audio Chime & Speech Synthesizer for QueueLess
class QueueAudioEngine {
    constructor() {
        this.audioCtx = null;
        this.soundEnabled = true;
        this.speechEnabled = true;
        this.speechVoice = null;
        this.initSpeech();
    }

    initContext() {
        if (!this.audioCtx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            this.audioCtx = new AudioContext();
        }
        if (this.audioCtx.state === 'suspended') {
            this.audioCtx.resume();
        }
    }

    initSpeech() {
        if ('speechSynthesis' in window) {
            const updateVoices = () => {
                const voices = window.speechSynthesis.getVoices();
                // Prefer clean English voice (Google US English, Samantha, Microsoft Zira/David)
                this.speechVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Zira') || v.name.includes('Samantha'))) 
                                || voices.find(v => v.lang.startsWith('en')) 
                                || voices[0];
            };
            window.speechSynthesis.onvoiceschanged = updateVoices;
            updateVoices();
        }
    }

    // Play smooth airport / clinic ding-dong chime
    playChime() {
        if (!this.soundEnabled) return;
        try {
            this.initContext();
            const ctx = this.audioCtx;
            const now = ctx.currentTime;

            // Tone 1: 587.33 Hz (D5)
            const osc1 = ctx.createOscillator();
            const gain1 = ctx.createGain();
            osc1.type = 'sine';
            osc1.frequency.setValueAtTime(587.33, now);
            gain1.gain.setValueAtTime(0.001, now);
            gain1.gain.exponentialRampToValueAtTime(0.35, now + 0.05);
            gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
            osc1.connect(gain1);
            gain1.connect(ctx.destination);
            osc1.start(now);
            osc1.stop(now + 0.55);

            // Tone 2: 440 Hz (A4)
            const osc2 = ctx.createOscillator();
            const gain2 = ctx.createGain();
            osc2.type = 'sine';
            osc2.frequency.setValueAtTime(440.0, now + 0.25);
            gain2.gain.setValueAtTime(0.001, now + 0.25);
            gain2.gain.exponentialRampToValueAtTime(0.4, now + 0.30);
            gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.95);
            osc2.connect(gain2);
            gain2.connect(ctx.destination);
            osc2.start(now + 0.25);
            osc2.stop(now + 0.95);
        } catch (e) {
            console.warn("Chime audio playback prevented or not permitted:", e);
        }
    }

    // Speak announcement e.g. "Token A 1 0 1, please proceed to Counter 1"
    speak(tokenNumber, counterName) {
        if (!this.speechEnabled || !('speechSynthesis' in window)) return;
        try {
            // Cancel any ongoing speech
            window.speechSynthesis.cancel();

            // Format token number to pronounce clearly: "A D M, 1, 0, 1"
            const parts = tokenNumber.split('-');
            let spokenToken = tokenNumber;
            if (parts.length === 2) {
                const prefixSpaced = parts[0].split('').join(' ');
                spokenToken = `${prefixSpaced}, ${parts[1]}`;
            }

            const text = `Attention please. Token ${spokenToken}, please proceed to ${counterName}.`;
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 0.92;
            utterance.pitch = 1.05;
            if (this.speechVoice) {
                utterance.voice = this.speechVoice;
            }

            // Small delay to let the ding-dong chime finish
            setTimeout(() => {
                window.speechSynthesis.speak(utterance);
            }, 600);
        } catch (e) {
            console.warn("Speech synthesis error:", e);
        }
    }

    announce(tokenNumber, counterName) {
        this.playChime();
        this.speak(tokenNumber, counterName);
    }
}

window.queueAudio = new QueueAudioEngine();
