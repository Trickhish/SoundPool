import { Routes } from '@angular/router';
import { HomeComponent } from './home/home.component';
import { LoginComponent } from './login/login.component';
import { authGuard } from './auth.guard';
import { RegisterComponent } from './register/register.component';
import { NavbarComponent } from './navbar/navbar.component';
import { ProfileComponent } from './profile/profile.component';
import { RoomsComponent } from './rooms/rooms.component';
import { PlaylistsComponent } from './playlists/playlists.component';
import { PlayerunitsComponent } from './playerunits/playerunits.component';
import { PlayerComponent } from './player/player.component';

export const routes: Routes = [
    {
        path:'',
        component: NavbarComponent,
        children: [
            {path:'home', component: HomeComponent, canActivate: [authGuard]},
            {path:'rooms', component: RoomsComponent, canActivate: [authGuard]},
            {path:'profile', component: ProfileComponent, canActivate: [authGuard]},
            {path:'playlists', component: PlaylistsComponent, canActivate: [authGuard]},
            {path:'units', component: PlayerunitsComponent, canActivate: [authGuard]},
            {path:'player/:player_id', component: PlayerComponent, canActivate: [authGuard]}
        ]
    },
    {path:'login', component:LoginComponent},
    {path:'register', component:RegisterComponent},
    {path:'**', redirectTo:'/login' }
];