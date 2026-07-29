import { Injectable, NgZone } from '@angular/core';
import { ToastrService } from 'ngx-toastr';
import { ApiService } from './api.service';
import { LivefbService } from './livefb.service';

/**
 * App-wide "what am I controlling" state. Tracks the active room, mirrors its
 * live playback state over SSE, and exposes transport — so the now-playing bar
 * (and anything else) can drive playback from any page.
 */
@Injectable({ providedIn: 'root' })
export class PlaybackService {
  activeRoomId: number | null = null;
  roomName = '';
  nowPlaying: any = null;      // { id, title, artist, cover, duration }
  playing = false;
  rights: any = null;
  rightsLoaded = false;        // false until getRoom resolves (don't pre-disable)

  progress = 0;                // 0..100 for the progress bar
  private positionMs = 0;      // last reported position
  private durationMs = 0;
  private posAt = 0;           // timestamp positionMs was reported (for interpolation)

  constructor(private api: ApiService, private event: LivefbService, private zone: NgZone, private toastr: ToastrService) {
    const saved = localStorage.getItem('activeRoom');
    if (saved) this.setActiveRoom(+saved, localStorage.getItem('activeRoomName') || '');
    this.setupKeyboard();
    this.setupMediaSession();
    // Smoothly advance the progress bar between position reports (~1/s over SSE).
    setInterval(() => {
      if (this.playing && this.durationMs) this.zone.run(() => { this.progress = this.computeProgress(); });
    }, 250);
  }

  private computeProgress(): number {
    if (!this.durationMs) return 0;
    const pos = this.positionMs + (this.playing ? Date.now() - this.posAt : 0);
    return Math.max(0, Math.min(100, (pos / this.durationMs) * 100));
  }

  private setPosition(ms: number, dur?: number) {
    this.positionMs = ms;
    this.posAt = Date.now();
    if (dur) this.durationMs = dur;
    this.progress = this.computeProgress();
  }

  // ── Keyboard: Space toggles play/pause (unless you're typing) ──
  private setupKeyboard() {
    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && !this.isTyping(e)) {
        e.preventDefault();
        this.zone.run(() => this.toggle());
      }
    });
  }

  private isTyping(e: KeyboardEvent): boolean {
    const t = e.target as HTMLElement | null;
    if (!t) return false;
    const tag = t.tagName?.toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || !!t.isContentEditable;
  }

  // ── Hardware media keys (Media Session API) ──
  // The OS only routes media keys to a tab that is actually playing audio, but
  // the room usually plays on a unit. Hold a silent looping audio to claim the
  // media session so play/pause/next keys reach us. Autoplay needs a gesture.
  private keeper: HTMLAudioElement | null = null;

  private setupMediaSession() {
    const ms: any = (navigator as any).mediaSession;
    if (!ms) return;
    ms.setActionHandler('play', () => this.zone.run(() => { this.keeperPlay(); if (!this.playing) this.toggle(); }));
    ms.setActionHandler('pause', () => this.zone.run(() => { if (this.playing) this.toggle(); }));
    ms.setActionHandler('previoustrack', () => this.zone.run(() => this.prev()));
    ms.setActionHandler('nexttrack', () => this.zone.run(() => this.next()));

    // Start the keeper once (unlocks autoplay), then sync it to the room state.
    const arm = () => { this.keeperPlay(); this.reflect(); window.removeEventListener('pointerdown', arm); window.removeEventListener('keydown', arm); };
    window.addEventListener('pointerdown', arm);
    window.addEventListener('keydown', arm);
  }

  private keeperPlay() {
    if (!this.keeper) {
      this.keeper = new Audio(this.silentWav());
      this.keeper.loop = true;
    }
    this.keeper.play().catch(() => {});
  }

  /** A 1s silent WAV data URI — silent content at normal volume still counts as
   *  "playing audio", which is what grants the media session. */
  private silentWav(): string {
    const sr = 8000, n = sr; // 1 second, mono, 16-bit
    const buf = new ArrayBuffer(44 + n * 2);
    const dv = new DataView(buf);
    const wr = (o: number, s: string) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
    wr(0, 'RIFF'); dv.setUint32(4, 36 + n * 2, true); wr(8, 'WAVE'); wr(12, 'fmt ');
    dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
    dv.setUint32(24, sr, true); dv.setUint32(28, sr * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
    wr(36, 'data'); dv.setUint32(40, n * 2, true);
    let bin = ''; const u8 = new Uint8Array(buf);
    for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
    return 'data:audio/wav;base64,' + btoa(bin);
  }

  private updateMediaSession() {
    const nav: any = navigator;
    if (!nav.mediaSession) return;
    const np = this.nowPlaying;
    if (np && (window as any).MediaMetadata) {
      nav.mediaSession.metadata = new (window as any).MediaMetadata({
        title: np.title || '', artist: np.artist || '', album: this.roomName || '',
        artwork: np.cover ? [{ src: np.cover, sizes: '250x250', type: 'image/jpeg' }] : []
      });
    }
    nav.mediaSession.playbackState = this.playing ? 'playing' : 'paused';
  }

  /** Point the controller at a room and start mirroring its state. */
  setActiveRoom(id: number, name = '') {
    const same = this.activeRoomId === id;
    this.activeRoomId = id;
    if (name) this.roomName = name;
    localStorage.setItem('activeRoom', String(id));
    if (name) localStorage.setItem('activeRoomName', name);

    if (!same) {
      this.rightsLoaded = false;   // will be set once getRoom resolves below
      // SSE fires outside Angular's zone; re-enter it. Guard by id so a stale
      // room's events (we never explicitly unsubscribe) can't clobber state.
      this.event.subscribe(`room_${id}`, (dt: any) =>
        this.zone.run(() => { if (this.activeRoomId === id) this.onEvent(dt); }));
    }

    this.api.getRoom(id).subscribe({
      next: (r: any) => this.zone.run(() => {
        this.roomName = r.name;
        this.rights = r.rights;
        this.rightsLoaded = true;
        if (r.name) localStorage.setItem('activeRoomName', r.name);
        if (r.state) this.applyState(r.state);
      }),
      error: () => {}   // room may have been deleted; leave last-known state
    });
  }

  private onEvent(dt: any) {
    if (!dt) return;
    if (dt.type === 'state') this.applyState(dt);
    else if (dt.type === 'progress') this.setPosition(dt.progress ?? 0, dt.duration);
    else if (dt.type === 'status') {
      if (dt.status === 'paused') this.playing = false;
      else if (dt.status === 'playing') this.playing = true;
    }
  }

  private applyState(s: any) {
    this.nowPlaying = s.now_playing ?? null;
    this.playing = !!s.playing;
    this.setPosition(s.position ?? 0, this.nowPlaying?.duration ?? 0);
    this.reflect();
  }

  /** Keep the OS media session (and its silent keeper) in sync with the room, so
   *  the play/pause key toggles correctly instead of only ever pausing. */
  private reflect() {
    this.updateMediaSession();
    if (this.keeper) {
      if (this.playing) this.keeper.play().catch(() => {});
      else this.keeper.pause();
    }
  }

  private can(right: string): boolean {
    return !!this.rights && (!!this.rights.is_admin || !!this.rights[right]);
  }
  get canPlayPause(): boolean { return this.can('can_playpause'); }
  get canSkip(): boolean { return this.can('can_skip'); }
  get canVoteSkip(): boolean { return this.can('can_vote_skip'); }
  /** Can use the next button at all (skip directly, or vote to skip in a party). */
  get canNext(): boolean { return this.canSkip || (!this.canSkip && this.canVoteSkip); }

  toggle() {
    if (this.activeRoomId == null || !this.canPlayPause) return;
    const wasPlaying = this.playing;
    this.playing = !wasPlaying;   // optimistic; SSE will confirm
    this.reflect();
    (wasPlaying ? this.api.roomPause(this.activeRoomId) : this.api.roomPlay(this.activeRoomId)).subscribe();
  }
  next() {
    if (this.activeRoomId == null) return;
    if (this.canSkip) { this.api.roomNext(this.activeRoomId).subscribe(); return; }
    if (this.canVoteSkip) this.api.roomVoteSkip(this.activeRoomId).subscribe({   // party vote
      next: (r: any) => this.zone.run(() => {
        if (r && r.votes && r.threshold && r.votes < r.threshold)
          this.toastr.info(`${r.votes}/${r.threshold} — voting to skip`);
        else this.toastr.success('Skipping…');
      })
    });
  }
  prev() { if (this.activeRoomId != null && this.canSkip) this.api.roomPrev(this.activeRoomId).subscribe(); }
}
