import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FontAwesomeModule, FaIconLibrary } from '@fortawesome/angular-fontawesome';
import { faPlay, faPause, faBackwardStep, faForwardStep } from '@fortawesome/free-solid-svg-icons';
import { PlaybackService } from '../playback.service';

@Component({
  selector: 'app-now-playing-bar',
  standalone: true,
  imports: [CommonModule, FontAwesomeModule],
  templateUrl: './now-playing-bar.component.html',
  styleUrl: './now-playing-bar.component.scss'
})
export class NowPlayingBarComponent {
  constructor(public playback: PlaybackService, private router: Router, library: FaIconLibrary) {
    library.addIcons(faPlay, faPause, faBackwardStep, faForwardStep);
  }

  openRoom() {
    if (this.playback.activeRoomId != null)
      this.router.navigate(['/room', this.playback.activeRoomId]);
  }
}
