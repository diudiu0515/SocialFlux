'use strict';
(() => {
  const backend = new URL(window.SOCIALFLUX_BACKEND_URL);
  const nativeFetch = window.fetch.bind(window);
  let authorization = '';
  const dialog = document.createElement('dialog');
  dialog.setAttribute('aria-label', '登录实验管理台');
  dialog.style.cssText = 'width:min(420px,90vw);padding:28px;border:1px solid #d5ded8;border-radius:16px;color:#173d31';
  dialog.innerHTML = '<form><h2>登录标注管理</h2><p>研究者登录后查看实时汇总和管理实验。参与标注无需登录。</p><label>用户名<input name="username" value="socialflux" autocomplete="username" required></label><label>密码<input name="password" type="password" autocomplete="current-password" required></label><p role="status" aria-live="polite"></p><button class="primary" type="submit">登录</button> <button type="button" data-close>稍后登录</button></form>';
  for (const input of dialog.querySelectorAll('input')) input.style.cssText = 'display:block;width:100%;box-sizing:border-box;margin:8px 0 16px;padding:10px';
  document.body.append(dialog);
  const connect = document.createElement('button');
  connect.textContent = '研究者登录';
  connect.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:1000;padding:12px;background:#173d31;color:white;border:0;border-radius:10px;cursor:pointer';
  if (!location.pathname.includes('/annotation')) document.body.append(connect);
  connect.onclick = () => dialog.showModal();
  dialog.querySelector('[data-close]').onclick = () => dialog.close();
  async function request(target, options = {}) {
    try { return await nativeFetch(target, {...options, credentials:'omit', signal:options.signal || AbortSignal.timeout(15000)}); }
    catch { throw Error('无法连接 AutoDL 研究服务器。尚未同步到服务器；请保留本地草稿，稍后重试。'); }
  }
  dialog.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget, button = form.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      const credentials = form.elements.username.value + ':' + form.elements.password.value;
      const header = 'Basic ' + btoa(String.fromCharCode(...new TextEncoder().encode(credentials)));
      const response = await request(new URL('/api/lab', backend), {headers:{Authorization:header},cache:'no-store'});
      if (!response.ok) throw Error(response.status === 401 ? '用户名或密码不正确。' : '服务器暂时不可用，请重试。');
      authorization = header;
      form.elements.password.value = '';
      dialog.close(); connect.textContent = '已连接研究服务器';
      window.dispatchEvent(new Event('socialflux-login'));
    } catch (error) { form.querySelector('[role="status"]').textContent = error.message; }
    finally { button.disabled = false; }
  };
  window.socialfluxLabRequest = async (path, options = {}) => {
    const target = new URL(path, backend), method = (options.method || 'GET').toUpperCase();
    if (target.origin !== backend.origin || !(target.pathname.startsWith('/api/') || target.pathname.startsWith('/media/'))) throw Error('无效的实验接口');
    if (target.pathname.startsWith('/api/annotation/') || target.pathname.startsWith('/media/')) {
      const headers = new Headers(options.headers);
      const code = localStorage.getItem('socialflux-annotation-recovery');
      if (code) headers.set('X-Annotation-Recovery', code);
      if (method === 'GET' && target.pathname === '/api/annotation/status' && !code && window.SOCIALFLUX_PUBLIC_CATALOG)
        return Response.json({session:null,invited:true,catalog:window.SOCIALFLUX_PUBLIC_CATALOG});
      try { return await request(target, {...options, headers}); }
      catch (error) {
        if (method === 'GET' && target.pathname === '/api/annotation/status' && window.SOCIALFLUX_PUBLIC_CATALOG)
          return Response.json({session:null,invited:true,catalog:window.SOCIALFLUX_PUBLIC_CATALOG,connectionError:error.message});
        throw error;
      }
    }
    if (!authorization) {
      if (method === 'GET' && target.pathname === '/api/lab' && window.SOCIALFLUX_PUBLIC_SNAPSHOT)
        return Response.json(window.SOCIALFLUX_PUBLIC_SNAPSHOT);
      dialog.showModal();
      throw Error('请先登录研究服务器。此操作尚未保存。');
    }
    const headers = new Headers(options.headers); headers.set('Authorization', authorization);
    return request(target, {...options, headers});
  };
})();
