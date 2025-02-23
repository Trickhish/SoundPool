import { Component } from '@angular/core';
import { Router, RouterOutlet, RouterLink } from '@angular/router';
import { TranslateService,TranslateModule } from '@ngx-translate/core';

@Component({
  selector: 'app-navbar',
  imports: [RouterOutlet, RouterLink, TranslateModule],
  templateUrl: './navbar.component.html',
  styleUrl: './navbar.component.scss'
})
export class NavbarComponent {
  constructor(
    private router: Router,
    private translate: TranslateService
  ) {

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
    if (this.router.url=='/') {
      this.router.navigate(['/home']);
    }
  }
}
