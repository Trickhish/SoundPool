import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../api.service';

/**
 * Approve a TV (or other keyboard-less device) that's showing a sign-in code.
 * The device never sees the password — it polls until this hands it a token.
 */
@Component({
  selector: 'app-link',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './link.component.html',
  styleUrl: './link.component.scss',
})
export class LinkComponent implements OnInit {
  code = '';
  busy = false;
  done = false;
  error: string | null = null;
  /** Arrived by scanning the TV's QR rather than typing the code. */
  scanned = false;

  constructor(private api: ApiService, private aroute: ActivatedRoute) {}

  ngOnInit() {
    // The TV's QR encodes /link?code=XXXXXX so there's nothing to type.
    // Still an explicit confirm: scanning shouldn't silently hand an account
    // to whatever screen produced the code.
    const c = this.aroute.snapshot.queryParamMap.get('code');
    if (c) {
      this.code = c;
      this.scanned = true;
    }
  }

  get clean(): string {
    return (this.code || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  }

  submit() {
    if (this.clean.length !== 6 || this.busy) return;
    this.busy = true;
    this.error = null;
    this.api.approveDevice(this.clean).subscribe({
      next: () => { this.busy = false; this.done = true; },
      error: (e) => { this.busy = false; this.error = e?.error?.detail || 'Could not link that device.'; },
    });
  }

  again() { this.code = ''; this.done = false; this.error = null; }
}
