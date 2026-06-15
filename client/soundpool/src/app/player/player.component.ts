import { Component, OnInit, OnDestroy, NgZone, ChangeDetectorRef } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { NgCircleProgressModule, CircleProgressOptions  } from 'ng-circle-progress';

import { FontAwesomeModule, FaIconLibrary } from '@fortawesome/angular-fontawesome';
import {  } from '@fortawesome/free-regular-svg-icons';
import { faPlay, faPlayCircle } from '@fortawesome/free-solid-svg-icons';
import { CachingService } from '../caching.service';
import { ApiService } from '../api.service';
import { Unit } from '../unit';
import { LivefbService } from '../livefb.service';
import { Song } from '../song';
import { TranslateService,TranslateModule } from '@ngx-translate/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ToastrService } from 'ngx-toastr';

export interface NowPlaying { id: string; title: string; artist: string; album: string; cover: string; duration: number; }
export interface QueueItem { key: number; id: string; title: string; artist: string; cover: string; duration: number; ready?: boolean; failed?: boolean; }
export interface DeezerPlaylist { id: number; title: string; nb_tracks: number; picture: string; }

export interface PlayerState {
  now_playing: NowPlaying | null;
  position: number;
  playing: boolean;
  current_index: number;
  msid: number;
  volume: number;
  shuffle: boolean;
  repeat: 'off' | 'all' | 'one';
  queue: QueueItem[];
}

type QueueMode = 'none' | 'search' | 'playlists';

const FALLBACK_COVER = 'soundpool_sqrd.png';

@Component({
  selector: 'app-player',
  imports: [NgCircleProgressModule, FontAwesomeModule, TranslateModule, CommonModule, FormsModule],
  templateUrl: './player.component.html',
  styleUrl: './player.component.scss',
  providers: [
    {
      provide: CircleProgressOptions,
      useValue: {
        radius: 50, outerStrokeWidth: 10, innerStrokeWidth: 5,
        outerStrokeColor: "#4CAF50", innerStrokeColor: "#ddd",
        animation: true, animationDuration: 300,
        showTitle: false, showUnits: false, showSubtitle: false
      }
    }
  ]
})
export class PlayerComponent implements OnInit, OnDestroy {
  constructor(
    private aroute: ActivatedRoute,
    private library: FaIconLibrary,
    private cache: CachingService,
    private api: ApiService,
    private event: LivefbService,
    private zone: NgZone,
    private cdr: ChangeDetectorRef,
    private toastr: ToastrService
  ) {
    this.moveHandler = (e: any) => this.onPointerMove(e);
    this.upHandler = () => this.onPointerUp();
    window.addEventListener('mousemove', this.moveHandler);
    window.addEventListener('mouseup', this.upHandler);
    window.addEventListener('touchmove', this.moveHandler, { passive: false });
    window.addEventListener('touchend', this.upHandler);
    library.addIcons(faPlay, faPlayCircle);
  }

  pid: string | null = null;
  player: Unit | null = null;
  isRoom = false;                 // bound to a room (radio) vs a single unit
  rights: any = null;             // room rights for the current user (room mode)
  myUnits: Unit[] = [];           // the user's units (output choices, room mode)
  roomOutputs: string[] = [];     // unit ids currently attached to the room
  voteCount = 0;
  voteThreshold = 0;
  voted = false;                  // did I vote to skip the current track (local)
  manageOpen = false;             // admin members/rights panel
  members: any[] = [];

  // Authoritative player state (mirrors the unit snapshot)
  state: PlayerState = this.emptyState();

  // Progress ring / scrubbing
  musicProgress = 0;            // 0..100, drives the ring
  positionMs = 0;               // smoothed current position for display
  private lastReportedPos = 0;  // last position from a progress/state event
  private lastReportedAt = 0;   // timestamp of that report
  mouseMoving = false;
  movingProgress = false;
  private seekSuppressUntil = 0; // ignore incoming progress right after a seek
  private ticker: any = null;
  private moveHandler: (e: any) => void;
  private upHandler: () => void;

  // Library overlay
  libraryOpen = false;
  libraryTab: 'songs' | 'playlists' | 'favorites' | 'history' = 'songs';
  favorites: any[] = [];              // Deezer liked tracks (Songs tab)
  favoritesLoaded = false;

  // SoundPool favorites + history
  favoriteIds = new Set<string>();    // song ids the user has favorited in-app
  favoritesList: any[] = [];          // SoundPool favorites (Favorites tab)
  historyList: any[] = [];
  historyLoaded = false;

  // Queue panel (hidden by default, toggled like Deezer)
  queueOpen = false;

  // Queue browse
  queueMode: QueueMode = 'none';
  queueBusy = false;
  searchQuery = '';
  searchResults: any[] = [];
  searchDebounce: any = null;
  deezerPlaylists: DeezerPlaylist[] = [];
  playlistsLoaded = false;
  addingPlaylistId: number | null = null;
  // Drill-in: viewing the tracks of a single playlist
  openedPlaylist: DeezerPlaylist | null = null;
  playlistTracks: any[] = [];
  playlistTracksLoading = false;

  emptyState(): PlayerState {
    return { now_playing: null, position: 0, playing: false, current_index: -1,
             msid: 0, volume: 1, shuffle: false, repeat: 'off', queue: [] };
  }

  // ── Derived view helpers ──
  get currentSong(): Song | null {
    const np = this.state.now_playing;
    if (!np) return null;
    return { id: np.id, title: np.title, artist: np.artist, album: np.album,
             img_url: np.cover || FALLBACK_COVER, duration: np.duration };
  }
  get playing(): boolean { return this.state.playing; }
  get cover(): string { return this.state.now_playing?.cover || FALLBACK_COVER; }
  get durationMs(): number { return this.state.now_playing?.duration || 0; }

  /** Thumb position on the ring (% of the disc box), top = 0%, clockwise. */
  get thumbX(): number { const t = (this.musicProgress / 100) * 2 * Math.PI; return 50 + 50 * Math.sin(t); }
  get thumbY(): number { const t = (this.musicProgress / 100) * 2 * Math.PI; return 50 - 50 * Math.cos(t); }

  /** Already-played songs (everything before the current one). */
  get prevSongs(): QueueItem[] {
    const end = this.state.current_index >= 0 ? this.state.current_index : this.state.msid;
    return this.state.queue.slice(0, end);
  }
  /** The currently playing/loaded song, if any. */
  get nowItem(): QueueItem | null {
    return this.state.current_index >= 0 ? (this.state.queue[this.state.current_index] || null) : null;
  }
  /** Upcoming songs. `msid` is the unit's cursor = index of the next song to
   *  play, so this matches the unit exactly. */
  get upNext(): QueueItem[] {
    const start = this.state.current_index >= 0 ? this.state.current_index + 1 : this.state.msid;
    return this.state.queue.slice(start);
  }

  get songProgress(): string {
    if (!this.state.now_playing) return '';
    return `${this.fmt(this.positionMs)} / ${this.fmt(this.durationMs)}`;
  }

  fmt(ms: number): string {
    const s = Math.max(0, Math.floor((ms || 0) / 1000));
    const m = Math.floor(s / 60);
    return `${m}:${(s % 60).toString().padStart(2, '0')}`;
  }

  // ── Lifecycle ──
  ngOnInit() {
    this.pid = this.aroute.snapshot.paramMap.get('player_id');
    if (!this.pid) return;
    this.isRoom = !!this.aroute.snapshot.data['room'];
    this.loadContent();

    // SSE callbacks come from the `eventsource` package's custom fetch, which
    // runs OUTSIDE Angular's zone — so mutations here would not trigger change
    // detection. Re-enter the zone AND force a detection pass so live events
    // (queue updates, now-playing, status) always render immediately.
    const channel = (this.isRoom ? 'room_' : 'pu_') + this.pid;
    this.event.subscribe(channel, (dt: any) => this.zone.run(() => {
      this.onEvent(dt);
      try { this.cdr.detectChanges(); } catch {}
    }));

    this.loadFavoriteIds();
    if (this.isRoom) {
      this.api.getUnits().subscribe({ next: (u) => { this.myUnits = u || []; } });
    }
    this.ticker = setInterval(() => this.tick(), 250);
  }

  ngOnDestroy() {
    window.removeEventListener('mousemove', this.moveHandler);
    window.removeEventListener('mouseup', this.upHandler);
    window.removeEventListener('touchmove', this.moveHandler);
    window.removeEventListener('touchend', this.upHandler);
    if (this.ticker) clearInterval(this.ticker);
  }

  loadContent() {
    if (this.isRoom) {
      this.api.getRoom(+this.pid!).subscribe({ next: (r: any) => this.applyRoom(r) });
      return;
    }
    this.cache.fetchData(`player_${this.pid!}`, () => this.api.getPlayer(this.pid!)).subscribe({
      next: (r: any) => {
        if (r.currentData != null) this.applyPlayer(r.currentData);
        r.newData$.subscribe({ next: (dt: any) => this.applyPlayer(dt) });
      }
    });
  }

  private applyPlayer(p: any) {
    if (!p) return;
    this.player = p;
    if (p.state) this.applyState(p.state);
  }

  private applyRoom(r: any) {
    if (!r) return;
    this.rights = r.rights;
    this.player = { id: String(r.id), name: r.name, online: true } as any;
    if (r.state) this.applyState(r.state);
  }

  // ── Live events ──
  private onEvent(dt: any) {
    if (!dt) return;
    switch (dt.type) {
      case 'state':
        this.applyState(dt);
        break;
      case 'progress':
        this.onProgress(dt);
        break;
      case 'status':
        if (this.player) {
          this.player.status = dt.status;
          this.player.online = (dt.status != 'offline');
          if (dt.name) this.player.name = dt.name;
        }
        if (dt.status === 'paused') this.state.playing = false;
        if (dt.status === 'playing') this.state.playing = true;
        break;
    }
  }

  private applyState(s: any) {
    this.state = {
      now_playing: s.now_playing ?? null,
      position: s.position ?? 0,
      playing: !!s.playing,
      current_index: s.current_index ?? -1,
      msid: s.msid ?? 0,
      volume: s.volume ?? 1,
      shuffle: !!s.shuffle,
      repeat: s.repeat ?? 'off',
      queue: s.queue ?? [],
    };
    if (s.outputs !== undefined) this.roomOutputs = s.outputs;
    if (s.vote_count !== undefined) {
      if (s.vote_count === 0) this.voted = false; // reset on new track / cleared votes
      this.voteCount = s.vote_count;
      this.voteThreshold = s.vote_threshold ?? 0;
    }
    if (!this.isScrubbing()) {
      this.lastReportedPos = this.state.position;
      this.lastReportedAt = Date.now();
      this.refreshProgress();
    }
  }

  private onProgress(dt: any) {
    if (this.isScrubbing()) return;
    const dur = parseFloat(dt.duration);
    if (this.state.now_playing) this.state.now_playing.duration = dur;
    this.lastReportedPos = parseFloat(dt.progress);
    this.lastReportedAt = Date.now();
    this.refreshProgress();
  }

  private isScrubbing(): boolean {
    return this.movingProgress || Date.now() < this.seekSuppressUntil;
  }

  /** Smoothly advance the position between 1s server ticks. */
  private tick() {
    // Only freeze while actively dragging; after a click/seek we still advance
    // from the (clicked) baseline — incoming stale ticks are gated separately.
    if (this.movingProgress || !this.state.playing || !this.state.now_playing) return;
    const est = this.lastReportedPos + (Date.now() - this.lastReportedAt);
    this.positionMs = Math.min(est, this.durationMs);
    this.refreshProgress();
  }

  private refreshProgress() {
    if (!this.isScrubbing()) this.positionMs = this.lastReportedPos + (Date.now() - this.lastReportedAt);
    this.musicProgress = this.durationMs > 0
      ? Math.min(100, (this.positionMs / this.durationMs) * 100)
      : 0;
  }

  // ── Progress bar / scrubbing (mouse + touch) ──
  private eventXY(ev: MouseEvent | TouchEvent): { x: number, y: number } {
    const t = (ev as TouchEvent).touches?.[0] || (ev as TouchEvent).changedTouches?.[0];
    if (t) return { x: t.clientX, y: t.clientY };
    return { x: (ev as MouseEvent).clientX, y: (ev as MouseEvent).clientY };
  }
  private pctFromXY(x: number, y: number): number {
    const svg = document.querySelector('#music_svg');
    if (!svg) return this.musicProgress;
    const rect = svg.getBoundingClientRect();
    const dx = x - rect.left - rect.width / 2;
    const dy = y - rect.top - rect.height / 2;
    let angle = ((Math.atan2(dy, dx) / Math.PI) * 50) + 25;
    if (angle < 0) angle = 100 + angle;
    return angle;
  }
  private applyScrub(pct: number) {
    this.musicProgress = pct;
    this.positionMs = (pct / 100) * this.durationMs;
  }

  startDrag(ev: MouseEvent | TouchEvent) {
    if (!this.can('can_seek')) return;
    if (ev.type === 'touchstart') ev.preventDefault(); // avoid scroll + synthetic click
    this.movingProgress = true;
    const { x, y } = this.eventXY(ev);
    this.applyScrub(this.pctFromXY(x, y));
  }

  onPointerMove(ev: MouseEvent | TouchEvent) {
    if (!this.movingProgress) return;
    if (ev.type === 'touchmove') ev.preventDefault(); // stop the page scrolling while scrubbing
    this.mouseMoving = true;
    const { x, y } = this.eventXY(ev);
    this.applyScrub(this.pctFromXY(x, y));
  }

  onPointerUp() {
    if (this.movingProgress) this.commitSeek(this.musicProgress);
    this.movingProgress = false;
    this.mouseMoving = false;
  }

  private commitSeek(pct: number) {
    if (!this.pid || !this.state.now_playing) return;
    this.state.playing = true; // seeking resumes playback
    this.seekSuppressUntil = Date.now() + 1500;
    this.lastReportedPos = (pct / 100) * this.durationMs;
    this.lastReportedAt = Date.now();
    (this.isRoom ? this.api.roomSeek(this.pid, pct) : this.api.seek(this.pid, pct)).subscribe();
  }

  // ── Playback ──
  play() { this.state.playing = true; (this.isRoom ? this.api.roomPlay(this.pid!) : this.api.play(this.player!.id)).subscribe(); }
  pause() { this.state.playing = false; (this.isRoom ? this.api.roomPause(this.pid!) : this.api.pause(this.player!.id)).subscribe(); }
  playpause() { this.playing ? this.pause() : this.play(); }
  prev() { (this.isRoom ? this.api.roomPrev(this.pid!) : this.api.prev(this.player!.id)).subscribe(); }
  next() { (this.isRoom ? this.api.roomNext(this.pid!) : this.api.next(this.player!.id)).subscribe(); }

  // ── Volume / shuffle / repeat ──
  private volumeDebounce: any = null;
  onVolumeInput(v: number) {
    this.state.volume = v;
    clearTimeout(this.volumeDebounce);
    this.volumeDebounce = setTimeout(() => {
      if (this.pid && !this.isRoom) this.api.setVolume(this.pid, v).subscribe();
    }, 120);
  }
  toggleShuffle() {
    const on = !this.state.shuffle;
    this.state.shuffle = on;
    if (this.pid) (this.isRoom ? this.api.roomShuffle(this.pid, on) : this.api.setShuffle(this.pid, on)).subscribe();
  }
  cycleRepeat() {
    const order: ('off' | 'all' | 'one')[] = ['off', 'all', 'one'];
    const next = order[(order.indexOf(this.state.repeat) + 1) % 3];
    this.state.repeat = next;
    if (this.pid) (this.isRoom ? this.api.roomRepeat(this.pid, next) : this.api.setRepeat(this.pid, next)).subscribe();
  }

  // ── Queue management ──
  dragKey: number | null = null;
  dragOverKey: number | null = null;

  jumpTo(item: QueueItem) {
    if (!this.pid || item.failed || !this.can('can_skip')) return;
    (this.isRoom ? this.api.roomQueueJump(this.pid, item.key) : this.api.queueJump(this.pid, item.key)).subscribe();
  }
  removeItem(item: QueueItem, ev: Event) {
    ev.stopPropagation();
    if (!this.pid) return;
    (this.isRoom ? this.api.roomQueueRemove(this.pid, item.key) : this.api.queueRemove(this.pid, item.key)).subscribe();
  }
  onDragStart(item: QueueItem) { if (!this.can('can_reorder')) return; this.dragKey = item.key; }
  onDragOver(item: QueueItem, ev: DragEvent) { ev.preventDefault(); this.dragOverKey = item.key; }
  onDrop(item: QueueItem, ev: DragEvent) {
    ev.preventDefault();
    if (this.pid && this.dragKey !== null && this.dragKey !== item.key) {
      (this.isRoom ? this.api.roomQueueMove(this.pid, this.dragKey, item.key)
                   : this.api.queueMove(this.pid, this.dragKey, item.key)).subscribe();
    }
    this.dragKey = null;
    this.dragOverKey = null;
  }
  onDragEnd() { this.dragKey = null; this.dragOverKey = null; }

  // ── Rights gating ──
  can(right: string): boolean {
    if (!this.isRoom) return true;            // unit-direct player: owner has full control
    if (!this.rights) return false;
    return !!this.rights.is_admin || !!this.rights[right];
  }
  get isAdmin(): boolean { return this.isRoom && !!this.rights?.is_admin; }
  get showVoteSkip(): boolean { return this.isRoom && !this.can('can_skip') && this.can('can_vote_skip'); }

  voteSkip() {
    if (!this.pid || this.voted) return;
    this.voted = true;
    this.api.roomVoteSkip(this.pid).subscribe({ error: () => { this.voted = false; } });
  }

  // ── Members / rights management (admin) ──
  openManage() {
    if (!this.pid) return;
    this.manageOpen = true;
    this.api.roomMembers(+this.pid).subscribe({ next: (m) => this.members = m });
  }
  closeManage() { this.manageOpen = false; }
  toggleMemberRight(m: any, field: string) {
    if (!this.pid) return;
    const val = !m[field];
    m[field] = val;
    this.api.setRoomRights(+this.pid, { user_id: m.user_id, [field]: val }).subscribe({
      error: () => { m[field] = !val; this.toastr.error('Could not update rights'); }
    });
  }

  // ── Output (room mode) ──
  isOutput(unitId: string): boolean { return this.roomOutputs.includes(unitId); }
  toggleOutput(unit: Unit) {
    if (!this.pid) return;
    const id = (unit as any).id;
    if (this.isOutput(id)) {
      this.roomOutputs = this.roomOutputs.filter(x => x !== id);
      this.api.roomClearOutput(this.pid, id).subscribe();
    } else {
      this.roomOutputs = [...this.roomOutputs, id];
      this.api.roomSelectOutput(this.pid, id).subscribe({
        error: () => { this.roomOutputs = this.roomOutputs.filter(x => x !== id); this.toastr.error('Could not set output'); }
      });
    }
  }

  // ── Queue panel ──
  toggleQueue() { this.queueOpen = !this.queueOpen; }
  closeQueue() { this.queueOpen = false; }

  // ── Library overlay ──
  openLibrary(tab: 'songs' | 'playlists' = 'songs') {
    this.libraryOpen = true;
    this.setTab(tab);
  }
  closeLibrary() {
    this.libraryOpen = false;
    this.openedPlaylist = null;
    this.searchQuery = '';
    this.searchResults = [];
  }
  setTab(tab: 'songs' | 'playlists' | 'favorites' | 'history') {
    this.libraryTab = tab;
    this.openedPlaylist = null;
    if (tab === 'songs' && !this.favoritesLoaded) this.loadFavorites();
    if (tab === 'playlists' && !this.playlistsLoaded) {
      this.api.deezerPlaylists().subscribe({
        next: (r) => { this.deezerPlaylists = r.playlists; this.playlistsLoaded = true; },
        error: () => { this.playlistsLoaded = true; }
      });
    }
    if (tab === 'favorites') this.loadFavoriteIds();
    if (tab === 'history' && !this.historyLoaded) this.loadHistory();
  }
  loadFavorites() {
    this.api.deezerFavorites().subscribe({
      next: (r) => { this.favorites = r.tracks; this.favoritesLoaded = true; },
      error: () => { this.favoritesLoaded = true; }
    });
  }
  loadHistory() {
    this.api.getHistory().subscribe({
      next: (r) => { this.historyList = r; this.historyLoaded = true; },
      error: () => { this.historyLoaded = true; }
    });
  }
  loadFavoriteIds() {
    this.api.getFavorites().subscribe({
      next: (r) => { this.favoritesList = r; this.favoriteIds = new Set(r.map((x: any) => x.id)); },
      error: () => {}
    });
  }

  // ── SoundPool favorites ──
  isFavorite(): boolean {
    const id = this.currentSong?.id;
    return !!id && this.favoriteIds.has(id);
  }
  toggleFavorite() {
    const s = this.currentSong;
    if (!s || !s.id) return;
    if (this.favoriteIds.has(s.id)) {
      this.favoriteIds.delete(s.id);
      this.api.removeFavorite(s.id).subscribe();
    } else {
      this.favoriteIds.add(s.id);
      this.api.addFavorite({ song_id: s.id, title: s.title || '', artist: s.artist || '', img_url: s.img_url || '' }).subscribe(() => {
        this.toastr.success(s.title || '', 'Added to favorites');
      });
    }
  }

  // ── Queue browse ──
  toggleMode(mode: QueueMode) {
    this.queueMode = this.queueMode === mode ? 'none' : mode;
    if (this.queueMode === 'playlists' && !this.playlistsLoaded) {
      this.api.deezerPlaylists().subscribe({
        next: (r) => { this.deezerPlaylists = r.playlists; this.playlistsLoaded = true; },
        error: () => { this.playlistsLoaded = true; }
      });
    }
    if (this.queueMode === 'search') {
      this.searchQuery = '';
      this.searchResults = [];
    }
    if (this.queueMode !== 'playlists') {
      this.openedPlaylist = null;
      this.playlistTracks = [];
    }
  }

  openPlaylist(pl: DeezerPlaylist) {
    this.openedPlaylist = pl;
    this.playlistTracks = [];
    this.playlistTracksLoading = true;
    this.api.deezerPlaylistTracks(pl.id).subscribe({
      next: (r) => { this.playlistTracks = r.tracks; this.playlistTracksLoading = false; },
      error: () => { this.playlistTracksLoading = false; }
    });
  }
  backToPlaylists() { this.openedPlaylist = null; this.playlistTracks = []; }

  onSearchInput() {
    clearTimeout(this.searchDebounce);
    if (!this.searchQuery.trim()) { this.searchResults = []; return; }
    this.searchDebounce = setTimeout(() => {
      this.api.search(this.searchQuery).subscribe({
        next: (r: any) => { this.searchResults = r; },
        error: () => {}
      });
    }, 350);
  }

  addSong(song: any) {
    if (!this.pid || !this.can('can_add')) return;
    const body = { song_id: song.id, title: song.title, artist: song.artist, img_url: song.img_url || '' };
    (this.isRoom ? this.api.roomQueueAdd(this.pid, body) : this.api.queueAdd(this.pid, body)).subscribe({
      next: () => this.toastr.success(song.title, 'Added to queue'),
      error: () => this.toastr.error('Could not add song')
    });
  }

  addPlaylist(pl: DeezerPlaylist) {
    if (!this.pid || this.addingPlaylistId !== null) return;
    this.addingPlaylistId = pl.id;
    (this.isRoom ? this.api.roomQueuePlaylist(this.pid, pl.id) : this.api.queuePlaylist(this.pid, pl.id)).subscribe({
      next: () => { this.addingPlaylistId = null; this.toastr.success(pl.title, 'Added playlist'); this.closeLibrary(); },
      error: () => { this.addingPlaylistId = null; this.toastr.error('Could not add playlist'); }
    });
  }

  clearQueue() {
    if (!this.pid) return;
    (this.isRoom ? this.api.roomQueueClear(this.pid) : this.api.queueClear(this.pid)).subscribe();
  }
}
