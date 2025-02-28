import { HttpErrorResponse, HttpEvent, HttpHandler, HttpHandlerFn, HttpInterceptor, HttpInterceptorFn, HttpRequest, HttpResponse } from '@angular/common/http';
import { catchError, map, Observable, throwError } from 'rxjs';
import { inject } from '@angular/core';
import { Router } from '@angular/router';

export const apiInterceptor:HttpInterceptorFn = (req:HttpRequest<any>, next:HttpHandlerFn):Observable<HttpEvent<any>> => {
  const router = inject(Router);

  const clonedRequest = req.clone({
    setHeaders: {
      'X-Token': localStorage.getItem('token')??""
    }
  });

  return(next(clonedRequest).pipe(
    map((event: HttpEvent<any>) => {
      if (event instanceof HttpResponse) {
        //console.log('Response intercepted:', event);
      }
      return event;
    }),
    catchError((error: HttpErrorResponse) => {
      if (error.status==403) {
        localStorage.removeItem("token");
        router.navigate(['/login']);
      }
      return throwError(error);
    })
  ));
};