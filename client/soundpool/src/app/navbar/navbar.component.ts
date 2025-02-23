import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { Router, RouterOutlet, RouterLink, NavigationEnd } from '@angular/router';
import { TranslateService,TranslateModule } from '@ngx-translate/core';

import { FontAwesomeModule, FaIconLibrary } from '@fortawesome/angular-fontawesome';
import {  } from '@fortawesome/free-regular-svg-icons';
import { faRightFromBracket } from '@fortawesome/free-solid-svg-icons';
import { ApiService } from '../api.service';

@Component({
  selector: 'app-navbar',
  imports: [RouterOutlet, RouterLink, TranslateModule, CommonModule, FontAwesomeModule],
  templateUrl: './navbar.component.html',
  styleUrl: './navbar.component.scss'
})
export class NavbarComponent {
  constructor(
    private library: FaIconLibrary,
    private router: Router,
    private translate: TranslateService,
    public api: ApiService
  ) { 
    this.router.events.subscribe(event => {
      if (event instanceof NavigationEnd) {
        this.currentRoute = event.urlAfterRedirects;
      }
    });

    library.addIcons(faRightFromBracket);
  }

  currentRoute: string = '';

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

  closeBurger() {
    document.querySelector(".burger_ctn")?.classList.remove('active');
    document.querySelector(".navbar")?.classList.remove('active');
  }

  logout() {
    localStorage.setItem("token", "");
    this.router.navigate(["/login"]);
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
    if (this.router.url=='/') {
      this.router.navigate(['/home']);
    }
  }
}
