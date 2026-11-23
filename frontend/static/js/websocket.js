// WebSocket Client Manager for QueueLess
class QueueSocket {
    constructor() {
        this.socket = null;
        this.reconnectInterval = 2500;
        this.reconnectTimer = null;
        this.listeners = new Map();
        this.isConnected = false;
        this.connect();
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        try {
            this.socket = new WebSocket(wsUrl);

            this.socket.onopen = () => {
                this.isConnected = true;
                console.log("[QueueLess] WebSocket connected");
                this.dispatch('connected', { status: true });
                if (this.reconnectTimer) {
                    clearTimeout(this.reconnectTimer);
                    this.reconnectTimer = null;
                }
            };

            this.socket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleMessage(message);
                } catch (e) {
                    console.error("[QueueLess] Failed to parse message:", e);
                }
            };

            this.socket.onclose = () => {
                this.isConnected = false;
                this.dispatch('disconnected', { status: false });
                this.scheduleReconnect();
            };

            this.socket.onerror = (err) => {
                console.warn("[QueueLess] WebSocket error:", err);
                this.socket.close();
            };
        } catch (err) {
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        if (!this.reconnectTimer) {
            this.reconnectTimer = setTimeout(() => {
                this.reconnectTimer = null;
                this.connect();
            }, this.reconnectInterval);
        }
    }

    handleMessage(msg) {
        // Dispatch specific event and generic 'all'
        this.dispatch(msg.type, msg);
        this.dispatch('*', msg);

        // Native DOM custom event for page listeners
        window.dispatchEvent(new CustomEvent('queueless:event', { detail: msg }));
    }

    on(eventType, callback) {
        if (!this.listeners.has(eventType)) {
            this.listeners.set(eventType, []);
        }
        this.listeners.get(eventType).push(callback);
    }

    off(eventType, callback) {
        if (!this.listeners.has(eventType)) return;
        const list = this.listeners.get(eventType).filter(cb => cb !== callback);
        this.listeners.set(eventType, list);
    }

    dispatch(eventType, data) {
        const list = this.listeners.get(eventType) || [];
        list.forEach(cb => {
            try { cb(data); } catch (e) { console.error(e); }
        });
    }

    send(data) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
        }
    }
}

window.queueSocket = new QueueSocket();
