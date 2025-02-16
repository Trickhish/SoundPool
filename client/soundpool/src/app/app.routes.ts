import { Routes } from '@angular/router';
import { HomeComponent } from './home/home.component';
import { LoginComponent } from './login/login.component';
import { authGuard } from './auth.guard';
import { RegisterComponent } from './register/register.component';

export const routes: Routes = [
    {path:'', component:HomeComponent, canActivate: [authGuard]},
    {path:'login', component:LoginComponent},
    {path:'register', component:RegisterComponent},
    {path:'**', redirectTo:'/login' }
];