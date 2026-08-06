// US-1.4 — view and edit profile.
// Contract: api.me() -> {id, email, name}; api.updateProfile({name?, email?})
// -> updated UserOut. 400 if neither field changes; 409 on duplicate email.
import { useState } from 'react';
import { api } from '../api';

export default function Profile({ user, onUpdated }) {
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  const dirty = name !== user.name || email !== user.email;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!dirty) {
      setEditing(false);
      return;
    }
    setError(null);
    setSaved(false);
    setBusy(true);
    try {
      const updates = {};
      if (name !== user.name) updates.name = name;
      if (email !== user.email) updates.email = email;
      const updatedUser = await api.updateProfile(updates);
      onUpdated(updatedUser);
      setEditing(false);
      setSaved(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function handleCancel() {
    setName(user.name);
    setEmail(user.email);
    setError(null);
    setEditing(false);
  }

  return (
    <div className="card" style={{ maxWidth: 440, margin: '0 auto' }}>
      <h1>Your account</h1>

      {error && <div className="error">{error}</div>}
      {saved && !editing && <p className="subtle">Profile updated.</p>}

      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="profile-name">Name</label>
          <input
            id="profile-name"
            type="text"
            value={name}
            onChange={(e) => { setName(e.target.value); setEditing(true); setSaved(false); }}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="profile-email">Email</label>
          <input
            id="profile-email"
            type="email"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setEditing(true); setSaved(false); }}
            required
          />
        </div>

        {editing && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="submit" disabled={busy || !dirty}>
              {busy ? 'Saving…' : 'Save changes'}
            </button>
            <button type="button" className="ghost" onClick={handleCancel} disabled={busy}>
              Cancel
            </button>
          </div>
        )}
      </form>
    </div>
  );
}
