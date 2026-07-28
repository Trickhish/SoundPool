import { Component } from '@angular/core';
import { TranslateModule } from '@ngx-translate/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ToastrService } from 'ngx-toastr';

import { ApiService } from '../api.service';
import { PlaybackService } from '../playback.service';
import { Song } from '../song';

@Component({
  selector: 'app-home',
  imports: [TranslateModule, CommonModule, FormsModule],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss'
})
export class HomeComponent {
  constructor(
    private api: ApiService,
    public playback: PlaybackService,
    private toastr: ToastrService,
    private router: Router
  ) {}

  squery = '';
  results: Song[] = [];
  searching = false;
  searched = false;
  private debounce: any = null;

  onSearchInput() {
    clearTimeout(this.debounce);
    const q = this.squery.trim();
    if (!q) { this.results = []; this.searched = false; return; }
    this.debounce = setTimeout(() => this.runSearch(q), 300);
  }

  private runSearch(q: string) {
    this.searching = true;
    this.api.search(q).subscribe({
      next: (r: Song[]) => { this.results = r || []; this.searching = false; this.searched = true; },
      error: () => { this.searching = false; this.searched = true; this.toastr.error('Search failed'); }
    });
  }

  addSong(s: Song) {
    if (this.playback.activeRoomId == null) {
      this.toastr.info('Open a room first to add songs');
      this.router.navigate(['/rooms']);
      return;
    }
    const body = { song_id: s.id || '', title: s.title || '', artist: s.artist || '', img_url: s.img_url || '' };
    this.api.roomQueueAdd(this.playback.activeRoomId, body).subscribe({
      next: () => this.toastr.success(s.title || '', `Added to ${this.playback.roomName || 'room'}`),
      error: () => this.toastr.error('Could not add song')
    });
  }
}
