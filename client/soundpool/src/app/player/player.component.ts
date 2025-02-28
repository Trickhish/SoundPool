import { Component } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { NgCircleProgressModule, CircleProgressOptions  } from 'ng-circle-progress';

import { FontAwesomeModule, FaIconLibrary } from '@fortawesome/angular-fontawesome';
import {  } from '@fortawesome/free-regular-svg-icons';
import { faPlay, faPlayCircle } from '@fortawesome/free-solid-svg-icons';
import { CachingService } from '../caching.service';
import { ApiService } from '../api.service';
import { Unit } from '../unit';

@Component({
  selector: 'app-player',
  imports: [NgCircleProgressModule, FontAwesomeModule],
  templateUrl: './player.component.html',
  styleUrl: './player.component.scss',
  providers: [
    {
      provide: CircleProgressOptions,
      useValue: {
        radius: 50,
        outerStrokeWidth: 10,
        innerStrokeWidth: 5,
        outerStrokeColor: "#4CAF50",
        innerStrokeColor: "#ddd",
        animation: true,
        animationDuration: 300,
        showTitle: false,
        showUnits: false,
        showSubtitle: false
      }
    }
  ]
})
export class PlayerComponent {
  constructor(
    private aroute: ActivatedRoute,
    private library: FaIconLibrary,
    private cache: CachingService,
    private api: ApiService
  ) {
    window.addEventListener('mousemove', (event) => this.onMouseMove(event));
    window.addEventListener('mouseup', () => this.onMouseUp());

    library.addIcons(faPlay, faPlayCircle);
  }

  pid:string|null=null;
  cover_url = "https://cdn-images.dzcdn.net/images/cover/32f4a932b43df0dbb6adfcab87a3c739/500x500-000000-80-0-0.jpg"; // soundpool_sqrd.png, ex_cover.jpg
  movingProgress:boolean = false;
  musicProgress:number = 0;
  mouseMoving:boolean = false;
  playing:boolean = false;
  player:Unit|null = null;


  async loadContent() {
    this.cache.fetchData("", ()=>{
      return(this.api.getPlayer(this.pid!));
    }).subscribe({
      next: (r)=> {
        console.log(r);
      }
    });


    this.cache.fetchData(`player_${this.pid!}`, ()=>{
      return(this.api.getPlayer(this.pid!));
    }).subscribe({
      next: (r)=> {
        if (r.currentData!=null) {
          this.player = r.currentData;
        }
        r.newData$.subscribe({
          next: (dt)=> {
            this.player = dt;
          },
          error: (err)=> {
            console.log(err);
          }
        });
      }
    });
  }


  ngOnInit() {
    this.pid = this.aroute.snapshot.paramMap.get('player_id');

    if (!this.pid) {
      return;
    }

    this.loadContent();
  }

  setPct(ev:MouseEvent) {
    var svg = document.querySelector("#music_svg");
    const rect = svg!.getBoundingClientRect();
    var cx = ev.pageX;
    var cy = ev.pageY;
    var x = cx - rect.left;
    var y = cy - rect.top;

    const dx = x - rect.width/2;
    const dy = y - rect.height/2;
    var angle = ((Math.atan2(dy, dx)/Math.PI)*50) + 25; // 57.3

    if (angle < 0) {
      angle = 100+angle;
    }

    var ags = angle.toString();

    //var ctn:HTMLElement = document.querySelector("#music_ctn")!;
    //ctn.style.setProperty("--percent", ags);
    this.musicProgress = angle
  }

  followMouse(ev:MouseEvent) {
    this.movingProgress = true;
    console.log(ev);
  }

  onMouseMove(ev: MouseEvent): void {
    this.mouseMoving=true;
    if (this.movingProgress) {
      this.setPct(ev);
    }
  }

  onMouseUp() {
    this.movingProgress=false;
    console.log(this.musicProgress);
    this.mouseMoving=false;
  }
}
