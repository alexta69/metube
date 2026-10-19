/// <reference types="@angular/localize" />

import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { AuthShell } from './app/auth-shell';


bootstrapApplication(AuthShell, appConfig)
  .catch((err) => console.error(err));