import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpResponse, HttpRequest, HttpHandler, HttpEvent, HttpInterceptor, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Router } from '@angular/router';
import { catchError, firstValueFrom, map, Observable, of, throwError } from 'rxjs';
import { User } from './user';
import { Song } from './song';
import { AuthService } from './auth.service';
import { Unit } from './unit';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  public static apiUrl = 'https://api.soundpool.dury.dev';
  public userPP:string = "/assets/user.png";
  mailExpf: RegExp = /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i;
  mailExp: RegExp = /^[\p{L}0-9._%+-]+@[\p{L}0-9.-]+\.[\p{L}]{2,}$/u;
  public user: User = {};
  public user_pu: Unit[] = [];

  constructor(
    private http: HttpClient,
    private router: Router
  ) {
    
  }

  public checkMail(email: string) {
    return(this.mailExp.test(email));
  }

  public fetchUser() {
    this.http.get.bind(this.http)(`${ApiService.apiUrl}/user`);
  }

  public updateUser() {
    this.http.get.bind(this.http)<User>(`${ApiService.apiUrl}/user`).subscribe({
      next: (r)=> {
        this.user = r;
      },
      error: (err)=> {
        console.log(err);
      }
    });
  }

  public async vtks() {
    return this.http.get.bind(this.http)(`${ApiService.apiUrl}/auth/vtk`).pipe(
      map(() => true),
      catchError(() => of(false))
    );
  }

  public vtk() {
    return(this.http.get(`${ApiService.apiUrl}/auth/vtk`));
  }

  public search(q: string) {
    return(this.http.get.bind(this.http)<Song[]>(`${ApiService.apiUrl}/song/search?q=`+encodeURIComponent(q)));
  }

  public getUnits() {
    return(this.http.get.bind(this.http)<Unit[]>(`${ApiService.apiUrl}/user/units`));
  }

  public getPlayer(pid:string) {
    return(this.http.get.bind(this.http)(`${ApiService.apiUrl}/player/${pid}`));
  }


  // INTERACTION WITH THE PLAYER
  //

  public play(pid:string) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/play`, null));
  }
  public pause(pid:string) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/pause`, null));
  }
  public prev(pid:string) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/prev`, null));
  }
  public next(pid:string) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/next`, null));
  }
  public seek(pid:string, percent:number) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/seek`, { percent }));
  }
  public setVolume(pid:string, level:number) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/volume`, { level }));
  }
  public setShuffle(pid:string, on:boolean) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/shuffle`, { on }));
  }
  public setRepeat(pid:string, mode:string) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/repeat`, { mode }));
  }
  public queueMove(pid:string, frm:number, to:number) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/queue/move`, { frm, to }));
  }
  public queueRemove(pid:string, index:number) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/queue/remove`, { index }));
  }
  public queueJump(pid:string, index:number) {
    return(this.http.post.bind(this.http)(`${ApiService.apiUrl}/player/${pid}/queue/jump`, { index }));
  }

  public queueAdd(pid: string, song: {song_id: string, title: string, artist: string, img_url: string}) {
    return this.http.post(`${ApiService.apiUrl}/player/${pid}/queue/add`, song);
  }
  public queueClear(pid: string) {
    return this.http.delete(`${ApiService.apiUrl}/player/${pid}/queue/clear`);
  }
  public queuePlaylist(pid: string, playlistId: number) {
    return this.http.post<{status: string, total: number}>(`${ApiService.apiUrl}/player/${pid}/queue/playlist/${playlistId}`, null);
  }

  //
  // DEEZER AUTH

  public deezerStatus() {
    return this.http.get<{connected: boolean}>(`${ApiService.apiUrl}/deezer/status`);
  }

  public deezerLoginStart() {
    return this.http.post<{code: string, journey_url: string, ttl: number, poll_interval: number, qr_url?: string}>(
      `${ApiService.apiUrl}/deezer/login/start`, null
    );
  }

  public deezerLoginPoll() {
    return this.http.get<{status: string}>(`${ApiService.apiUrl}/deezer/login/poll`);
  }

  public deezerLogout() {
    return this.http.delete(`${ApiService.apiUrl}/deezer/logout`);
  }

  public deezerPlaylists() {
    return this.http.get<{playlists: {id: number, title: string, nb_tracks: number, picture: string}[]}>(`${ApiService.apiUrl}/deezer/playlists`);
  }

  public deezerPlaylistTracks(playlistId: number) {
    return this.http.get<{tracks: {id: string, title: string, artist: string, img_url: string}[]}>(`${ApiService.apiUrl}/deezer/playlist/${playlistId}/tracks`);
  }

  //
  // INTERACTION WITH THE PLAYER


}