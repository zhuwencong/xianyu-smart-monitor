type WebSocketEventHandler = (data: any) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectInterval = 3000;
  private listeners: Map<string, WebSocketEventHandler[]> = new Map();
  public isConnected = false;
  private shouldConnect = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    // 由后端会话校验成功后调用 start，不能信任 localStorage 标记。
  }

  public start() {
    // 手动启动 WebSocket 连接
    this.shouldConnect = true;
    if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
      this.connect();
    }
  }

  public stop() {
    // 停止 WebSocket 连接
    this.shouldConnect = false;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      const socket = this.ws;
      this.ws = null;
      socket.close();
    }
    this.isConnected = false;
  }

  private connect() {
    if (!this.shouldConnect) return;
    this.reconnectTimer = null;
    // Determine the protocol (ws or wss) based on the current page protocol
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host; // This includes port if present

    const url = `${protocol}//${host}/ws`;

    console.log(`Connecting to WebSocket at ${url}`);
    const socket = new WebSocket(url);
    this.ws = socket;

    socket.onopen = () => {
      if (this.ws !== socket) {
        socket.close();
        return;
      }
      console.log('WebSocket connected');
      this.isConnected = true;
      this.emit('connected', { isConnected: true });
    };

    socket.onmessage = (event) => {
      if (this.ws !== socket) return;
      try {
        const message = JSON.parse(event.data);
        // Expecting message format: { type: 'event_type', data: ... }
        if (message.type) {
          this.emit(message.type, message.data);
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message', e);
      }
    };

    socket.onclose = (event) => {
      if (this.ws !== socket) return;
      this.ws = null;
      if (this.isConnected) {
        console.log('WebSocket disconnected');
        this.isConnected = false;
        this.emit('disconnected', { isConnected: false });
      }
      if (event.code === 1008) {
        this.shouldConnect = false;
      }
      if (this.shouldConnect) {
        this.reconnectTimer = setTimeout(() => this.connect(), this.reconnectInterval);
      }
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      // Close will trigger onclose which handles reconnect
      socket.close();
    };
  }

  public on(event: string, handler: WebSocketEventHandler) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event)?.push(handler);
  }

  public off(event: string, handler: WebSocketEventHandler) {
    const handlers = this.listeners.get(event);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index !== -1) {
        handlers.splice(index, 1);
      }
    }
  }

  private emit(event: string, data: any) {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.forEach((handler) => handler(data));
    }
  }
}

// Export a singleton instance
export const wsService = new WebSocketService();
