import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ToastrService } from 'ngx-toastr';
import { ApiService } from '../api.service';
import { PlaybackService } from '../playback.service';

interface DeezerPlaylist {
  id: number;
  title: string;
  nb_tracks: number;
  picture: string;
}

interface PlaylistTrack { id: string; title: string; artist: string; img_url: string; }

@Component({
  selector: 'app-playlists',
  imports: [CommonModule],
  templateUrl: './playlists.component.html',
  styleUrl: './playlists.component.scss'
})
export class PlaylistsComponent implements OnInit {
  deezerPlaylists: DeezerPlaylist[] = [];
  deezerLoading = true;
  deezerConnected = true;

  opened: DeezerPlaylist | null = null;
  tracks: PlaylistTrack[] = [];
  tracksLoading = false;
  addingAll = false;

  constructor(
    public api: ApiService,
    public playback: PlaybackService,
    private toastr: ToastrService,
    private router: Router
  ) {}

  ngOnInit() {
    this.api.deezerPlaylists().subscribe({
      next: (r) => {
        this.deezerPlaylists = r.playlists;
        this.deezerLoading = false;
      },
      error: (e) => {
        this.deezerLoading = false;
        if (e.status === 403) this.deezerConnected = false;
      }
    });
  }

  open(pl: DeezerPlaylist) {
    this.opened = pl;
    this.tracks = [];
    this.tracksLoading = true;
    this.api.deezerPlaylistTracks(pl.id).subscribe({
      next: (r) => { this.tracks = r.tracks || []; this.tracksLoading = false; },
      error: () => { this.tracksLoading = false; this.toastr.error('Could not load playlist'); }
    });
  }

  back() { this.opened = null; this.tracks = []; }

  private ensureRoom(): number | null {
    if (this.playback.activeRoomId == null) {
      this.toastr.info('Open a room first to add songs');
      this.router.navigate(['/rooms']);
      return null;
    }
    return this.playback.activeRoomId;
  }

  addTrack(t: PlaylistTrack) {
    const room = this.ensureRoom();
    if (room == null) return;
    this.api.roomQueueAdd(room, { song_id: t.id, title: t.title, artist: t.artist, img_url: t.img_url || '' }).subscribe({
      next: () => this.toastr.success(t.title, `Added to ${this.playback.roomName || 'room'}`),
      error: () => this.toastr.error('Could not add song')
    });
  }

  addAll() {
    const room = this.ensureRoom();
    if (room == null || !this.opened || this.addingAll) return;
    this.addingAll = true;
    this.api.roomQueuePlaylist(room, this.opened.id).subscribe({
      next: () => { this.addingAll = false; this.toastr.success(this.opened!.title, `Added to ${this.playback.roomName || 'room'}`); },
      error: () => { this.addingAll = false; this.toastr.error('Could not add playlist'); }
    });
  }
}
