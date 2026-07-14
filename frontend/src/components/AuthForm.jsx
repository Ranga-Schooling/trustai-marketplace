// E5 Frontend (owner: Adrian) — US-1.1/US-1.2 auth screens.
// Contract: api.register({email, name, password}), api.login({email, password})
// -> {access_token}; store via setToken(), then api.me() -> user object.
// TODO(E5): login/register modes, field state, inline error display,
// disabled button while busy. Style tokens are in styles.css.
import { api, setToken } from '../api';

export default function AuthForm({ onSignedIn }) {
  return (
    <div className="card" style={{ maxWidth: 440, margin: '0 auto' }}>
      <h1>Sign in</h1>
      <p className="subtle">TODO(E5/US-1.2): build the auth form.</p>
    </div>
  );
}
