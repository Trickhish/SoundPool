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
      // 401 = the session is invalid -> log out. A 403 just means this specific
      // action is forbidden (e.g. a party guest lacking a right); don't log out.
      if (error.status==401) {
        localStorage.removeItem("token");
        router.navigate(['/login']);
      }
      return throwError(error);
    })
  ));
};