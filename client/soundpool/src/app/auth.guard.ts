import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';
import { ApiService } from './api.service';


export const authGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const api = inject(ApiService);

  if (authService.isAuthenticated()) {
    if (api.user.username==null) {
      api.updateUser();
    }
    
    return true;
  } else {
    // Remember where they were headed. Scanning a TV's sign-in QR lands on
    // /link?code=… — bouncing to the login page would otherwise throw the code
    // away and the QR would be useless to anyone not already signed in here.
    router.navigate(['/login'], { queryParams: { redirect: state.url } });
    return false;
  }
};