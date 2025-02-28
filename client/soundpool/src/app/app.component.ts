import { Component, HostListener } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';
import { LivefbService } from './livefb.service';
import { ApiService } from './api.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  constructor(
    private translate: TranslateService,
    private livefb: LivefbService,
    private api: ApiService
  ) {
    this.translate.setDefaultLang('en');
    this.translate.use(localStorage.getItem('lang') || 'en');
  }

  title = 'soundpool';

  switchLanguage(lang: string) {
    this.translate.use(lang);
    localStorage.setItem('lang', lang);
  }

  ngOnInit() {
    this.api.vtk().subscribe({
      next: (r)=> {
        this.livefb.launch();
      },
      error: (err)=> {
        localStorage.removeItem("token");
      }
    });
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    var tg = event.target as HTMLElement;

    for (var e of document.querySelectorAll(".dismissible")) {
      if (!tg.classList.contains('donotdismiss') && !e.contains(tg)) {
        e.classList.remove('active');

        var al = e.getAttribute("data-activateonhide");
        if (al!=null) {
          for (var tae of JSON.parse(al)) {
            document.querySelector(tae).classList.add("active");
          }
        }
      }
    }
  }
}
