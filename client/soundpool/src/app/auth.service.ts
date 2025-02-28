import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpResponse, HttpRequest, HttpHandler, HttpEvent, HttpInterceptor, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Router } from '@angular/router';
import { ApiService } from './api.service';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  constructor(
    private http: HttpClient,
    private router: Router,
    private api: ApiService
  ) { }

  isAuthenticated(): boolean {
    var tk = localStorage.getItem('token');
    if (tk==null || tk=="") {
      return(false)
    } else {
      /*this.api.vtk().subscribe({

      });*/
      return(true);
    }
  }

  getcookie(cname:string) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
  }

  setcookie(name:string, value:string, exmins:number) {
      const d = new Date();
      d.setTime(d.getTime() + (exmins*60*1000));
      var expires = "expires="+ d.toUTCString();
      document.cookie = name + "=" + value + ";" + expires + ";path=/";
      //alert(name + "=" + value+' => '+document.cookie);
  }

  public login(mail: string, pass: string): Observable<any> {
    return(this.http.post(`${ApiService.apiUrl}/auth/login`, {
      "email": mail,
      "password": pass
    }));
  }

  public register(username:string, mail:string, pass:string): Observable<any> {
    return(this.http.post(`${ApiService.apiUrl}/auth/register`, {
      "username": username,
      "email": mail,
      "password": pass
    }));
  }
}
