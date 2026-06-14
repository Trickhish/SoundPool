import { Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../api.service';

type DeezerState = 'unknown' | 'connected' | 'disconnected' | 'pending' | 'loading';

@Component({
  selector: 'app-profile',
  imports: [CommonModule],
  templateUrl: './profile.component.html',
  styleUrl: './profile.component.scss'
})
export class ProfileComponent implements OnDestroy {
  deezerState: DeezerState = 'unknown';
  deezerCode: string = '';
  deezerJourneyUrl: string = '';
  deezerQrUrl: string = '';
  pollInterval: number = 2;
  private pollTimer: any = null;

  constructor(public api: ApiService) {}

  ngOnInit() {
    this.api.deezerStatus().subscribe({
      next: (r) => { this.deezerState = r.connected ? 'connected' : 'disconnected'; },
      error: () => { this.deezerState = 'disconnected'; }
    });
  }

  ngOnDestroy() { this.stopPolling(); }

  connectDeezer() {
    this.deezerState = 'loading';
    this.api.deezerLoginStart().subscribe({
      next: (r: any) => {
        this.deezerCode = r.code;
        this.deezerJourneyUrl = r.journey_url;
        this.deezerQrUrl = r.qr_url || '';
        this.pollInterval = r.poll_interval;
        this.deezerState = 'pending';
        this.startPolling();
      },
      error: () => { this.deezerState = 'disconnected'; }
    });
  }

  disconnectDeezer() {
    this.api.deezerLogout().subscribe({ next: () => { this.deezerState = 'disconnected'; } });
  }

  private startPolling() {
    this.pollTimer = setInterval(() => {
      this.api.deezerLoginPoll().subscribe({
        next: (r) => {
          if (r.status === 'ok') { this.stopPolling(); this.deezerState = 'connected'; }
        },
        error: () => { this.stopPolling(); this.deezerState = 'disconnected'; }
      });
    }, this.pollInterval * 1000);
  }

  private stopPolling() {
    if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
  }

  cancelLogin() { this.stopPolling(); this.deezerState = 'disconnected'; }
}
