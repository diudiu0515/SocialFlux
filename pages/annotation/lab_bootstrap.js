'use strict';
(() => {
  const backend = new URL(window.SOCIALFLUX_BACKEND_URL);
  let authorization = '';
  let completeLogin;
  const login = new Promise(resolve => { completeLogin = resolve; });
  const dialog = document.createElement('dialog');
  dialog.setAttribute('aria-label', '登录实验管理台');
  dialog.style.cssText = 'width:min(420px,90vw);padding:28px;border:1px solid #d5ded8;border-radius:16px;color:#173d31';
  dialog.innerHTML = '<form><h2>登录实验管理台</h2><p>使用研究者账号查看与管理实验。</p><label>用户名<input name="username" value="socialflux" autocomplete="username" required></label><label>密码<input name="password" type="password" autocomplete="current-password" required></label><p role="status" aria-live="polite"></p><button class="primary" type="submit">登录</button></form>';
  for (const input of dialog.querySelectorAll('input')) input.style.cssText = 'display:block;width:100%;box-sizing:border-box;margin:8px 0 16px;padding:10px';
  document.body.append(dialog);
  dialog.addEventListener('cancel', event => event.preventDefault());
  dialog.showModal();
  dialog.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button');
    const message = form.querySelector('[role="status"]');
    button.disabled = true;
    try {
      const credentials = form.elements.username.value + ':' + form.elements.password.value;
      const header = 'Basic ' + btoa(String.fromCharCode(...new TextEncoder().encode(credentials)));
      const response = await fetch(new URL('/api/lab', backend), {
        headers: {Authorization: header}, credentials: 'omit', cache: 'no-store'
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw Error(response.status === 401 ? '用户名或密码不正确。' : data.error || '暂时无法连接，请稍后重试。');
      }
      authorization = header;
      form.elements.password.value = '';
      dialog.close();
      completeLogin();
      dialog.remove();
    } catch (error) { message.textContent = error.message; }
    finally { button.disabled = false; }
  };
  window.socialfluxLabRequest = async (path, options = {}) => {
    const target = new URL(path, backend);
    if (target.origin !== backend.origin || !(target.pathname.startsWith('/api/') || target.pathname.startsWith('/media/'))) throw Error('无效的实验接口');
    await login;
    return fetch(target, {...options, credentials: 'omit',
      headers: {...options.headers, Authorization: authorization}});
  };
})();
