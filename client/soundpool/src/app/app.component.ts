import { Component, HostListener } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  constructor(private translate: TranslateService) {
    this.translate.setDefaultLang('en');
    this.translate.use(localStorage.getItem('lang') || 'en');
  }

  title = 'soundpool';

  switchLanguage(lang: string) {
    this.translate.use(lang);
    localStorage.setItem('lang', lang);
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    var tg = event.target as HTMLElement;

    for (var e of document.querySelectorAll(".dismissible")) {
      if (!tg.classList.contains('donotdismiss') && !e.contains(tg)) {
        e.classList.remove('active');
      }
    }
  }
}
