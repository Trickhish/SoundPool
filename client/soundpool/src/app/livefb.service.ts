import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import {EventSource as es} from 'eventsource'
import { HttpClient } from '@angular/common/http';

@Injectable({
  providedIn: 'root'
})
export class LivefbService {
  constructor(
    private api: ApiService,
    private http: HttpClient
  ) { }
  listening:boolean = false;
  tosub:[string, Function][] = [];
  callbacks:{[id: string]: Function[];} = {};

  startListening() {
    const eventSource = new es(`${ApiService.apiUrl}/event/sse`, {
      fetch: (input, init) =>
        fetch(input, {
          ...init,
          headers: {
            ...init?.headers,
            "x-token": localStorage.getItem("token")??"",
          },
        }),
    });

    eventSource.onopen = ()=> {
      this.listening=true;

      for (var [ev,cb] of this.tosub) {
        this.subscribe(ev, cb);
      }
    }

    eventSource.onmessage = (event) => {
      var [ev, dt] = JSON.parse(event.data)

      for (let cb of this.callbacks[ev]) {
        cb(dt);
      }
    };

    eventSource.onerror = (error) => {
      eventSource.close();
      this.listening=false;
    };

    return () => {
      eventSource.close();
      this.listening=false;
    };
  }

  launch() {
    this.startListening();

    setInterval(() => {
      if (!this.listening) {
        this.startListening();
      }
    }, 2000);
  }



  subscribe(ev: string, cb:Function) {
    var fn=false;
    for (var [evi, cbi] of this.tosub) {
      if (ev==evi && cb==cbi) {
        fn=true;
        break;
      }
    }
    if (!fn) {
      this.tosub.push([ev, cb]);
    }
    

    if (this.listening) {
      this.http.get(`${ApiService.apiUrl}/event/subscribe/${ev}`).subscribe({
        next: (r)=> {
          if (!Object.keys(this.callbacks).includes(ev)) {
            this.callbacks[ev] = [];
          }
          if (!this.callbacks[ev].includes(cb)) {
            this.callbacks[ev].push(cb);
          }
        }
      });
    } else {
      
    }
  }

  listenToEvent(ev: string): Observable<any> {
    return new Observable((observer) => {
      
      // observer.next(dt);
      // observer.error(error);
      
    });
  }
}
