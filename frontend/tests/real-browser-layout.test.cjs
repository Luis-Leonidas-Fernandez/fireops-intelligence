const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const FRONTEND_DIR = path.resolve(__dirname, '..');

// Helper function to serve static frontend files
function startServer() {
  const mimeTypes = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.svg': 'image/svg+xml',
  };

  let mockFailReview = false;
  let mockPendingRequests = [
    {
      id: 501,
      email: 'solicitante.real@bomberos.gob.ar',
      source: 'google',
      requested_at: '2026-10-28T14:30:00Z',
      status: 'pending',
    },
  ];
  let mockInvitations = [
    {
      id: 901,
      email: 'vigente.real@bomberos.gob.ar',
      role: 'SUPERVISOR',
      created_at: '2026-10-28T12:00:00Z',
      expires_at: '2026-10-30T12:00:00Z',
      used_at: null,
      status: 'active',
      registration_request_id: 400,
      reissue_count: 0,
      can_reissue: false,
    },
    {
      id: 902,
      email: 'vencida.real@bomberos.gob.ar',
      role: 'SUPERVISOR',
      created_at: '2026-10-20T12:00:00Z',
      expires_at: '2026-10-22T12:00:00Z',
      used_at: null,
      status: 'expired',
      registration_request_id: 401,
      reissue_count: 1,
      can_reissue: true,
    },
  ];

  const server = http.createServer((req, res) => {
    const parsedUrl = new URL(req.url, 'http://127.0.0.1');

    if (parsedUrl.pathname === '/auth/me') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(
        JSON.stringify({
          id: 1,
          email: 'admin@bomberos.gob.ar',
          display_name: 'Admin Cuartel',
          role: 'ADMINISTRADOR',
        })
      );
      return;
    }
    if (parsedUrl.pathname === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ok' }));
      return;
    }
    if (
      parsedUrl.pathname === '/inventory/categories' ||
      parsedUrl.pathname === '/inventory/assets/' ||
      parsedUrl.pathname === '/inventory/locations' ||
      parsedUrl.pathname === '/inventory/movements'
    ) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify([]));
      return;
    }
    if (parsedUrl.pathname === '/auth/registration-requests' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(mockPendingRequests));
      return;
    }
    if (parsedUrl.pathname === '/auth/invitations' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(mockInvitations));
      return;
    }
    if (parsedUrl.pathname === '/auth/registration-requests/501/review' && req.method === 'POST') {
      if (mockFailReview) {
        res.writeHead(503, { 'Content-Type': 'application/json' });
        res.end(
          JSON.stringify({
            error: {
              code: 'DELIVERY_FAILED',
              message: 'No se pudo enviar el correo de invitación.',
            },
          })
        );
        return;
      }
      mockPendingRequests = [];
      mockInvitations.unshift({
        id: 903,
        email: 'solicitante.real@bomberos.gob.ar',
        role: 'SUPERVISOR',
        created_at: '2026-10-28T15:00:00Z',
        expires_at: '2026-10-30T15:00:00Z',
        used_at: null,
        status: 'active',
        registration_request_id: 501,
        reissue_count: 0,
        can_reissue: false,
      });
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ message: 'Solicitud revisada.' }));
      return;
    }

    if (parsedUrl.pathname === '/solicitudes') {
      res.writeHead(303, { Location: '/?view=Invitaciones&tab=requests' });
      res.end();
      return;
    }

    let filePath = path.join(FRONTEND_DIR, parsedUrl.pathname);

    if (parsedUrl.pathname === '/') {
      filePath = path.join(FRONTEND_DIR, 'index.html');
    } else if (parsedUrl.pathname === '/registro') {
      filePath = path.join(FRONTEND_DIR, 'pages/registro/index.html');
    } else if (parsedUrl.pathname === '/iniciar-sesion') {
      filePath = path.join(FRONTEND_DIR, 'pages/iniciar-sesion/index.html');
    } else if (parsedUrl.pathname === '/privacidad') {
      filePath = path.join(FRONTEND_DIR, 'pages/privacidad/index.html');
    } else if (parsedUrl.pathname === '/terminos') {
      filePath = path.join(FRONTEND_DIR, 'pages/terminos/index.html');
    }

    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      res.writeHead(404);
      res.end('Not Found');
      return;
    }

    const ext = path.extname(filePath);
    res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'text/plain' });
    fs.createReadStream(filePath).pipe(res);
  });

  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({
        server,
        port: server.address().port,
        setMockFailReview: (val) => {
          mockFailReview = Boolean(val);
        },
      });
    });
  });
}

// Simple CDP Client using built-in WebSocket in Node 22
async function createCdpSession(cdpUrl) {
  const ws = new WebSocket(cdpUrl);
  let id = 1;
  const pending = new Map();

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message));
      else resolve(msg.result);
    }
  };

  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  function send(method, params = {}) {
    const reqId = id++;
    return new Promise((resolve, reject) => {
      pending.set(reqId, { resolve, reject });
      ws.send(JSON.stringify({ id: reqId, method, params }));
    });
  }

  return { ws, send };
}

test('Real Browser (Google Chrome 154 Headless): verifies computed styles and mutual exclusivity of forms', async () => {
  if (!fs.existsSync(CHROME_PATH)) {
    console.warn('Chrome binary not found at %s. Skipping real-browser visual test.', CHROME_PATH);
    return;
  }

  const { server, port, setMockFailReview } = await startServer();
  const cdpPort = port + 1000 + Math.floor(Math.random() * 500);

  // Launch real headless Chrome with CDP enabled
  const chromeProcess = spawn(CHROME_PATH, [
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    `--remote-debugging-port=${cdpPort}`,
    'about:blank',
  ]);

  try {
    // Wait for Chrome CDP endpoint to be ready
    let versionData = null;
    for (let i = 0; i < 30; i++) {
      try {
        const resp = await fetch(`http://127.0.0.1:${cdpPort}/json/version`);
        if (resp.ok) {
          versionData = await resp.json();
          break;
        }
      } catch (_e) {
        await new Promise((r) => setTimeout(r, 100));
      }
    }
    assert.ok(versionData, 'Chrome DevTools Protocol endpoint must be responsive');

    // Create a new tab
    const newTabResp = await fetch(`http://127.0.0.1:${cdpPort}/json/new`, { method: 'PUT' });
    const tabData = await newTabResp.json();
    const cdp = await createCdpSession(tabData.webSocketDebuggerUrl);

    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');

    // 1. Navigate to /registro WITHOUT invite token (Estado A)
    await cdp.send('Page.navigate', { url: `http://127.0.0.1:${port}/registro` });
    await new Promise((r) => setTimeout(r, 300)); // Allow DOM & JS execution

    const stylesStateA = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const panel = document.querySelector("#registration-request-panel");
        const form = document.querySelector("#registration-form");
        const googleBtn = document.querySelector("#google-request-button");
        const title = document.querySelector("#registration-title");
        const panelStyle = window.getComputedStyle(panel);
        const formStyle = window.getComputedStyle(form);
        const btnStyle = window.getComputedStyle(googleBtn);
        return {
          panelDisplay: panelStyle.display,
          panelVisibility: panelStyle.visibility,
          formDisplay: formStyle.display,
          formVisibility: formStyle.visibility,
          titleText: title.textContent,
          btnDisplay: btnStyle.display,
          btnColor: btnStyle.color,
          btnBg: btnStyle.backgroundColor,
          btnWidth: parseFloat(btnStyle.width),
        };
      })()`,
      returnByValue: true,
    });

    const resA = stylesStateA.result.value;
    assert.notEqual(resA.panelDisplay, 'none', 'Estado A: Request panel computed display must NOT be none');
    assert.equal(resA.formDisplay, 'none', 'Estado A: Registration form computed display MUST be none');
    assert.equal(resA.titleText, 'Solicitar acceso', 'Estado A: Title must be "Solicitar acceso"');
    assert.equal(resA.btnDisplay, 'flex', 'Google request button display must be flex');
    assert.equal(resA.btnColor, 'rgb(31, 41, 55)', 'Google request button text must be dark (#1f2937)');
    assert.equal(resA.btnBg, 'rgb(255, 255, 255)', 'Google request button background must be white');
    assert.ok(resA.btnWidth > 200, `Google request button must be full-width (got ${resA.btnWidth}px)`);

    // 2. Navigate to /registro WITH invite token in hash (Estado B)
    await cdp.send('Page.navigate', { url: `http://127.0.0.1:${port}/registro#invite=valid-test-token` });
    await new Promise((r) => setTimeout(r, 300));

    const stylesStateB = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const panel = document.querySelector("#registration-request-panel");
        const form = document.querySelector("#registration-form");
        const title = document.querySelector("#registration-title");
        const panelStyle = window.getComputedStyle(panel);
        const formStyle = window.getComputedStyle(form);
        return {
          panelDisplay: panelStyle.display,
          formDisplay: formStyle.display,
          titleText: title.textContent,
        };
      })()`,
      returnByValue: true,
    });

    const resB = stylesStateB.result.value;
    assert.equal(resB.panelDisplay, 'none', 'Estado B: Request panel computed display MUST be none');
    assert.equal(resB.formDisplay, 'grid', 'Estado B: Registration form computed display MUST be grid');
    assert.equal(resB.titleText, 'Crear cuenta', 'Estado B: Title must be "Crear cuenta"');

    // 3. Check footer legal links on /registro
    const footerLinksRegistro = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const priv = document.querySelector('footer.form-footer a[href="/privacidad"]');
        const term = document.querySelector('footer.form-footer a[href="/terminos"]');
        return {
          privExists: Boolean(priv),
          termExists: Boolean(term),
          privText: priv ? priv.textContent.trim() : null,
          termText: term ? term.textContent.trim() : null,
        };
      })()`,
      returnByValue: true,
    });
    assert.equal(footerLinksRegistro.result.value.privExists, true, 'Footer must link to /privacidad');
    assert.equal(footerLinksRegistro.result.value.termExists, true, 'Footer must link to /terminos');

    // 4. Navigate to /iniciar-sesion and check footer legal links
    await cdp.send('Page.navigate', { url: `http://127.0.0.1:${port}/iniciar-sesion` });
    await new Promise((r) => setTimeout(r, 200));

    const footerLinksLogin = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const priv = document.querySelector('footer.form-footer a[href="/privacidad"]');
        const term = document.querySelector('footer.form-footer a[href="/terminos"]');
        return {
          privExists: Boolean(priv),
          termExists: Boolean(term),
        };
      })()`,
      returnByValue: true,
    });
    assert.equal(footerLinksLogin.result.value.privExists, true, 'Login footer must link to /privacidad');
    assert.equal(footerLinksLogin.result.value.termExists, true, 'Login footer must link to /terminos');

    // 5. Navigate to /privacidad and verify responsive layout
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 375,
      height: 667,
      deviceScaleFactor: 2,
      mobile: true,
    });
    await cdp.send('Page.navigate', { url: `http://127.0.0.1:${port}/privacidad` });
    await new Promise((r) => setTimeout(r, 200));

    const privPageData = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const title = document.title;
        const bodyText = document.body.innerText;
        const scrollWidth = document.documentElement.scrollWidth;
        const innerWidth = window.innerWidth;
        const hasOverflow = scrollWidth > innerWidth;
        return {
          title,
          hasDeveloper: bodyText.includes('Luis Leonidas Fernández'),
          hasContactEmail: bodyText.includes('fernandezluis303@gmail.com'),
          hasAAIP: bodyText.includes('Agencia de Acceso a la Información Pública'),
          hasArgon2id: bodyText.includes('Argon2id'),
          hasNoPlaceholders: !bodyText.includes('[Completar]'),
          hasNoINRI: !bodyText.includes('INRI Servicios Digitales'),
          scrollWidth,
          innerWidth,
          hasOverflow,
        };
      })()`,
      returnByValue: true,
    });

    const privRes = privPageData.result.value;
    assert.equal(privRes.title, 'Política de Privacidad | Fire Control');
    assert.equal(privRes.hasDeveloper, true, 'Must identify Luis Leonidas Fernández');
    assert.equal(privRes.hasContactEmail, true, 'Must include contact email');
    assert.equal(privRes.hasAAIP, true, 'Must cite AAIP');
    assert.equal(privRes.hasArgon2id, true, 'Must mention Argon2id');
    assert.equal(privRes.hasNoPlaceholders, true, 'Must NOT contain [Completar]');
    assert.equal(privRes.hasNoINRI, true, 'Must NOT mention INRI Servicios Digitales');
    assert.equal(privRes.hasOverflow, false, `Mobile view must not overflow horizontally (${privRes.scrollWidth} > ${privRes.innerWidth})`);

    // 6. Navigate to /terminos and verify responsive layout
    await cdp.send('Page.navigate', { url: `http://127.0.0.1:${port}/terminos` });
    await new Promise((r) => setTimeout(r, 200));

    const termsPageData = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const title = document.title;
        const bodyText = document.body.innerText;
        const scrollWidth = document.documentElement.scrollWidth;
        const innerWidth = window.innerWidth;
        const hasOverflow = scrollWidth > innerWidth;
        return {
          title,
          hasDeveloper: bodyText.includes('Luis Leonidas Fernández'),
          hasEmergencyWarning: bodyText.includes('100 o 911'),
          has48Hours: bodyText.includes('48 horas'),
          hasNoPlaceholders: !bodyText.includes('[Completar]'),
          hasNoINRI: !bodyText.includes('INRI Servicios Digitales'),
          scrollWidth,
          innerWidth,
          hasOverflow,
        };
      })()`,
      returnByValue: true,
    });

    const termsRes = termsPageData.result.value;
    assert.equal(termsRes.title, 'Términos y Condiciones | Fire Control');
    assert.equal(termsRes.hasDeveloper, true, 'Must identify Luis Leonidas Fernández');
    assert.equal(termsRes.hasEmergencyWarning, true, 'Must warn that it does not replace 100/911');
    assert.equal(termsRes.has48Hours, true, 'Must note 48h expiration for invitations');
    assert.equal(termsRes.hasNoPlaceholders, true, 'Must NOT contain [Completar]');
    assert.equal(termsRes.hasNoINRI, true, 'Must NOT mention INRI Servicios Digitales');
    assert.equal(termsRes.hasOverflow, false, `Mobile view must not overflow horizontally (${termsRes.scrollWidth} > ${termsRes.innerWidth})`);

    // 7. Navigate to Dashboard (/) and verify Gestión de accesos (#view-invitaciones)
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 1280,
      height: 800,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await cdp.send('Page.navigate', { url: `http://127.0.0.1:${port}/` });
    await new Promise((r) => setTimeout(r, 350));

    // Activate Gestión de accesos view
    await cdp.send('Runtime.evaluate', {
      expression: `document.querySelector('aside .primary-nav button[data-view="Invitaciones"]').click()`,
    });
    await new Promise((r) => setTimeout(r, 250));

    const accessViewCheck = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const view = document.querySelector('#view-invitaciones');
        const reqRows = Array.from(document.querySelectorAll('#access-requests-tbody tr'));
        const invRows = Array.from(document.querySelectorAll('#access-invitations-tbody tr'));
        const reissueButtons = Array.from(document.querySelectorAll('#access-invitations-tbody button[data-action="reissue-invitation"]'));
        return {
          viewHidden: view.hidden,
          pageTitle: document.querySelector('#page-title').textContent.trim(),
          reqCountBadge: document.querySelector('#access-requests-count').textContent.trim(),
          invCountBadge: document.querySelector('#access-invitations-count').textContent.trim(),
          reqRowTexts: reqRows.map((r) => r.innerText),
          invRowCount: invRows.length,
          reissueBtnCount: reissueButtons.length,
          reissueTargetReqId: reissueButtons[0] ? reissueButtons[0].dataset.requestId : null,
          hasFictitiousEmails: view.innerHTML.includes('j.martinez@bomberos.gob.ar') || view.innerHTML.includes('r.sosa@bomberos.gob.ar'),
        };
      })()`,
      returnByValue: true,
    });

    const acc = accessViewCheck.result.value;
    assert.equal(acc.viewHidden, false, 'Gestión de accesos view must be visible');
    assert.equal(acc.pageTitle, 'Gestión de accesos');
    assert.equal(acc.reqCountBadge, '1');
    assert.equal(acc.invCountBadge, '2');
    assert.equal(acc.hasFictitiousEmails, false, 'Zero fictitious emails allowed');
    assert.ok(acc.reqRowTexts[0].includes('solicitante.real@bomberos.gob.ar'));
    assert.equal(acc.reissueBtnCount, 1, 'Only the invitation with can_reissue === true must render Reemitir button');
    assert.equal(acc.reissueTargetReqId, '401');

    // Test failure handling: when review fails (503), no success message is shown and error state is displayed
    setMockFailReview(true);
    await cdp.send('Runtime.evaluate', {
      expression: `document.querySelector('#access-requests-tbody button[data-action="approve-request"]').click()`,
    });
    await new Promise((r) => setTimeout(r, 200));

    const failureCheck = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const banner = document.querySelector('#access-feedback-banner');
        const toast = document.querySelector('#toast');
        return {
          bannerHidden: banner.hidden,
          bannerState: banner.dataset.state,
          bannerText: banner.textContent,
          toastText: toast.textContent,
        };
      })()`,
      returnByValue: true,
    });

    assert.equal(failureCheck.result.value.bannerHidden, false);
    assert.equal(failureCheck.result.value.bannerState, 'error');
    assert.ok(failureCheck.result.value.bannerText.includes('No se pudo enviar el correo'));
    assert.ok(!failureCheck.result.value.toastText.includes('Solicitud aprobada'));

    // Test success handling: when review succeeds (200), request disappears from pending and appears in invitations
    setMockFailReview(false);
    await cdp.send('Runtime.evaluate', {
      expression: `document.querySelector('#access-requests-tbody button[data-action="approve-request"]').click()`,
    });
    await new Promise((r) => setTimeout(r, 250));

    const successCheck = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const banner = document.querySelector('#access-feedback-banner');
        return {
          bannerState: banner.dataset.state,
          reqCountBadge: document.querySelector('#access-requests-count').textContent.trim(),
          invCountBadge: document.querySelector('#access-invitations-count').textContent.trim(),
          reqBodyText: document.querySelector('#access-requests-tbody').innerText,
        };
      })()`,
      returnByValue: true,
    });

    assert.equal(successCheck.result.value.bannerState, 'success');
    assert.equal(successCheck.result.value.reqCountBadge, '0');
    assert.equal(successCheck.result.value.invCountBadge, '3');
    assert.ok(successCheck.result.value.reqBodyText.includes('No hay solicitudes pendientes'));

    // 8. Navigate to /solicitudes and verify redirect opens Dashboard -> Gestión de accesos -> Solicitudes pendientes
    await cdp.send('Page.navigate', { url: `http://127.0.0.1:${port}/solicitudes` });
    await new Promise((r) => setTimeout(r, 350));

    const solicitudesRedirectCheck = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const invView = document.querySelector('#view-invitaciones');
        const dashView = document.querySelector('#view-inventario-general');
        const tabReq = document.querySelector('#tab-access-requests');
        const panelReq = document.querySelector('#panel-access-requests');
        const panelInv = document.querySelector('#panel-access-invitations');
        return {
          pathname: window.location.pathname,
          search: window.location.search,
          pageTitle: document.querySelector('#page-title').textContent.trim(),
          invViewHidden: invView.hidden,
          dashViewHidden: dashView.hidden,
          tabReqSelected: tabReq.getAttribute('aria-selected'),
          panelReqHidden: panelReq.hidden,
          panelInvHidden: panelInv.hidden,
        };
      })()`,
      returnByValue: true,
    });

    const solRes = solicitudesRedirectCheck.result.value;
    assert.equal(solRes.pathname, '/');
    assert.equal(solRes.search, '?view=Invitaciones&tab=requests');
    assert.equal(solRes.pageTitle, 'Gestión de accesos');
    assert.equal(solRes.invViewHidden, false, '/solicitudes redirect must open #view-invitaciones');
    assert.equal(solRes.dashViewHidden, true, 'Dashboard overview must be hidden when opening Gestión de accesos');
    assert.equal(solRes.tabReqSelected, 'true', 'Solicitudes pendientes tab must be automatically selected');
    assert.equal(solRes.panelReqHidden, false, 'Solicitudes pendientes panel must be visible');
    assert.equal(solRes.panelInvHidden, true, 'Invitaciones emitidas panel must be hidden');

    cdp.ws.close();
  } finally {
    chromeProcess.kill('SIGKILL');
    await new Promise((resolve) => server.close(resolve));
  }
});
