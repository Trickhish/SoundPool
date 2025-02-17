import { Component, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { FontAwesomeModule, FaIconLibrary } from '@fortawesome/angular-fontawesome';
import { faStar as farStar, faEye, faEyeSlash } from '@fortawesome/free-regular-svg-icons';
import { faStar as fasStar, faEye as fasEye } from '@fortawesome/free-solid-svg-icons';
import { AuthService } from '../auth.service';
import { FormsModule,FormControl } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { TranslateService,TranslateModule } from '@ngx-translate/core';
import { ApiService } from '../api.service';
import { DisplayService } from '../display.service';

@Component({
  selector: 'app-login',
  imports: [FontAwesomeModule, FormsModule, TranslateModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  schemas: []
})
export class LoginComponent {
  constructor(
    library: FaIconLibrary,
    private authService: AuthService,
    private translate: TranslateService,
    private api: ApiService,
    private auth: AuthService,
    private disp: DisplayService,
  ) {
    library.addIcons(faEye, fasEye, faEyeSlash);

    
  }

  email: string = '';
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
    console.log(this.email, this.password);

    if (this.email.trim()=="" || this.password.trim()=="") {
      this.disp.toast(this.translate.instant("empty_field_msg"), this.translate.instant("empty_field_title"), "error");
      return;
    }

    this.auth.login(this.email, this.password).subscribe({
      next: (r: any)=> {
        //this.disp.notif("Connexion réussie", 500, "success");

        console.log(r);
      },
      error: (err)=> {
        if (err.status==401) { // wrong credentials
          //this.disp.notif("Adresse email ou mot de passe invalide", 1000, "warning");
        } else if (err.status==409) { // not confirmed
          //this.disp.notif("Pour confirmer votre compte, cliquez sur le lien qui vous a été envoyé par email.", 5000, "warning")
        }
        console.log("ERR: ",err);
      }
    });
  }
}
