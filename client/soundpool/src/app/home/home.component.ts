import { Component, OnInit } from '@angular/core';
import { TranslateService,TranslateModule } from '@ngx-translate/core';
import { ApiService } from '../api.service';
import { AuthService } from '../auth.service';
import { Router } from '@angular/router';
import { DisplayService } from '../display.service';

import { FontAwesomeModule, FaIconLibrary } from '@fortawesome/angular-fontawesome';
import {  } from '@fortawesome/free-regular-svg-icons';
import { faGlobe } from '@fortawesome/free-solid-svg-icons';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-home',
  imports: [TranslateModule, FontAwesomeModule, CommonModule],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss'
})
export class HomeComponent {
  constructor(
      private library: FaIconLibrary,
      private translate: TranslateService,
      private api: ApiService,
      private auth: AuthService,
      private disp: DisplayService,
      private router: Router
  ) {
    library.addIcons(faGlobe);
  }
  
  langImg(lg=this.translate.currentLang) {
    if (['us','en','uk','eng'].includes(lg)) {
      lg="us";
    }
    return(`/assets/flags/${lg}.svg`);
  }

  langs() {
    return(['en', 'fr']);
    //return(this.translate.langs);
  }

  selectLang() {
    document.querySelector(".lang_ctn")?.classList.add('active');
    document.querySelector("#langbtn")?.classList.remove('active');
  }

  setLang(lg: string) {
    localStorage.setItem("lang", lg);
    document.querySelector(".lang_ctn")?.classList.remove('active');
    document.querySelector("#langbtn")?.classList.add('active');
    
    this.translate.use(lg);
  }

  goto(p: string) {
    document.querySelector(".burger_ctn")?.classList.remove('active');
    document.querySelector(".navbar")?.classList.remove('active');
  }

  burger(ev: Event) {
    var tg = ev.target as HTMLElement;

    if (tg.classList.contains('active')) {
      tg.classList.remove('active');
      document.querySelector(".navbar")?.classList.remove('active');
    } else {
      tg.classList.add('active');
      document.querySelector(".navbar")?.classList.add('active');
    }
    
  }

  ngOnInit() {

  }
}
