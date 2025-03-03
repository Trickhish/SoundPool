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
  public static apiUrl = 'http://localhost:8080'; // 192.168.1.94
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

  //
  // INTERACTION WITH THE PLAYER


}