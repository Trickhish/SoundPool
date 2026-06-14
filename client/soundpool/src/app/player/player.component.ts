import { Component, OnInit, OnDestroy } from '@angular/core';
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

export interface QueueEntry { title: string; artist: string; img_url: string; }
export interface DeezerPlaylist { id: number; title: string; nb_tracks: number; picture: string; }

type QueueMode = 'none' | 'search' | 'playlists';

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
    private event: LivefbService
  ) {
    window.addEventListener('mousemove', (e) => this.onMouseMove(e));
    window.addEventListener('mouseup', () => this.onMouseUp());
    library.addIcons(faPlay, faPlayCircle);
  }

  pid: string | null = null;
  cover_url = "soundpool_sqrd.png";
  movingProgress = false;
  musicProgress = 0;
  mouseMoving = false;
  playing = false;
  player: Unit | null = null;
  currentSong: Song | null = null;
  songProgress = "";

  // Queue state
  queueMode: QueueMode = 'none';
  queueList: QueueEntry[] = [];
  queueBusy = false;

  // Search panel
  searchQuery = '';
  searchResults: any[] = [];
  searchDebounce: any = null;

  // Playlist panel
  deezerPlaylists: DeezerPlaylist[] = [];
  playlistsLoaded = false;
  addingPlaylistId: number | null = null;

  async loadContent() {
    this.cache.fetchData(`player_${this.pid!}`, () => this.api.getPlayer(this.pid!)).subscribe({
      next: (r: any) => {
        if (r.currentData != null) this.player = r.currentData;
        r.newData$.subscribe({
          next: (dt: any) => {
            this.player = dt;
            this.playing = this.player?.status == "playing";
          }
        });
      }
    });
  }

  ngOnInit() {
    this.pid = this.aroute.snapshot.paramMap.get('player_id');
    if (!this.pid) return;
    this.loadContent();

    this.event.subscribe(`pu_${this.pid}`, (dt: any) => {
      if (dt.type == "status") {
        if (!this.player) return;
        this.player.status = dt.status;
        this.player.online = (dt.status != "offline");
        this.playing = (this.player.status == "playing");
        this.player.name = dt.name;
      } else if (dt.type == "playing_song") {
        this.currentSong = { title: dt.name, duration: dt.duration, img_url: dt.img_url };
        this.musicProgress = 0;
      } else if (dt.type == "progress") {
        if (this.currentSong) {
          this.currentSong.title = dt.name;
          this.currentSong.img_url = dt.img_url;
        } else {
          this.currentSong = { title: dt.name, duration: dt.duration, img_url: dt.img_url };
        }
        this.musicProgress = parseFloat(dt.progress) / parseFloat(dt.duration) * 100;
      }
    });
  }

  ngOnDestroy() {
    window.removeEventListener('mousemove', (e) => this.onMouseMove(e));
    window.removeEventListener('mouseup', () => this.onMouseUp());
  }

  // ── Progress bar ──

  setPct(ev: MouseEvent) {
    var svg = document.querySelector("#music_svg");
    const rect = svg!.getBoundingClientRect();
    const dx = ev.pageX - rect.left - rect.width / 2;
    const dy = ev.pageY - rect.top - rect.height / 2;
    var angle = ((Math.atan2(dy, dx) / Math.PI) * 50) + 25;
    if (angle < 0) angle = 100 + angle;
    this.musicProgress = angle;
  }
  followMouse(ev: MouseEvent) { this.movingProgress = true; }
  onMouseMove(ev: MouseEvent) {
    this.mouseMoving = true;
    if (this.movingProgress) this.setPct(ev);
  }
  onMouseUp() { this.movingProgress = false; this.mouseMoving = false; }

  // ── Playback ──

  play() { this.api.play(this.player!.id).subscribe(); }
  pause() { this.api.pause(this.player!.id).subscribe(); }
  playpause() { this.playing ? this.pause() : this.play(); }
  prev() { this.api.prev(this.player!.id).subscribe(); }
  next() { this.api.next(this.player!.id).subscribe(); }

  // ── Queue controls ──

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
  }

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
    if (!this.pid || this.queueBusy) return;
    this.queueBusy = true;
    this.api.queueAdd(this.pid, {
      song_id: song.id, title: song.title, artist: song.artist, img_url: song.img_url || ''
    }).subscribe({
      next: () => {
        this.queueList.push({ title: song.title, artist: song.artist, img_url: song.img_url || '' });
        this.queueBusy = false;
        this.queueMode = 'none';
      },
      error: () => { this.queueBusy = false; }
    });
  }

  addPlaylist(pl: DeezerPlaylist) {
    if (!this.pid || this.addingPlaylistId !== null) return;
    this.addingPlaylistId = pl.id;
    this.api.queuePlaylist(this.pid, pl.id).subscribe({
      next: (r) => {
        this.queueList.push({ title: `${pl.title} (${r.total} tracks)`, artist: 'Deezer playlist', img_url: pl.picture });
        this.addingPlaylistId = null;
        this.queueMode = 'none';
      },
      error: () => { this.addingPlaylistId = null; }
    });
  }

  clearQueue() {
    if (!this.pid) return;
    this.api.queueClear(this.pid).subscribe({
      next: () => { this.queueList = []; }
    });
  }
}
