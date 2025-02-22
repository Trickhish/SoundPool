import { Component, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { FontAwesomeModule, FaIconLibrary } from '@fortawesome/angular-fontawesome';
import { faStar as farStar, faEye, faEyeSlash } from '@fortawesome/free-regular-svg-icons';
import { faStar as fasStar, faEye as fasEye } from '@fortawesome/free-solid-svg-icons';
import { AuthService } from '../auth.service';
import { FormsModule,FormControl } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { TranslateService,TranslateModule } from '@ngx-translate/core';
import { DisplayService } from '../display.service';
import { Router } from '@angular/router';

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
    private translate: TranslateService,
    private auth: AuthService,
    private disp: DisplayService,
    private router: Router
  ) {
    library.addIcons(faEye, fasEye, faEyeSlash);

    
  }

  mail: string = '';
  username: string = '';
  password: string = '';
  passwordVisible: boolean = false;
  errmsg: string = "";

  showPass() {
    this.passwordVisible=!this.passwordVisible;
  }

  resetErr() {
    this.errmsg="";
    document.querySelectorAll(".auth_ctn input").forEach((e)=>{
      e.classList.remove("err");
    });
  }

  register() {
    if (this.username.trim()=="" || this.mail.trim()=="" || this.password.trim()=="") {
      //this.disp.trtoast("empty_field", "error");
      this.errmsg = this.translate.instant("empty_field_msg");
      if (this.mail.trim()=="") {
        document.querySelector("input[name='mail']")?.classList.add("err");
      }
      if (this.username.trim()=="") {
        document.querySelector("input[name='username']")?.classList.add("err");
      }
      if (this.password.trim()=="") {
        document.querySelector("input[name='password']")?.classList.add("err");
      }
      return;
    }

    this.auth.register(this.username, this.mail, this.password).subscribe({
      next: (r)=> {
        console.log("successfully registered: ",r);
        localStorage.setItem("token", r["token"]);

        this.router.navigate(['/']);
      },
      error: (err)=> {
        if (err.status==401) { // wrong credentials
          //this.disp.notif("Adresse email ou mot de passe invalide", 1000, "warning");
          console.log("Email already used");
          this.errmsg = this.translate.instant("used_email_msg");
          //this.disp.trtoast("used_email", "error");
          return;
        } else if (err.status==409) { // not confirmed
          this.errmsg = this.translate.instant("email_not_confirmed");
          //this.disp.notif("Pour confirmer votre compte, cliquez sur le lien qui vous a été envoyé par email.", 5000, "warning")
          return;
        }
        console.log("ERR: ",err);
      }
    });
  }
}
