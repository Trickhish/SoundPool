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
  errmsg: string = "";

  showPass() {
    this.passwordVisible=!this.passwordVisible;
  }

  test() {
    this.disp.toast("Here is the body of the toast message.", "Toast Title", "error", 100000);
  }

  resetErr() {
    this.errmsg="";
    document.querySelectorAll(".auth_ctn input").forEach((e)=>{
      e.classList.remove("err");
    });
  }

  login() {
    if (this.email.trim()=="" || this.password.trim()=="") {
      this.errmsg = this.translate.instant("empty_field_msg");
      if (this.email.trim()=="") {
        document.querySelector("input[name='mail']")?.classList.add("err");
      }
      if (this.password.trim()=="") {
        document.querySelector("input[name='password']")?.classList.add("err");
      }
      //this.disp.toast(this.translate.instant("empty_field_msg"), this.translate.instant("empty_field_title"), "error");
      return;
    }

    if (!this.api.checkMail(this.email)) {
      this.errmsg = this.translate.instant("email_format");
      document.querySelector("input[name='mail']")?.classList.add("err");
      return;
    }

    this.auth.login(this.email, this.password).subscribe({
      next: (r: any)=> {
        //this.disp.notif("Connexion réussie", 500, "success");

        console.log(r);
      },
      error: (err)=> {
        if (err.status==401) { // wrong credentials
          this.errmsg = this.translate.instant("bad_credentials");
          document.querySelector("input[name='mail']")?.classList.add("err");
          document.querySelector("input[name='password']")?.classList.add("err");
          //this.disp.notif("Adresse email ou mot de passe invalide", 1000, "warning");
        } else if (err.status==409) { // not confirmed
          this.errmsg = this.translate.instant("email_not_confirmed");
          //this.disp.notif("Pour confirmer votre compte, cliquez sur le lien qui vous a été envoyé par email.", 5000, "warning")
        } else if (err.status==422) {
          this.errmsg = this.translate.instant("email_format");
          document.querySelector("input[name='mail']")?.classList.add("err");
        }
        console.log("ERR: ",err);
      }
    });
  }
}
