import { Component, OnInit, NgZone } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { ApiService } from '../api.service';

/**
 * Screen pairing: type the 4-digit code shown in the room's settings instead of
 * copying the long display URL onto a TV.
 *
 * The code is only a handshake — it's exchanged here for the room's real
 * display token, which is what /display/:code actually uses. It's also
 * remembered locally so this screen goes straight to the display next time.
 *
 * The digit boxes are four explicit inputs read straight from the DOM: an
 * *ngFor over four identical empty strings let Angular reuse/move the nodes, so
 * a digit typed in one box appeared in the next one too.
 */
@Component({
  selector: 'app-display-pair',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './display-pair.component.html',
  styleUrl: './display-pair.component.scss'
})
export class DisplayPairComponent implements OnInit {
  busy = false;
  error = '';

  constructor(private api: ApiService, private router: Router, private zone: NgZone) {}

  ngOnInit() {
    // A screen that paired before shouldn't have to do it again.
    const saved = localStorage.getItem('displayCode');
    if (saved) { this.router.navigate(['/display', saved]); return; }
    setTimeout(() => this.focus(0), 60);
  }

  private box(i: number): HTMLInputElement | null {
    return document.getElementById('d' + i) as HTMLInputElement | null;
  }
  private focus(i: number) {
    const el = this.box(i);
    el?.focus();
    el?.select();
  }
  /** Tapping a box on a TV/phone shouldn't strand you mid-code. */
  onFocus(i: number) {
    const code = this.readCode();
    if (i > code.length) this.focus(code.length);
  }

  private readCode(): string {
    let s = '';
    for (let i = 0; i < 4; i++) s += (this.box(i)?.value || '').replace(/\D/g, '');
    return s;
  }
  private setBoxes(v: string) {
    for (let i = 0; i < 4; i++) {
      const el = this.box(i);
      if (el) el.value = v[i] || '';
    }
  }
  private clear() {
    this.setBoxes('');
    this.focus(0);
  }

  onInput(i: number, ev: any) {
    const el = ev.target as HTMLInputElement;
    const digits = (el.value || '').replace(/\D/g, '');
    if (!digits) { el.value = ''; return; }
    // Keep exactly one digit in this box; spill the rest into the ones after it
    // (covers autofill and fast typing).
    el.value = digits[0];
    let next = i + 1;
    for (let k = 1; k < digits.length && next < 4; k++, next++) {
      const nb = this.box(next);
      if (nb) nb.value = digits[k];
    }
    this.error = '';
    const code = this.readCode();
    if (code.length === 4) this.submit();
    else this.focus(Math.min(next, 3));
  }

  onKey(i: number, ev: KeyboardEvent) {
    if (ev.key === 'Backspace') {
      const el = this.box(i);
      if (el && !el.value && i > 0) {
        ev.preventDefault();
        const prev = this.box(i - 1);
        if (prev) prev.value = '';
        this.focus(i - 1);
      }
      this.error = '';
    } else if (ev.key === 'ArrowLeft' && i > 0) { ev.preventDefault(); this.focus(i - 1); }
    else if (ev.key === 'ArrowRight' && i < 3) { ev.preventDefault(); this.focus(i + 1); }
    else if (ev.key === 'Enter') { if (this.readCode().length === 4) this.submit(); }
  }

  onPaste(ev: ClipboardEvent) {
    ev.preventDefault();
    const v = (ev.clipboardData?.getData('text') || '').replace(/\D/g, '').slice(0, 4);
    if (!v) return;
    this.setBoxes(v);
    this.error = '';
    if (v.length === 4) this.submit(); else this.focus(v.length);
  }

  submit() {
    const code = this.readCode();
    if (this.busy || code.length !== 4) return;
    this.busy = true;
    this.error = '';
    this.api.pairDisplay(code).subscribe({
      next: (r) => this.zone.run(() => {
        localStorage.setItem('displayCode', r.display_code);
        this.router.navigate(['/display', r.display_code]);
      }),
      error: (e) => this.zone.run(() => {
        this.busy = false;
        // Say what actually went wrong — a silently-cleared box is the worst
        // possible feedback on a screen you're standing in front of.
        if (e?.status === 0) {
          this.error = "Can't reach SoundPool. Check this screen's internet connection.";
        } else if (e?.status === 429) {
          this.error = 'Too many attempts. Wait a minute, then try again.';
        } else if (e?.status === 404) {
          this.error = 'That code is wrong or has expired. Generate a new one in the room settings.';
        } else {
          this.error = e?.error?.detail || 'Could not pair this screen. Try again.';
        }
        setTimeout(() => this.clear(), 50);
      })
    });
  }
}
