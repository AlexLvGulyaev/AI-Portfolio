import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';

export function LoginPage() {
  const [tokenInput, setTokenInput] = useState('');
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/system';

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setError('');

    if (!tokenInput.trim()) {
      setError('Введите токен');
      return;
    }

    login(tokenInput.trim());
    navigate(from, { replace: true });
  };

  return (
    <div className="admin-login">
      <form className="admin-login__form" onSubmit={handleSubmit}>
        <h1 className="admin-login__title">AI Portfolio Admin</h1>
        {error && <div className="admin-login__error">{error}</div>}
        <label className="admin-login__label" htmlFor="token">
          Admin API Token
        </label>
        <input
          id="token"
          className="admin-login__input"
          type="password"
          value={tokenInput}
          onChange={(e) => setTokenInput(e.target.value)}
          placeholder="Введите ADMIN_API_TOKEN"
          autoComplete="off"
        />
        <button className="admin-login__submit" type="submit">
          Войти
        </button>
      </form>
    </div>
  );
}
