import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpResponse, HttpRequest, HttpHandler, HttpEvent, HttpInterceptor, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Router } from '@angular/router';
import { catchError, map, Observable, throwError } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  public static apiUrl = 'http://localhost:8080';
  public userPP:string = "/assets/user.png";
  mailExpf: RegExp = /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i;
  mailExp: RegExp = /^[\p{L}0-9._%+-]+@[\p{L}0-9.-]+\.[\p{L}]{2,}$/u;

  constructor(
    private http: HttpClient,
    private router: Router
  ) {
    
  }

  checkMail(email: string) {
    return(this.mailExp.test(email));
  }
}