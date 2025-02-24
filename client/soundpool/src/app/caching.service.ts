import { Injectable } from '@angular/core';
import { Observable, of, tap } from 'rxjs';
import { HttpClient, HttpHeaders, HttpResponse, HttpRequest, HttpHandler, HttpEvent, HttpInterceptor, HttpErrorResponse, HttpParams } from '@angular/common/http';

@Injectable({
  providedIn: 'root'
})
export class CachingService {
  constructor() { }

  cachedData:{[id: string]: any;} = {};

  getTs() {
    return((new Date()).getTime());
  }

  setData(name:string, data:any) {
    this.cachedData[name] = [this.getTs(), data];
  }

  fetchF(ff:Function) {

  }

  fetchData(name:string, fetch_func:Function): Observable<{ currentData: any, newData$: Observable<any> }> {
    if (Object.keys(this.cachedData).includes(name)) {
      var [ts, dt] = this.cachedData[name];

      if ((this.getTs()-ts) > 5000) {
        const newData$ = fetch_func().pipe(
          tap((r: any) => {
            this.cachedData[name] = [this.getTs(), r];
          })
        );
  
        return of({
          currentData: dt,
          newData$: newData$
        });

        /*return fetch_func().pipe(
          tap((r: any) => {
            this.cachedData[name] = [this.getTs(), r];
          })
        );*/
      } else {
        return(of({
          currentData: dt,
          newData$: of(dt)
        }));
      }
    } else {
      const newData$ = fetch_func().pipe(
        tap((r: any) => {
          this.cachedData[name] = [this.getTs(), r];
        })
      );

      return of({
        currentData: null,
        newData$: newData$
      });
      /*return fetch_func().pipe(
        tap((r: any) => {
          this.cachedData[name] = [this.getTs(), r];
        })
      );*/
    }
  }
}
