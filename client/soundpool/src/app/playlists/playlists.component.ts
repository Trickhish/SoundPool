import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../api.service';

interface DeezerPlaylist {
  id: number;
  title: string;
  nb_tracks: number;
  picture: string;
}

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

  constructor(public api: ApiService) {}

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
}
