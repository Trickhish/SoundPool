import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../api.service';
import { ToastrService } from 'ngx-toastr';

@Component({
  selector: 'app-rooms',
  imports: [CommonModule, FormsModule],
  templateUrl: './rooms.component.html',
  styleUrl: './rooms.component.scss'
})
export class RoomsComponent implements OnInit {
  constructor(private api: ApiService, private router: Router, private toastr: ToastrService) {}

  rooms: any[] = [];
  loading = true;
  creating = false;
  newName = '';
  newPassword = '';

  ngOnInit() { this.load(); }

  load() {
    this.loading = true;
    this.api.listRooms().subscribe({
      next: (r) => { this.rooms = r; this.loading = false; },
      error: () => { this.loading = false; }
    });
  }

  create() {
    if (!this.newName.trim()) return;
    this.api.createRoom(this.newName.trim(), this.newPassword || undefined).subscribe({
      next: (room) => { this.creating = false; this.newName = ''; this.newPassword = ''; this.open(room); },
      error: () => this.toastr.error('Could not create room')
    });
  }

  enter(room: any) {
    if (room.is_member) { this.open(room); return; }
    let pw: string | undefined;
    if (room.has_password) {
      pw = window.prompt(`Password for "${room.name}"`) || undefined;
      if (pw === undefined) return;
    }
    this.api.joinRoom(room.id, pw).subscribe({
      next: (r) => this.open(r),
      error: () => this.toastr.error('Could not join (wrong password?)')
    });
  }

  open(room: any) { this.router.navigate(['/room', room.id]); }

  leave(room: any, ev: Event) {
    ev.stopPropagation();
    this.api.leaveRoom(room.id).subscribe({ next: () => this.load() });
  }
}
