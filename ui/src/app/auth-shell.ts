import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  OnInit,
  inject,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { App } from './app';
import {
  ApiToken,
  AuthService,
  AuthUser,
  Invitation,
  UserRole,
  appUrl,
} from './services/auth.service';

type ShellView = 'app' | 'login' | 'onboarding' | 'invite' | 'users' | 'profile';

@Component({
  selector: 'app-root',
  imports: [FormsModule, DatePipe, App],
  templateUrl: './auth-shell.html',
  styleUrl: './auth-shell.sass',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuthShell implements OnInit {
  private auth = inject(AuthService);
  private cdr = inject(ChangeDetectorRef);

  loading = true;
  readonly homeUrl = appUrl();
  submitting = false;
  view: ShellView = 'app';
  user: AuthUser | null = null;
  error = '';
  success = '';

  username = '';
  password = '';
  passwordConfirmation = '';
  invitationToken = '';
  invitation: Invitation | null = null;

  users: AuthUser[] = [];
  invitations: Invitation[] = [];
  invitationRole: UserRole = 'user';
  createdInvitationLink = '';

  currentPassword = '';
  newPassword = '';
  newPasswordConfirmation = '';
  tokens: ApiToken[] = [];
  tokenName = '';
  revealedToken = '';

  ngOnInit() {
    this.view = this.routeView();
    this.invitationToken = new URLSearchParams(window.location.search).get('token') ?? '';
    if (this.view === 'invite') {
      this.loadInvitation();
      return;
    }
    this.auth.status().subscribe({
      next: (status) => {
        if (status.setup_required) {
          if (this.view !== 'onboarding') {
            window.location.replace(appUrl('onboarding'));
            return;
          }
        } else if (!status.authenticated) {
          if (this.view !== 'login') {
            window.location.replace(appUrl('login'));
            return;
          }
        } else {
          this.user = status.user;
          if (this.view === 'login' || this.view === 'onboarding') {
            window.location.replace(appUrl());
            return;
          }
          if (this.view === 'users') {
            if (this.user?.role !== 'admin') {
              window.location.replace(appUrl());
              return;
            }
            this.loadUsers();
          } else if (this.view === 'profile') {
            this.loadTokens();
          }
        }
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error),
    });
  }

  private routeView(): ShellView {
    const segment = window.location.pathname.replace(/\/+$/, '').split('/').pop();
    if (segment === 'login' || segment === 'onboarding' || segment === 'users' || segment === 'profile') {
      return segment;
    }
    if (segment === 'invite') {
      return 'invite';
    }
    return 'app';
  }

  private loadInvitation() {
    if (!this.invitationToken) {
      this.error = 'This invitation link is incomplete.';
      this.loading = false;
      return;
    }
    this.auth.invitation(this.invitationToken).subscribe({
      next: (invitation) => {
        this.invitation = invitation;
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error),
    });
  }

  submitCredentials() {
    this.clearMessages();
    if (this.view !== 'login' && this.password !== this.passwordConfirmation) {
      this.error = 'Passwords do not match.';
      return;
    }
    this.submitting = true;
    const operation =
      this.view === 'onboarding'
        ? this.auth.onboarding(this.username, this.password)
        : this.auth.login(this.username, this.password);
    operation.pipe(finalize(() => {
      this.submitting = false;
      this.cdr.markForCheck();
    })).subscribe({
      next: () => window.location.replace(appUrl()),
      error: (error) => this.fail(error, false),
    });
  }

  acceptInvitation() {
    this.clearMessages();
    if (this.password !== this.passwordConfirmation) {
      this.error = 'Passwords do not match.';
      return;
    }
    this.submitting = true;
    this.auth
      .acceptInvitation(this.invitationToken, this.username, this.password)
      .pipe(finalize(() => {
        this.submitting = false;
        this.cdr.markForCheck();
      }))
      .subscribe({
        next: () => window.location.replace(appUrl()),
        error: (error) => this.fail(error, false),
      });
  }

  logout() {
    this.auth.logout().subscribe({
      next: () => window.location.replace(appUrl('login')),
      error: () => window.location.replace(appUrl('login')),
    });
  }

  private loadUsers() {
    this.auth.users().subscribe({
      next: (users) => {
        this.users = users.map((user) => ({ ...user }));
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error),
    });
    this.auth.invitations().subscribe({
      next: (invitations) => {
        this.invitations = invitations;
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error),
    });
  }

  saveUser(user: AuthUser) {
    this.clearMessages();
    this.auth.updateUser(user).subscribe({
      next: (result) => {
        Object.assign(user, result.user);
        this.success = `${user.username} was updated.`;
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error, false),
    });
  }

  revokeUser(user: AuthUser) {
    if (!window.confirm(`Sign ${user.username} out everywhere and revoke all API tokens?`)) {
      return;
    }
    this.auth.revokeUser(user.id).subscribe({
      next: () => {
        this.success = `Access was revoked for ${user.username}.`;
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error, false),
    });
  }

  deleteUser(user: AuthUser) {
    if (!window.confirm(`Permanently delete ${user.username}?`)) {
      return;
    }
    this.auth.deleteUser(user.id).subscribe({
      next: () => {
        this.users = this.users.filter((item) => item.id !== user.id);
        this.success = `${user.username} was deleted.`;
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error, false),
    });
  }

  createInvitation() {
    this.clearMessages();
    this.auth.createInvitation(this.invitationRole).subscribe({
      next: ({ invitation }) => {
        this.invitations = [invitation, ...this.invitations];
        this.createdInvitationLink =
          `${window.location.origin}${appUrl(`invite/${encodeURIComponent(invitation.token ?? '')}`)}`;
        this.success = 'Invitation created. Copy it now; the secret is shown only once.';
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error, false),
    });
  }

  copyInvitation() {
    if (!this.createdInvitationLink) {
      return;
    }
    if (!navigator.clipboard?.writeText) {
      this.error = 'Clipboard access is unavailable. Select and copy the link manually.';
      this.cdr.markForCheck();
      return;
    }
    navigator.clipboard.writeText(this.createdInvitationLink).then(
      () => {
        this.success = 'Invitation link copied.';
        this.cdr.markForCheck();
      },
      () => {
        this.error = 'Could not copy the link. Select and copy it manually.';
        this.cdr.markForCheck();
      },
    );
  }

  revokeInvitation(invitation: Invitation) {
    this.auth.revokeInvitation(invitation.id).subscribe({
      next: () => {
        this.invitations = this.invitations.filter((item) => item.id !== invitation.id);
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error, false),
    });
  }

  private loadTokens() {
    this.auth.tokens().subscribe({
      next: (tokens) => {
        this.tokens = tokens;
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error),
    });
  }

  changePassword() {
    this.clearMessages();
    if (this.newPassword !== this.newPasswordConfirmation) {
      this.error = 'New passwords do not match.';
      return;
    }
    this.auth.changePassword(this.currentPassword, this.newPassword).subscribe({
      next: () => {
        this.currentPassword = '';
        this.newPassword = '';
        this.newPasswordConfirmation = '';
        this.success = 'Password changed. Other sessions and API tokens were revoked.';
        this.tokens = [];
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error, false),
    });
  }

  createToken() {
    this.clearMessages();
    this.auth.createToken(this.tokenName).subscribe({
      next: ({ token }) => {
        this.tokens = [token, ...this.tokens];
        this.revealedToken = token.token ?? '';
        this.tokenName = '';
        this.success = 'API token created. Copy it now; it will not be shown again.';
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error, false),
    });
  }

  revokeToken(token: ApiToken) {
    this.auth.revokeToken(token.id).subscribe({
      next: () => {
        this.tokens = this.tokens.filter((item) => item.id !== token.id);
        this.cdr.markForCheck();
      },
      error: (error) => this.fail(error, false),
    });
  }

  private clearMessages() {
    this.error = '';
    this.success = '';
  }

  private fail(error: unknown, stopLoading = true) {
    const candidate = error as { error?: { msg?: string }; message?: string };
    this.error = candidate?.error?.msg || candidate?.message || 'Request failed.';
    if (stopLoading) {
      this.loading = false;
    }
    this.cdr.markForCheck();
  }
}
