import { Injectable } from '@angular/core';
import { Observable, TimeInterval } from 'rxjs';
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
  subbed:[string, Function][] = [];
  callbacks:{[id: string]: Function[];} = {};
  lint:any = null;

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
      //console.log("LISTENNING");

      for (var [ev,cb] of this.tosub) {
        this.subscribe(ev, cb);
        this.subbed.push([ev, cb]);
      }
    }

    eventSource.onmessage = (event) => {
      var [ev, dt] = JSON.parse(event.data)

      for (let cb of this.callbacks[ev]) {
        cb(dt);
      }
    };

    eventSource.onerror = (error) => {
      for (var ev of this.subbed) {
        this.tosub.push(ev);
      }
      this.subbed=[];

      eventSource.close();
      this.listening=false;
    };

    return () => {
      for (var ev of this.subbed) {
        this.tosub.push(ev);
      }
      this.subbed=[];
      
      eventSource.close();
      this.listening=false;
    };
  }

  launch() {
    if (this.listening) {
      return;
    }
    this.startListening();

    this.lint = setInterval(() => {
      if (!this.listening) {
        this.startListening();
      }
    }, 2000);
  }

  stop() {
    if (this.lint!=null) {
      clearInterval(this.lint);
    }
    this.subbed=[];
    this.listening=false;
  }

  isSubbed(ev:any, cb:any) {
    for (var [evi, cbi] of this.subbed) {
      if (ev==evi && cb.toString()==cbi.toString()) {
        return(true);
      }
    }
    return(false);
  }

  isToSub(ev:any, cb:any) {
    for (var [evi, cbi] of this.tosub) {
      if (ev==evi && cb.toString()==cbi.toString()) {
        return(true);
      }
    }
    return(false);
  }

  subscribe(ev: string, cb:Function, pid:string="") {
    var issubbed=this.isSubbed(ev, cb);
    var istosub=this.isToSub(ev, cb);

    if (!istosub) {
      this.tosub.push([ev, cb]);
    }

    if (!issubbed) {
      if (this.listening) {
        this.http.get(`${ApiService.apiUrl}/event/subscribe/${ev}`).subscribe({
          next: (r)=> {
            this.tosub.splice(this.tosub.indexOf([ev, cb]), 1);
            this.subbed.push([ev, cb]);

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
  }

  listenToEvent(ev: string): Observable<any> {
    return new Observable((observer) => {
      
      // observer.next(dt);
      // observer.error(error);
      
    });
  }
}
