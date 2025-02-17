import { Injectable } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import { ToastrModule, ToastrService } from 'ngx-toastr';

@Injectable({
  providedIn: 'root'
})
export class DisplayService {

  constructor(
    private toastr: ToastrService,
    private translate: TranslateService,
  ) { }

  toast(msg:string, title:string, type:string="info") {
    switch(type) {
      case "success":
        this.toastr.success(msg, title);
        break;
      case "error":
        this.toastr.error(msg, title);
        break;
      default:
        this.toastr.info(msg, title);
        break;
    }
  }

  trtoast(name:string, type:string="info") {
    this.toast(this.translate.instant(name+"_msg"), this.translate.instant(name+"_title"), type);
  }
}
