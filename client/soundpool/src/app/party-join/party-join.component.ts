import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../api.service';

@Component({
  selector: 'app-party-join',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './party-join.component.html',
  styleUrl: './party-join.component.scss'
})
export class PartyJoinComponent {
  code = '';
  roomName = '';
  memberCount = 0;
  username = '';
  loading = true;
  joining = false;
  error = '';

  constructor(private route: ActivatedRoute, private api: ApiService) {
    this.code = this.route.snapshot.paramMap.get('code') || '';
    if (!this.code) { this.error = 'Invalid link'; this.loading = false; return; }
    this.api.getParty(this.code).subscribe({
      next: (r) => { this.roomName = r.name; this.memberCount = r.member_count; this.loading = false; },
      error: () => { this.error = 'This party link is invalid or has ended.'; this.loading = false; }
    });
  }

  join() {
    const name = this.username.trim();
    if (!name || this.joining) return;
    this.joining = true;
    this.api.joinParty(this.code, name).subscribe({
      next: (r) => {
        // Preserve a real account's token so the guest can exit back to it later.
        const existing = localStorage.getItem('token');
        if (existing && !localStorage.getItem('realToken')) localStorage.setItem('realToken', existing);
        localStorage.setItem('token', r.token);
        // Full reload so the app bootstraps authenticated (validates token, opens SSE).
        window.location.href = `/room/${r.room_id}`;
      },
      error: () => { this.joining = false; this.error = 'Could not join — the party may have ended.'; }
    });
  }
}
