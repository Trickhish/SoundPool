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
    router.navigate(['/login']);
    return false;
  }
};