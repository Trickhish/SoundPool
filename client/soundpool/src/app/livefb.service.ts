import { Injectable } from '@angular/core';
import { ApiService } from './api.service';
import { EventSource as es } from 'eventsource'
import { HttpClient } from '@angular/common/http';

@Injectable({
  providedIn: 'root'
})
export class LivefbService {
  constructor(
    private api: ApiService,
    private http: HttpClient
  ) { }

  listening = false;

  // Desired subscriptions — the single source of truth. Survives reconnects so
  // every channel is re-subscribed on a fresh connection (previously the queue
  // bookkeeping corrupted itself, silently dropping channels after a reconnect
  // so live `state` events never reached the browser).
  private callbacks: { [ev: string]: Function[] } = {};
  // Events already (re)subscribed on the CURRENT connection; cleared on reconnect.
  private serverSubbed = new Set<string>();
  private source: any = null;
  private lint: any = null;

  private startListening() {
    const eventSource = new es(`${ApiService.apiUrl}/event/sse`, {
      fetch: (input, init) =>
        fetch(input, {
          ...init,
          headers: { ...init?.headers, "x-token": localStorage.getItem("token") ?? "" },
        }),
    });
    this.source = eventSource;

    eventSource.onopen = () => {
      this.listening = true;
      // Fresh connection => nothing is subscribed server-side yet. Re-subscribe
      // every channel we care about (this also re-seeds each channel snapshot).
      this.serverSubbed.clear();
      for (const ev of Object.keys(this.callbacks)) {
        if (this.callbacks[ev].length) this.serverSubscribe(ev);
      }
    };

    eventSource.onmessage = (event) => {
      const [ev, dt] = JSON.parse(event.data);
      const cbs = this.callbacks[ev];
      if (cbs) for (const cb of cbs) cb(dt);
    };

    eventSource.onerror = () => {
      this.serverSubbed.clear();
      eventSource.close();
      this.listening = false;
    };
  }

  /** Tell the server this connection wants `ev` (deduped per connection). */
  private serverSubscribe(ev: string) {
    if (this.serverSubbed.has(ev)) return;
    this.serverSubbed.add(ev);   // optimistic; cleared on reconnect
    this.http.get(`${ApiService.apiUrl}/event/subscribe/${ev}`).subscribe({
      error: () => { this.serverSubbed.delete(ev); }   // allow a later retry
    });
  }

  launch() {
    if (this.listening) return;
    this.startListening();
    this.lint = setInterval(() => {
      if (!this.listening) this.startListening();
    }, 2000);
  }

  stop() {
    if (this.lint != null) clearInterval(this.lint);
    this.serverSubbed.clear();
    this.listening = false;
    try { this.source?.close(); } catch { }
  }

  subscribe(ev: string, cb: Function) {
    if (!this.callbacks[ev]) this.callbacks[ev] = [];
    if (!this.callbacks[ev].includes(cb)) this.callbacks[ev].push(cb);
    if (this.listening) this.serverSubscribe(ev);
  }
}
