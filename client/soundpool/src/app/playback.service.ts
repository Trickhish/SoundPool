import { Injectable, NgZone } from '@angular/core';
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

  constructor(private api: ApiService, private event: LivefbService, private zone: NgZone) {
    const saved = localStorage.getItem('activeRoom');
    if (saved) this.setActiveRoom(+saved, localStorage.getItem('activeRoomName') || '');
  }

  /** Point the controller at a room and start mirroring its state. */
  setActiveRoom(id: number, name = '') {
    const same = this.activeRoomId === id;
    this.activeRoomId = id;
    if (name) this.roomName = name;
    localStorage.setItem('activeRoom', String(id));
    if (name) localStorage.setItem('activeRoomName', name);

    if (!same) {
      // SSE fires outside Angular's zone; re-enter it. Guard by id so a stale
      // room's events (we never explicitly unsubscribe) can't clobber state.
      this.event.subscribe(`room_${id}`, (dt: any) =>
        this.zone.run(() => { if (this.activeRoomId === id) this.onEvent(dt); }));
    }

    this.api.getRoom(id).subscribe({
      next: (r: any) => this.zone.run(() => {
        this.roomName = r.name;
        this.rights = r.rights;
        if (r.name) localStorage.setItem('activeRoomName', r.name);
        if (r.state) this.applyState(r.state);
      }),
      error: () => {}   // room may have been deleted; leave last-known state
    });
  }

  private onEvent(dt: any) {
    if (!dt) return;
    if (dt.type === 'state') this.applyState(dt);
    else if (dt.type === 'status') {
      if (dt.status === 'paused') this.playing = false;
      else if (dt.status === 'playing') this.playing = true;
    }
  }

  private applyState(s: any) {
    this.nowPlaying = s.now_playing ?? null;
    this.playing = !!s.playing;
  }

  private can(right: string): boolean {
    return !!this.rights && (!!this.rights.is_admin || !!this.rights[right]);
  }
  get canPlayPause(): boolean { return this.can('can_playpause'); }
  get canSkip(): boolean { return this.can('can_skip'); }

  toggle() {
    if (this.activeRoomId == null || !this.canPlayPause) return;
    const wasPlaying = this.playing;
    this.playing = !wasPlaying;   // optimistic; SSE will confirm
    (wasPlaying ? this.api.roomPause(this.activeRoomId) : this.api.roomPlay(this.activeRoomId)).subscribe();
  }
  next() { if (this.activeRoomId != null && this.canSkip) this.api.roomNext(this.activeRoomId).subscribe(); }
  prev() { if (this.activeRoomId != null && this.canSkip) this.api.roomPrev(this.activeRoomId).subscribe(); }
}
