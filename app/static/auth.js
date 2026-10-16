// Acceso al panel de Lince: todas las llamadas a la API llevan el token
// (LINCE_API_TOKEN del .env). Se pide una vez y se guarda en este navegador.
(function () {
  const CLAVE = 'lince_token';
  const leer = () => { try { return localStorage.getItem(CLAVE) || ''; } catch (e) { return ''; } };
  const guardar = (t) => { try { localStorage.setItem(CLAVE, t); } catch (e) {} };
  const pedir = () => {
    const t = (window.prompt('Token de acceso a Lince (LINCE_API_TOKEN):') || '').trim();
    if (t) guardar(t);
    return t;
  };
  const original = window.fetch.bind(window);
  window.fetch = async function (url, opts) {
    const conToken = (token) => {
      const o = Object.assign({}, opts || {});
      o.headers = Object.assign({}, (opts && opts.headers) || {}, { 'X-Lince-Token': token });
      return original(url, o);
    };
    let r = await conToken(leer() || pedir());
    if (r.status === 401) r = await conToken(pedir());
    return r;
  };
  window.linceSalir = () => { try { localStorage.removeItem(CLAVE); } catch (e) {} location.reload(); };
})();
