import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '@bisheng/api';
import { tokenStore } from '@bisheng/auth';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username || !password) return setError('请输入账号和密码');

    setLoading(true);
    setError('');
    try {
      tokenStore.set(await authApi.login(username, password));
      navigate('/dashboard', { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="brand login-brand">
          <span className="brand-mark">B</span>
          <span className="brand-name">
            BiSheng <b>Gateway</b>
          </span>
        </div>
        <h1>登录 AI Gateway</h1>
        <p>统一管理企业 AI Agent、报告与模型调用。</p>
        <form className="login-form" onSubmit={submit}>
          <label className="login-field">
            <span>账号</span>
            <input
              className="login-input"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              placeholder="请输入账号"
            />
          </label>
          <label className="login-field">
            <span>密码</span>
            <input
              className="login-input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              placeholder="请输入密码"
            />
          </label>
          <button className="login-button primary-button" disabled={loading}>
            {loading ? '登录中…' : '登录'}
          </button>
        </form>
        {error && <div className="error">{error}</div>}
      </section>
    </main>
  );
}