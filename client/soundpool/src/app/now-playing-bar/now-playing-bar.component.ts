import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { PlaybackService } from '../playback.service';

@Component({
  selector: 'app-now-playing-bar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './now-playing-bar.component.html',
  styleUrl: './now-playing-bar.component.scss'
})
export class NowPlayingBarComponent {
  constructor(public playback: PlaybackService, private router: Router) {}

  openRoom() {
    if (this.playback.activeRoomId != null)
      this.router.navigate(['/room', this.playback.activeRoomId]);
  }
}
