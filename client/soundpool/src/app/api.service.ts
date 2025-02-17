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

  constructor(
    private http: HttpClient,
    private router: Router
  ) {
    
  }

  
}