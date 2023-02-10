import { BrowserModule } from '@angular/platform-browser';
import { NgModule } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NgbModule } from '@ng-bootstrap/ng-bootstrap';
import { HttpClientModule } from '@angular/common/http';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import { CookieService } from 'ngx-cookie-service';

import { AppComponent } from './app.component';
import { EtaPipe, SpeedPipe, EncodeURIComponent } from './downloads.pipe';
import { MasterCheckboxComponent, SlaveCheckboxComponent } from './master-checkbox.component';
import { MeTubeSocket } from './metube-socket';
import { NgSelectModule } from '@ng-select/ng-select';

@NgModule({
  declarations: [
    AppComponent,
    EtaPipe,
    SpeedPipe,
    EncodeURIComponent,
    MasterCheckboxComponent,
    SlaveCheckboxComponent
  ],
  imports: [
    BrowserModule,
    FormsModule,
    NgbModule,
    HttpClientModule,
    FontAwesomeModule,
    NgSelectModule
  ],
  providers: [CookieService, MeTubeSocket],
  bootstrap: [AppComponent]
})
export class AppModule { }
