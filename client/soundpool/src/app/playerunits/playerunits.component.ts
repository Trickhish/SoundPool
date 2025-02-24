import { Component } from '@angular/core';
import { ApiService } from '../api.service';
import { Unit } from '../unit';
import { CommonModule } from '@angular/common';
import { LivefbService } from '../livefb.service';
import { CachingService } from '../caching.service';

@Component({
  selector: 'app-playerunits',
  imports: [CommonModule],
  templateUrl: './playerunits.component.html',
  styleUrl: './playerunits.component.scss'
})
export class PlayerunitsComponent {
  constructor(
    public api: ApiService,
    private event: LivefbService,
    private cache: CachingService
  ) {

  }
  firstLoad:boolean = true;
  units: Unit[] = [];

  loadUnits() {
    this.api.getUnits().subscribe({
      next: (r)=> {
        this.api.user_pu = r;
      },
      error: (err)=> {
        
      }
    });
  }

  getUnitById(uid: string) {
    for (var u of this.units) {
      if (u.id==uid) {
        return(u);
      }
    }
    return(null);
  }

  async loadContent() {
    this.cache.fetchData("myunits", ()=>{
      return(this.api.getUnits());
    }).subscribe({
      next: (r)=> {
        if (r.currentData!=null) {
          this.units = r.currentData;
        }
        r.newData$.subscribe({
          next: (dt)=> {
            this.units = dt;
          },
          error: (err)=> {
            console.log(err);
          }
        });
      }
    });
  }

  ngOnInit() {
    this.loadContent();

    if (this.firstLoad) {
      this.event.subscribe("mypu", (dt: any)=>{
        console.log(dt);
        if (dt.type=="status") {
          var id = dt.id;
          var u = this.getUnitById(id);
          if (u!=null) {
            u.online=dt.status;
            u.name=dt.name;
          }
        }
  
        
      });
  
      this.firstLoad=false;
    }
  }
}
