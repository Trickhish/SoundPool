import { Component, OnInit, NgZone, ChangeDetectorRef } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../api.service';
import { LivefbService } from '../livefb.service';
import { ToastrService } from 'ngx-toastr';

@Component({
  selector: 'app-unit-settings',
  imports: [CommonModule, FormsModule],
  templateUrl: './unit-settings.component.html',
  styleUrl: './unit-settings.component.scss'
})
export class UnitSettingsComponent implements OnInit {
  constructor(private route: ActivatedRoute, private api: ApiService,
              private event: LivefbService, private zone: NgZone,
              private cdr: ChangeDetectorRef, private toastr: ToastrService) {}

  id = '';
  name = '';
  online = false;
  status = '';
  audio: any = { sinks: [], outputs: [], bt: { powered: false, scanning: false, devices: [] } };
  private volDebounce: any = {};

  ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id') || '';
    if (!this.id) return;
    this.load();
    this.event.subscribe(`pu_${this.id}`, (dt: any) => this.zone.run(() => {
      if (dt?.type === 'audio_state') { this.audio = dt.audio || this.audio; }
      else if (dt?.type === 'status') { this.online = dt.status !== 'offline'; this.status = dt.status; }
      try { this.cdr.detectChanges(); } catch {}
    }));
  }

  load() {
    this.api.getUnitAudio(this.id).subscribe({
      next: (r: any) => {
        this.name = r.name || '';
        this.online = r.online;
        this.status = r.status;
        if (r.audio) this.audio = r.audio;
      }
    });
  }

  // ── General ──
  saveName() {
    if (!this.name.trim()) return;
    this.api.renameUnit(this.id, this.name.trim()).subscribe({
      next: () => this.toastr.success('Renamed'),
      error: () => this.toastr.error('Could not rename')
    });
  }

  // ── Outputs ──
  isOutput(name: string): boolean { return (this.audio.outputs || []).includes(name); }
  toggleOutput(sink: any) {
    const cur: string[] = this.audio.outputs || [];
    const next = this.isOutput(sink.name) ? cur.filter(n => n !== sink.name) : [...cur, sink.name];
    this.audio.outputs = next; // optimistic
    this.api.setUnitOutputs(this.id, next).subscribe({ error: () => this.toastr.error('Could not set output') });
  }
  onVolume(sink: any, level: number) {
    sink.volume = Math.round(level * 100);
    clearTimeout(this.volDebounce[sink.name]);
    this.volDebounce[sink.name] = setTimeout(() => {
      this.api.setSinkVolume(this.id, sink.name, level).subscribe();
    }, 150);
  }

  // ── Bluetooth ──
  private scanTimer: any = null;
  scan() {
    this.audio.bt.scanning = true;
    this.api.btScan(this.id, 8).subscribe({ error: () => this.audio.bt.scanning = false });
    // Safety net: clear the spinner even if the completion event is missed.
    clearTimeout(this.scanTimer);
    this.scanTimer = setTimeout(() => { this.audio.bt.scanning = false; this.cdr.detectChanges(); }, 14000);
  }
  bt(action: 'pair' | 'connect' | 'disconnect' | 'remove', d: any) {
    this.api.btAction(this.id, action, d.mac).subscribe({
      next: () => this.toastr.success(`${action}: ${d.name}`),
      error: () => this.toastr.error(`Could not ${action}`)
    });
  }
}
