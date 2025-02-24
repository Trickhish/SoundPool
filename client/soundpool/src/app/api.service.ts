import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpResponse, HttpRequest, HttpHandler, HttpEvent, HttpInterceptor, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Router } from '@angular/router';
import { catchError, firstValueFrom, map, Observable, of, throwError } from 'rxjs';
import { User } from './user';
import { Song } from './song';
import { AuthService } from './auth.service';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  public static apiUrl = 'http://192.168.1.95:8080';
  public userPP:string = "/assets/user.png";
  mailExpf: RegExp = /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i;
  mailExp: RegExp = /^[\p{L}0-9._%+-]+@[\p{L}0-9.-]+\.[\p{L}]{2,}$/u;
  public user: User = {};

  constructor(
    private http: HttpClient,
    private router: Router,
    private auth: AuthService
  ) {
    
  }

  public checkMail(email: string) {
    return(this.mailExp.test(email));
  }

  public fetchUser() {
    this.http.get(`${ApiService.apiUrl}/user`);
  }

  public updateUser() {
    this.http.get<User>(`${ApiService.apiUrl}/user`).subscribe({
      next: (r)=> {
        this.user = r;
      },
      error: (err)=> {
        console.log(err);
      }
    });
  }

  public async vtk() {
    return this.http.get(`${ApiService.apiUrl}/auth/vtk`).pipe(
      map(() => true),
      catchError(() => of(false))
    );
  }

  public search(q: string) {
    return(this.http.get<Song[]>(`${ApiService.apiUrl}/song/search?q=`+encodeURIComponent(q)));
  }
}