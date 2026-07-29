import { Component, OnInit, OnDestroy, NgZone } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { CommonModule } from '@angular/common';
import { ApiService } from '../api.service';
import QRCode from 'qrcode';

interface LyricLine { ms: number; line: string; }

/**
 * Big-screen display mode — a public, read-only view of a room meant for a TV
 * or projector. Reached via a shareable /display/:code link (no login). Shows
 * the now-playing track, synced lyrics, a party-join QR while a party is live,
 * and an admin-authored message. Everything the admin toggles in room settings.
 *
 * Fully polled (every 2s) so it needs no auth/token; playback position is
 * interpolated locally between polls for a smooth progress bar + lyric sync.
 */
@Component({
  selector: 'app-display',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './display.component.html',
  styleUrl: './display.component.scss'
})
export class DisplayComponent implements OnInit, OnDestroy {
  code = '';
  info: any = null;
  notFound = false;

  nowId: string | null = null;
  lyrics: LyricLine[] = [];
  plain = '';
  lyricsLoading = false;
  activeIdx = -1;

  posMs = 0;
  private lastPos = 0;
  private lastAt = 0;
  playing = false;
  durMs = 0;

  qr: string | null = null;
  private qrForCode: string | null = null;

  private pollTimer: any = null;
  private tickTimer: any = null;

  constructor(private aroute: ActivatedRoute, private api: ApiService, private zone: NgZone) {}

  ngOnInit() {
    this.code = this.aroute.snapshot.paramMap.get('code') || '';
    this.poll();
    this.pollTimer = setInterval(() => this.poll(), 2000);
    this.tickTimer = setInterval(() => this.zone.run(() => this.tick()), 250);
  }

  ngOnDestroy() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.tickTimer) clearInterval(this.tickTimer);
  }

  private poll() {
    this.api.displayInfo(this.code).subscribe({
      next: (i) => this.zone.run(() => this.applyInfo(i)),
      error: (e) => this.zone.run(() => { if (e?.status === 404) this.notFound = true; })
    });
  }

  private applyInfo(i: any) {
    this.notFound = false;
    this.info = i;
    const np = i.now_playing;
    this.playing = !!i.playing;
    this.durMs = np?.duration || 0;
    this.lastPos = i.position || 0;
    this.lastAt = Date.now();

    if ((np?.id || null) !== this.nowId) {
      this.nowId = np?.id || null;
      this.loadLyrics();
    }

    // Party-join QR — only while a party is live and the admin enabled it.
    const wantQr = i.party_active && i.show_qr && i.party_code;
    if (wantQr && i.party_code !== this.qrForCode) {
      this.qrForCode = i.party_code;
      const link = `${window.location.origin}/party/${i.party_code}`;
      QRCode.toDataURL(link, { width: 320, margin: 1 })
        .then(url => this.zone.run(() => { this.qr = url; })).catch(() => {});
    } else if (!wantQr) {
      this.qr = null;
      this.qrForCode = null;
    }
  }

  private loadLyrics() {
    this.lyrics = [];
    this.plain = '';
    this.activeIdx = -1;
    if (!this.nowId || !this.info?.show_lyrics) return;
    this.lyricsLoading = true;
    this.api.displayLyrics(this.code, this.nowId).subscribe({
      next: (r) => this.zone.run(() => {
        this.lyrics = r?.synced || [];
        this.plain = r?.plain || '';
        this.lyricsLoading = false;
      }),
      error: () => this.zone.run(() => { this.lyricsLoading = false; })
    });
  }

  private tick() {
    this.posMs = this.playing ? this.lastPos + (Date.now() - this.lastAt) : this.lastPos;
    if (this.lyrics.length) {
      let idx = -1;
      for (let k = 0; k < this.lyrics.length; k++) {
        if (this.lyrics[k].ms <= this.posMs) idx = k; else break;
      }
      if (idx !== this.activeIdx) {
        this.activeIdx = idx;
        this.scrollActive();
      }
    }
  }

  private scrollActive() {
    setTimeout(() => {
      const el = document.querySelector(`#lyric-${this.activeIdx}`) as HTMLElement | null;
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 0);
  }

  get progressPct(): number {
    return this.durMs > 0 ? Math.min(100, (this.posMs / this.durMs) * 100) : 0;
  }
  get showPlayer(): boolean { return !!this.info?.show_player; }
  get showLyrics(): boolean { return !!this.info?.show_lyrics; }
  get showMessage(): boolean { return !!this.info?.show_message && !!(this.info?.message || '').trim(); }
  get cover(): string { return this.info?.now_playing?.cover || 'soundpool_sqrd.png'; }
  fmt(ms: number): string {
    const s = Math.max(0, Math.floor((ms || 0) / 1000));
    return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
  }
}
