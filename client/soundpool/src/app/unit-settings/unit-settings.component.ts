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
  location = '';
  online = false;
  status = '';
  audio: any = { sinks: [], outputs: [], bt: { powered: false, scanning: false, devices: [] } };
  private volDebounce: any = {};

  ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id') || '';
    if (!this.id) return;
    this.load();
    this.event.subscribe(`pu_${this.id}`, (dt: any) => this.zone.run(() => {
      if (dt?.type === 'audio_state') {
        this.audio = dt.audio || this.audio;
        this.reportBtResult();
      }
      else if (dt?.type === 'status') { this.online = dt.status !== 'offline'; this.status = dt.status; }
      try { this.cdr.detectChanges(); } catch {}
    }));
  }

  load() {
    this.api.getUnitAudio(this.id).subscribe({
      next: (r: any) => {
        this.name = r.name || '';
        this.location = r.location || '';
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

  saveLocation() {
    this.api.setUnitLocation(this.id, this.location.trim()).subscribe({
      next: () => this.toastr.success('Location saved'),
      error: () => this.toastr.error('Could not save location')
    });
  }

  // ── Outputs ──
  isOutput(name: string): boolean { return (this.audio.outputs || []).includes(name); }
  testOutput(sink: any) {
    this.api.testUnitOutput(this.id, sink.name).subscribe({
      next: () => this.toastr.info('Playing a test sound…'),
      error: () => this.toastr.error('Could not test output')
    });
  }
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
  btBusy: string | null = null;   // mac currently being acted on

  bt(action: 'pair' | 'connect' | 'disconnect' | 'remove', d: any) {
    this.btBusy = d.mac;
    // The real outcome arrives with the next audio_state (bt.last) — the HTTP
    // call only acknowledges that the unit accepted the command.
    this.api.btAction(this.id, action, d.mac).subscribe({
      error: () => this.zone.run(() => {
        this.btBusy = null;
        this.toastr.error(`Could not reach the unit`);
      })
    });
    // Safety net so the spinner can't stick if the unit never reports back.
    clearTimeout(this.btTimer);
    this.btTimer = setTimeout(() => { this.btBusy = null; this.cdr.detectChanges(); }, 45000);
  }

  private btTimer: any = null;
  private lastBtTs = 0;
  /** Toast the outcome of the unit's last Bluetooth action (once per result). */
  private reportBtResult() {
    const last = this.audio?.bt?.last;
    if (!last || !last.ts || last.ts === this.lastBtTs) return;
    this.lastBtTs = last.ts;
    this.btBusy = null;
    clearTimeout(this.btTimer);
    const dev = (this.audio.bt.devices || []).find((x: any) => x.mac === last.mac);
    const name = dev?.name || last.mac;
    const verb: any = { pair: 'Paired', connect: 'Connected', disconnect: 'Disconnected', remove: 'Forgot' };
    if (last.ok) this.toastr.success(name, `${verb[last.action] || last.action} ✓`);
    else this.toastr.error(last.error || 'Failed', `Could not ${last.action} ${name}`);
  }
}
