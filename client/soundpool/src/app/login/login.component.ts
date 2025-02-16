import { Component, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { FontAwesomeModule, FaIconLibrary } from '@fortawesome/angular-fontawesome';
import { faStar as farStar, faEye, faEyeSlash } from '@fortawesome/free-regular-svg-icons';
import { faStar as fasStar, faEye as fasEye } from '@fortawesome/free-solid-svg-icons';

@Component({
  selector: 'app-login',
  imports: [FontAwesomeModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  schemas: []
})
export class LoginComponent {
  constructor(library: FaIconLibrary) {
    library.addIcons(faEye, fasEye, faEyeSlash);
  }
}
