import {
  ArrowRightOutlined,
  CloudServerOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  LockOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '@bisheng/api';
import { tokenStore } from '@bisheng/auth';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
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
      <section className="login-showcase" aria-label="AI Gateway">
        <div className="brand login-showcase-brand">
          <span className="brand-mark">B</span>
          <span className="brand-name">
          AI <b>Gateway</b>
          </span>
        </div>

        <div className="login-intro">
          <div className="login-kicker"><span>安全</span><i /> <span>高效</span><i /> <span>智能</span></div>
          <h1><b>AI Gateway</b></h1>
          <p>统一管理企业 AI Agent，提供安全可控的智能服务网关</p>
        </div>

        <div className="login-capabilities">
          <div className="login-capability">
            <span className="login-capability-icon"><SafetyCertificateOutlined /></span>
            <div><strong>安全防护</strong><small>多重身份认证 · 敏感信息过滤 · 全链路加密</small></div>
          </div>
          <div className="login-capability">
            <span className="login-capability-icon"><CloudServerOutlined /></span>
            <div><strong>智能网关</strong><small>统一接入 · 流量调度 · 负载均衡</small></div>
          </div>
          <div className="login-capability">
            <span className="login-capability-icon"><RobotOutlined /></span>
            <div><strong>AI Agent 管理</strong><small>模型调用 · 能力编排 · 监控审计</small></div>
          </div>
        </div>

        {/* <img className="login-visual" src="/login-gateway-visual.png" alt="智能网关安全防护主视觉" /> */}
        <div className="login-signature">BISHENG&nbsp;&nbsp;·&nbsp;&nbsp;AI GATEWAY</div>
      </section>

      <section className="login-card">
        <div className="brand login-brand">
          <span className="brand-mark">B</span>
          <span className="brand-name">
            <b>AI 防火墙</b>
          </span>
        </div>
        <h1>登录 AI Gateway</h1>
        <p>统一管理企业 AI Agent、报告与模型调用。</p>
        <form className="login-form" onSubmit={submit}>
          <label className="login-field">
            <span><UserOutlined />账号</span>
            <div className="login-input-wrap">
              <UserOutlined className="login-input-icon" />
              <input
                className="login-input"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                placeholder="请输入管理员账号"
              />
            </div>
          </label>
          <label className="login-field">
            <span><LockOutlined />密码</span>
            <div className="login-input-wrap">
              <LockOutlined className="login-input-icon" />
              <input
                className="login-input"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                placeholder="请输入密码"
              />
              <button
                className="login-password-toggle"
                type="button"
                aria-label={showPassword ? '隐藏密码' : '显示密码'}
                onClick={() => setShowPassword((visible) => !visible)}
              >
                {showPassword ? <EyeOutlined /> : <EyeInvisibleOutlined />}
              </button>
            </div>
          </label>
          <button className="login-button primary-button" disabled={loading}>
            {loading ? '登录中…' : <><ArrowRightOutlined />登录</>}
          </button>
        </form>
        {error && <div className="error">{error}</div>}
        <div className="login-trust"><SafetyCertificateOutlined />安全连接&nbsp;&nbsp;·&nbsp;&nbsp;数据加密&nbsp;&nbsp;·&nbsp;&nbsp;可信网关</div>
      </section>
    </main>
  );
}
