import { Component, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { FontAwesomeModule, FaIconLibrary } from '@fortawesome/angular-fontawesome';
import { faStar as farStar, faEye, faEyeSlash } from '@fortawesome/free-regular-svg-icons';
import { faStar as fasStar, faEye as fasEye } from '@fortawesome/free-solid-svg-icons';
import { AuthService } from '../auth.service';
import { FormsModule,FormControl } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { TranslateService,TranslateModule } from '@ngx-translate/core';

@Component({
  selector: 'app-register',
  imports: [FontAwesomeModule, FormsModule, TranslateModule],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss'
})
export class RegisterComponent {
  constructor(
    library: FaIconLibrary,
    private authService: AuthService,
    private translate: TranslateService
  ) {
    library.addIcons(faEye, fasEye, faEyeSlash);

    
  }

  username: string = '';
  password: string = '';
  errorMessage: string = '';
  passwordVisible: boolean = false;

  resetErr() {
    this.errorMessage="";
  }

  showPass() {
    this.passwordVisible=!this.passwordVisible;
  }

  login() {
    console.log(this.username, this.password);
  }
}
