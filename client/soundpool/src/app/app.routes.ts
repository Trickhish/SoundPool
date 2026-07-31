import { Routes } from '@angular/router';
import { HomeComponent } from './home/home.component';
import { LoginComponent } from './login/login.component';
import { authGuard } from './auth.guard';
import { RegisterComponent } from './register/register.component';
import { NavbarComponent } from './navbar/navbar.component';
import { ProfileComponent } from './profile/profile.component';
import { RoomsComponent } from './rooms/rooms.component';
import { PlaylistsComponent } from './playlists/playlists.component';
import { LinkComponent } from './link/link.component';
import { PlayerunitsComponent } from './playerunits/playerunits.component';
import { PlayerComponent } from './player/player.component';
import { UnitSettingsComponent } from './unit-settings/unit-settings.component';
import { PartyJoinComponent } from './party-join/party-join.component';
import { DisplayComponent } from './display/display.component';
import { DisplayPairComponent } from './display-pair/display-pair.component';

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
            {path:'link', component: LinkComponent, canActivate: [authGuard]},
            {path:'room/:player_id', component: PlayerComponent, canActivate: [authGuard], data: {room: true}},
            {path:'unit/:id', component: UnitSettingsComponent, canActivate: [authGuard]}
        ]
    },
    {path:'login', component:LoginComponent},
    {path:'register', component:RegisterComponent},
    {path:'party/:code', component:PartyJoinComponent},
    {path:'display', component:DisplayPairComponent},
    {path:'display/:code', component:DisplayComponent},
    {path:'**', redirectTo:'/login' }
];