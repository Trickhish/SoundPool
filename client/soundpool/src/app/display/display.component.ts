import { Component, OnInit, OnDestroy, NgZone } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { CommonModule } from '@angular/common';
import { ApiService } from '../api.service';
import { LivefbService } from '../livefb.service';
import QRCode from 'qrcode';

interface LyricLine { ms: number; line: string; }

/**
 * Big-screen display mode — a public, read-only view of a room meant for a TV
 * or projector. Reached via a shareable /display/:code link (no login). Shows
 * the now-playing track, synced lyrics, a party-join QR while a party is live,
 * and an admin-authored message. Everything the admin toggles in room settings.
 *
 * Playback (song / position / pause / seek) rides the live SSE feed so it
 * reacts instantly; a slow poll refreshes the admin config (what to show,
 * message, party QR). Position is interpolated locally for a smooth bar.
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
  queue: { title: string; artist: string; cover: string; score: number }[] = [];
  votingEnabled = false;
  voteCount = 0;         // people who voted to skip the current track
  voteThreshold = 0;     // votes needed to skip

  // Live activity ticker — small stack of recent one-liners, each self-expires.
  activity: { id: number; icon: string; text: string }[] = [];
  private nextActId = 0;
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
  private sseStarted = false;
  private sseLive = false;   // true once live playback events arrive

  constructor(private aroute: ActivatedRoute, private api: ApiService,
              private zone: NgZone, private event: LivefbService) {}

  ngOnInit() {
    this.code = this.aroute.snapshot.paramMap.get('code') || '';
    this.poll();
    this.pollTimer = setInterval(() => this.poll(), 4000);   // config/message/party only
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

  /** Once we know the room id, wire up the live SSE feed for snappy playback.
   *  Reuse any existing token (e.g. a logged-in admin previewing); otherwise
   *  mint a throwaway display token so a public TV can subscribe. */
  private startSse(roomId: number) {
    if (this.sseStarted) return;
    this.sseStarted = true;
    const go = () => {
      this.event.subscribe(`room_${roomId}`, (dt: any) => this.zone.run(() => this.onSse(dt)));
      this.event.launch();
    };
    if (localStorage.getItem('token')) { go(); return; }
    this.api.displayToken(this.code).subscribe({
      next: (r) => { localStorage.setItem('token', r.token); go(); },
      error: () => { this.sseStarted = false; }   // keep polling as the fallback
    });
  }

  private onSse(dt: any) {
    if (!dt) return;
    this.sseLive = true;
    if (dt.type === 'state') {
      this.setPlayback(dt.now_playing ?? null, dt.position ?? 0, !!dt.playing);
      this.votingEnabled = !!dt.voting_enabled;
      this.voteCount = dt.vote_count ?? 0;
      this.voteThreshold = dt.vote_threshold ?? 0;
      const q = dt.queue || [];
      const ci = dt.current_index ?? -1;
      this.queue = (ci >= 0 ? q.slice(ci + 1) : q)
        .map((t: any) => ({ title: t.title, artist: t.artist, cover: t.cover, score: t.score || 0 }));
    } else if (dt.type === 'progress') {
      this.durMs = parseFloat(dt.duration) || this.durMs;
      this.lastPos = parseFloat(dt.progress) || 0;
      this.lastAt = Date.now();
    } else if (dt.type === 'status') {
      if (dt.status === 'paused') this.playing = false;
      else if (dt.status === 'playing') this.playing = true;
    } else if (dt.type === 'activity') {
      this.pushActivity(dt.icon || '🎵', dt.text || '');
    }
  }

  private pushActivity(icon: string, text: string) {
    if (!text || !this.info?.show_activity) return;
    const id = ++this.nextActId;
    this.activity = [...this.activity, { id, icon, text }];
    if (this.activity.length > 4) this.activity = this.activity.slice(-4);   // keep it tidy
    setTimeout(() => this.zone.run(() => {
      this.activity = this.activity.filter(a => a.id !== id);
    }), 6500);   // self-expire after ~6.5s
  }

  /** Apply a now-playing snapshot (from a poll or an SSE state event). */
  private setPlayback(np: any, position: number, playing: boolean) {
    this.playing = playing;
    this.durMs = np?.duration || 0;
    this.lastPos = position || 0;
    this.lastAt = Date.now();
    if ((np?.id || null) !== this.nowId) {
      this.nowId = np?.id || null;
      this.loadLyrics();
    }
  }

  private applyInfo(i: any) {
    this.notFound = false;
    this.info = i;
    this.startSse(i.room_id);
    // Seed playback from the poll until the live SSE feed takes over.
    if (!this.sseLive) this.setPlayback(i.now_playing, i.position, !!i.playing);
    if (Array.isArray(i.queue)) this.queue = i.queue;
    this.votingEnabled = !!i.voting_enabled;
    this.voteCount = i.vote_count ?? 0;
    this.voteThreshold = i.vote_threshold ?? 0;

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
        this.kickBg();   // lyrics rendering can leave the blur layer stale — nudge it
      }),
      error: () => this.zone.run(() => { this.lyricsLoading = false; })
    });
  }

  /** Force the backdrop's composited blur layer to re-rasterize (same effect as
   *  poking a size property by hand), guarding against a stale bottom gap. */
  private kickBg() {
    requestAnimationFrame(() => {
      const bg = document.querySelector('.disp-bg') as HTMLElement | null;
      if (!bg) return;
      bg.style.transform = 'translateZ(0) scale(1.0001)';
      requestAnimationFrame(() => { bg.style.transform = ''; });
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
      // Scroll only the lyrics container — never scrollIntoView, which can also
      // scroll the page/host and disturb the full-screen backdrop layout.
      const scroll = document.querySelector('.disp-lyr-scroll') as HTMLElement | null;
      const el = document.querySelector(`#lyric-${this.activeIdx}`) as HTMLElement | null;
      if (!scroll || !el) return;
      const top = el.offsetTop - scroll.clientHeight / 2 + el.offsetHeight / 2;
      scroll.scrollTo({ top, behavior: 'smooth' });
    }, 0);
  }

  get progressPct(): number {
    return this.durMs > 0 ? Math.min(100, (this.posMs / this.durMs) * 100) : 0;
  }
  get showPlayer(): boolean { return !!this.info?.show_player; }
  get showLyrics(): boolean { return !!this.info?.show_lyrics; }
  get showQueue(): boolean { return !!this.info?.show_queue; }
  /** Queue takes the big right-hand column when lyrics aren't shown. */
  get queueInColumn(): boolean { return this.showQueue && !this.showLyrics; }
  /** Compact queue under the thumbnail when lyrics occupy the column. */
  get queueUnderThumb(): boolean { return this.showQueue && this.showLyrics && this.showPlayer; }
  /** Is there anything filling the right-hand column? */
  get hasRightCol(): boolean { return this.showLyrics || this.queueInColumn; }
  /** Fewer entries when compact under the thumbnail, more when full-column. */
  get queueShown() { return this.queue.slice(0, this.queueUnderThumb ? 2 : 9); }
  get showMessage(): boolean { return !!this.info?.show_message && !!(this.info?.message || '').trim(); }
  /** Skip-vote tally — only when enabled and at least one person has voted. */
  get showSkipVotes(): boolean { return !!this.info?.show_skipvotes && this.voteCount > 0; }
  get cover(): string { return this.info?.now_playing?.cover || 'soundpool_sqrd.png'; }
  trackAct = (_: number, a: { id: number }) => a.id;
  fmt(ms: number): string {
    const s = Math.max(0, Math.floor((ms || 0) / 1000));
    return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
  }
}
