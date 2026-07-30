import { Component, OnInit, NgZone } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../api.service';

/**
 * Screen pairing: type the 4-digit code shown in the room's settings instead of
 * copying the long display URL onto a TV.
 *
 * The code is only a handshake — it's exchanged here for the room's real
 * display token, which is what /display/:code actually uses. It's also
 * remembered locally so this screen goes straight to the display next time.
 */
@Component({
  selector: 'app-display-pair',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './display-pair.component.html',
  styleUrl: './display-pair.component.scss'
})
export class DisplayPairComponent implements OnInit {
  digits: string[] = ['', '', '', ''];
  busy = false;
  error = '';

  constructor(private api: ApiService, private router: Router, private zone: NgZone) {}

  ngOnInit() {
    // A screen that paired before shouldn't have to do it again.
    const saved = localStorage.getItem('displayCode');
    if (saved) this.router.navigate(['/display', saved]);
    setTimeout(() => this.focus(0), 50);
  }

  private focus(i: number) {
    const el = document.getElementById('d' + i) as HTMLInputElement | null;
    el?.focus();
    el?.select();
  }

  onInput(i: number, ev: any) {
    const v = (ev.target.value || '').replace(/\D/g, '');
    if (v.length > 1) { this.onPaste(v); return; }   // e.g. autofill or paste
    this.digits[i] = v;
    this.error = '';
    if (v && i < 3) this.focus(i + 1);
    if (this.code.length === 4) this.submit();
  }

  onKey(i: number, ev: KeyboardEvent) {
    if (ev.key === 'Backspace' && !this.digits[i] && i > 0) this.focus(i - 1);
    if (ev.key === 'Enter' && this.code.length === 4) this.submit();
  }

  onPaste(text: string) {
    const v = (text || '').replace(/\D/g, '').slice(0, 4);
    for (let i = 0; i < 4; i++) this.digits[i] = v[i] || '';
    if (v.length === 4) this.submit(); else this.focus(v.length);
  }

  get code(): string { return this.digits.join('').replace(/\D/g, ''); }

  submit() {
    if (this.busy || this.code.length !== 4) return;
    this.busy = true;
    this.error = '';
    this.api.pairDisplay(this.code).subscribe({
      next: (r) => this.zone.run(() => {
        localStorage.setItem('displayCode', r.display_code);
        this.router.navigate(['/display', r.display_code]);
      }),
      error: (e) => this.zone.run(() => {
        this.busy = false;
        this.error = e?.error?.detail || 'Could not pair this screen.';
        this.digits = ['', '', '', ''];
        this.focus(0);
      })
    });
  }
}
