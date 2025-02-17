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

  toast(msg:string, title:string, type:string="info", dur:number=3000) {
    switch(type) {
      case "success":
        this.toastr.success(msg, title, {timeOut: dur});
        break;
      case "error":
        this.toastr.error(msg, title, {timeOut: dur});
        break;
      case "success":
        this.toastr.success(msg, title, {timeOut: dur});
        break;
      case "warning":
        this.toastr.warning(msg, title, {timeOut: dur});
        break;
      default:
        this.toastr.info(msg, title, {timeOut: dur});
        break;
    }
  }

  trtoast(name:string, type:string="info", dur:number=3000) {
    this.toast(this.translate.instant(name+"_msg"), this.translate.instant(name+"_title"), type, dur);
  }
}
