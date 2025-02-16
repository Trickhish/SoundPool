import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class AuthService {

  isAuthenticated(): boolean {
    return !!localStorage.getItem('token');
  }

  login(mail:String, password:String): void {
    //localStorage.setItem('token', token);
  }

  logout(): void {
    localStorage.removeItem('token');
  }
}
