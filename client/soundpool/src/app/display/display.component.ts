import { Component, OnInit, OnDestroy, NgZone } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { CommonModule } from '@angular/common';
import { ApiService } from '../api.service';
import { LivefbService } from '../livefb.service';
import QRCode from 'qrcode';

interface LyricLine { ms: number; line: string; dur?: number; }

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
      let upcoming = ci >= 0 ? q.slice(ci + 1) : q;
      // Repeat-all wraps: on the last track the next songs come from the top,
      // so "up next" shouldn't look empty.
      if (dt.repeat === 'all' && ci >= 0) upcoming = upcoming.concat(q.slice(0, ci));
      this.queue = upcoming
        .map((t: any) => ({ title: t.title, artist: t.artist, cover: t.cover, score: t.score || 0 }));
      this.preloadArtwork();
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

  // ── Mascot + event bursts ────────────────────────────────────────────────
  // Both are driven by the same activity events as the ticker, so the screen
  // visibly reacts to what people are actually doing in the room.
  bursts: { id: number; icon: string; x: number; y: number; parts: any[] }[] = [];
  private nextBurstId = 0;

  /** What each activity icon throws on screen. */
  private static REACTIONS: any = {
    '👋': ['🎉', '✨', '🎊'],
    '➕': ['♪', '♫', '♬'],
    '📀': ['♪', '♫', '💿'],
    '❤️': ['❤️', '💖', '✨'],
    '🎉': ['🎉', '🎊', '✨', '🥳'],
    '🤖': ['🎵'],
    '🔀': ['🔀', '✨'],
  };

  private react(icon: string, _text: string) {
    const burst = DisplayComponent.REACTIONS[icon];
    if (burst && this.info?.show_activity) this.spawnBurst(burst);
  }

  /** Confetti-style burst of emoji flying out from a random spot. */
  private spawnBurst(icons: string[]) {
    const id = ++this.nextBurstId;
    const x = 25 + Math.random() * 50;
    const y = 30 + Math.random() * 35;
    const parts = Array.from({ length: 18 }, () => {
      const a = Math.random() * Math.PI * 2;
      const d = 18 + Math.random() * 26;
      return {
        icon: icons[Math.floor(Math.random() * icons.length)],
        dx: Math.cos(a) * d + 'vh',
        dy: Math.sin(a) * d - 12 + 'vh',      // bias upward
        rot: (Math.random() * 720 - 360) + 'deg',
        delay: Math.random() * 0.25 + 's',
        size: (2.2 + Math.random() * 2.6) + 'vh',
      };
    });
    this.bursts = [...this.bursts, { id, icon: icons[0], x, y, parts }];
    setTimeout(() => this.zone.run(() => {
      this.bursts = this.bursts.filter(b => b.id !== id);
    }), 2600);
  }

  trackBurst = (_: number, b: { id: number }) => b.id;

  private recentActivity = new Map<string, number>();   // key -> last-seen ms
  private pushActivity(icon: string, text: string) {
    if (!text) return;
    if (!this.info?.show_activity) return;
    // Dedupe: the SSE delivery layer can hand the same event to a tab more than
    // once when a prior stale server-side client is still fanned into (a real
    // duplicate action wouldn't fire the exact same icon+text within 1.5s).
    const key = icon + '|' + text;
    const now = Date.now();
    const last = this.recentActivity.get(key) || 0;
    if (now - last < 1500) return;
    this.recentActivity.set(key, now);
    if (this.recentActivity.size > 40) {   // bounded cache
      const cutoff = now - 3000;
      for (const [k, t] of this.recentActivity) if (t < cutoff) this.recentActivity.delete(k);
    }
    this.react(icon, text);   // after the dedupe check, so bursts fire once
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
    // Title, cover and backdrop all read from `info.now_playing`. That used to
    // be refreshed only by the 4s poll, while the progress bar followed SSE —
    // so the track's text and artwork lagged seconds behind the bar. Keep them
    // on the live feed too.
    if (this.info) this.info.now_playing = np;
    if ((np?.id || null) !== this.nowId) {
      this.nowId = np?.id || null;
      // Snap the progress + lyric highlight to the new track immediately so we
      // don't briefly render the previous track's tail (a full progress bar for
      // ~250ms) while waiting for the next tick to recompute.
      this.posMs = this.lastPos;
      this.activeIdx = -1;
      this.loadLyrics();
    }
  }

  private applyInfo(i: any) {
    this.notFound = false;
    // The poll is for config (what to show, message, party). Once SSE is live it
    // owns now_playing — otherwise this 4s snapshot would keep stamping a stale
    // track back over the live one.
    const live = this.sseLive ? this.info?.now_playing : undefined;
    const hadLyrics = !!this.info?.show_lyrics;
    this.info = i;
    if (this.sseLive) this.info.now_playing = live;
    // Lyrics are normally fetched on a track change, so switching the toggle on
    // mid-song used to show nothing until the next song started.
    if (!hadLyrics && i.show_lyrics && this.nowId && !this.lyrics.length && !this.plain) {
      this.loadLyrics();
    }
    this.startSse(i.room_id);
    // Seed playback from the poll until the live SSE feed takes over.
    if (!this.sseLive) this.setPlayback(i.now_playing, i.position, !!i.playing);
    if (Array.isArray(i.queue)) { this.queue = i.queue; this.preloadArtwork(); }
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
        this.activeIdx = -1;   // start fresh so the first tick picks the new song's line, not the old index
        this.kickBg();         // lyrics rendering can leave the blur layer stale — nudge it
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
  /** Karaoke: lyrics fill the screen in big type, everything else steps aside. */
  get nextUp() { return this.queue.length ? this.queue[0] : null; }

  // ── Lyric lead-in ────────────────────────────────────────────────────────
  // During an intro or an instrumental break, fill a ring so singers know when
  // to come back in (the same cue Deezer gives).
  private static LEADIN_MIN_GAP = 4500;   // only for real gaps, not line changes
  private static LEADIN_WINDOW  = 5000;   // how long the ring is on screen

  /** When the current line stops being sung.
   *  Deezer gives a real per-line duration; LRC sources (LRCLIB/Musixmatch)
   *  don't, so estimate from the text — otherwise a slow song's long lines look
   *  identical to an instrumental break. */
  private lineEnd(i: number): number {
    if (i < 0) return 0;                       // before the first line = intro
    const l = this.lyrics[i];
    if (!l) return 0;
    if (l.dur && l.dur > 0) return l.ms + l.dur;
    const words = (l.line || '').trim();
    if (!words) return l.ms;
    const est = Math.min(6000, Math.max(1200, words.length * 90));   // ~11 chars/s
    return l.ms + est;
  }

  /** 0..1 while a lead-in is running, or null when there's nothing to count in. */
  get leadIn(): number | null {
    if (!this.lyrics.length || !this.playing) return null;
    const next = this.lyrics[this.activeIdx + 1];
    if (!next) return null;
    // Measure silence, not the distance between line starts.
    const gap = next.ms - this.lineEnd(this.activeIdx);
    if (gap < DisplayComponent.LEADIN_MIN_GAP) return null;
    const remaining = next.ms - this.posMs;
    if (remaining <= 0) return null;
    const window = Math.min(gap, DisplayComponent.LEADIN_WINDOW);
    if (remaining > window) return null;      // still early — nothing yet
    return 1 - remaining / window;
  }
  /** Circumference of the ring, for the stroke-dash trick. */
  readonly leadInCirc = 2 * Math.PI * 46;
  get leadInOffset(): number {
    const p = this.leadIn ?? 0;
    return this.leadInCirc * (1 - p);
  }
  get lyricsFull(): boolean { return !!this.info?.lyrics_full && this.showLyrics; }
  /** Queue takes the big right-hand column when lyrics aren't shown. */
  get queueInColumn(): boolean { return this.showQueue && !this.showLyrics && !this.lyricsFull; }
  /** Compact queue under the thumbnail when lyrics occupy the column. */
  get queueUnderThumb(): boolean { return this.showQueue && this.showLyrics && this.showPlayer && !this.lyricsFull; }
  /** Is there anything filling the right-hand column? */
  get hasRightCol(): boolean { return (this.showLyrics && !this.lyricsFull) || this.queueInColumn; }
  /** Fewer entries when compact under the thumbnail, more when full-column.
   *  The full column is kept short enough to always fit, so a row is never
   *  clipped in half at the container edge. */
  get queueShown() { return this.queue.slice(0, this.queueUnderThumb ? 2 : 5); }
  get showMessage(): boolean { return !!this.info?.show_message && !!(this.info?.message || '').trim(); }
  /** Skip-vote tally — only when enabled and at least one person has voted. */
  get showSkipVotes(): boolean { return !!this.info?.show_skipvotes && this.voteCount > 0; }
  get cover(): string { return this.info?.now_playing?.cover || 'soundpool_sqrd.png'; }
  /** Warm the browser cache with upcoming artwork so the cover and the blurred
   *  backdrop appear the instant the track changes instead of being fetched
   *  from Deezer's CDN at that moment. */
  private preloaded = new Set<string>();
  private preloadArtwork() {
    const urls = this.queue.slice(0, 3).map(q => q.cover).filter(Boolean);
    for (const u of urls) {
      if (this.preloaded.has(u)) continue;
      this.preloaded.add(u);
      const img = new Image();
      img.decoding = 'async';
      img.src = u;
    }
    if (this.preloaded.size > 60) this.preloaded.clear();   // keep it bounded
  }

  trackAct = (_: number, a: { id: number }) => a.id;
  fmt(ms: number): string {
    const s = Math.max(0, Math.floor((ms || 0) / 1000));
    return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
  }
}
