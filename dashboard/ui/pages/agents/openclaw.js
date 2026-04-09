(() => {
  var ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  function OpenClawTerminal(props) {
    var Box = MaterialUI.Box;
    var cwd = props.cwd;
    var queuedInput = props.queuedInput;
    var queuedInputKey = props.queuedInputKey;
    var onStatusChange = props.onStatusChange;

    var containerRef = React.useRef(null);
    var termRef = React.useRef(null);
    var wsRef = React.useRef(null);
    var fitRef = React.useRef(null);
    var lastSentKeyRef = React.useRef(0);
    var pendingInputRef = React.useRef("");
    var pendingInputKeyRef = React.useRef(0);

    React.useEffect(function() {
      pendingInputRef.current = queuedInput || "";
      pendingInputKeyRef.current = queuedInputKey || 0;
    }, [queuedInput, queuedInputKey]);

    React.useEffect(function() {
      var el = containerRef.current;
      if (!el) return;

      var T = window.Terminal;
      if (!T) {
        el.style.cssText = "display:flex;align-items:center;justify-content:center;background:#0d1117;color:#c9d1d9;font-family:monospace;font-size:13px;padding:24px;";
        el.textContent = "Terminal unavailable: xterm.js could not be loaded.";
        if (onStatusChange) onStatusChange("Unavailable");
        return;
      }

      var term = new T({
        cursorBlink: true,
        convertEol: true,
        fontFamily: "'Cascadia Code', 'Fira Code', Consolas, 'Courier New', monospace",
        fontSize: 13,
        theme: {
          background: "#0d1117",
          foreground: "#c9d1d9",
          cursor: "#f0f6fc",
          selectionBackground: "#264f78",
          black: "#0d1117",
          red: "#ff7b72",
          green: "#3fb950",
          yellow: "#d29922",
          blue: "#58a6ff",
          magenta: "#d2a8ff",
          cyan: "#39c5cf",
          white: "#c9d1d9",
          brightBlack: "#8b949e",
          brightRed: "#ffa198",
          brightGreen: "#56d364",
          brightYellow: "#e3b341",
          brightBlue: "#79c0ff",
          brightMagenta: "#d2a8ff",
          brightCyan: "#56d4dd",
          brightWhite: "#f0f6fc",
        },
      });
      var FA = window.FitAddon;
      var fitAddon = null;
      if (FA && FA.FitAddon) {
        fitAddon = new FA.FitAddon();
        term.loadAddon(fitAddon);
      }
      term.open(el);
      if (fitAddon) {
        try { fitAddon.fit(); } catch (_) {}
      }
      term.focus();
      termRef.current = term;
      fitRef.current = fitAddon;

      var proto = location.protocol === "https:" ? "wss:" : "ws:";
      var cols = term.cols || 80;
      var rows = term.rows || 24;
      var ws = new WebSocket(proto + "//" + location.host + "/ws/pty?cwd=" + encodeURIComponent(cwd || "") + "&cols=" + cols + "&rows=" + rows);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      if (onStatusChange) onStatusChange("Connecting");

      ws.onopen = function() {
        if (fitAddon) {
          try { fitAddon.fit(); } catch (_) {}
        }
        if (onStatusChange) onStatusChange("Connected");
        if (pendingInputRef.current && pendingInputKeyRef.current && pendingInputKeyRef.current !== lastSentKeyRef.current) {
          lastSentKeyRef.current = pendingInputKeyRef.current;
          ws.send(pendingInputRef.current);
        }
        term.focus();
      };
      ws.onmessage = function(e) {
        if (e.data instanceof ArrayBuffer) term.write(new Uint8Array(e.data));
        else term.write(e.data);
      };
      ws.onclose = function() {
        term.write("\r\n\x1b[33m[Terminal disconnected]\x1b[0m\r\n");
        if (onStatusChange) onStatusChange("Disconnected");
      };
      ws.onerror = function() {
        term.write("\r\n\x1b[31m[Connection failed]\x1b[0m\r\n");
        if (onStatusChange) onStatusChange("Error");
      };

      term.onData(function(data) {
        if (ws.readyState === WebSocket.OPEN) ws.send(data);
      });

      var sendResize = function() {
        if (fitAddon) {
          try { fitAddon.fit(); } catch (_) {}
        }
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
        }
      };
      var observer = new ResizeObserver(sendResize);
      observer.observe(el);

      return function() {
        observer.disconnect();
        try { ws.close(); } catch (_) {}
        try { term.dispose(); } catch (_) {}
        termRef.current = null;
        wsRef.current = null;
        fitRef.current = null;
      };
    }, [cwd, onStatusChange]);

    React.useEffect(function() {
      if (!queuedInput || !queuedInputKey || queuedInputKey === lastSentKeyRef.current) return;
      var ws = wsRef.current;
      var term = termRef.current;
      if (!ws || !term) return;
      if (ws.readyState !== WebSocket.OPEN) return;
      lastSentKeyRef.current = queuedInputKey;
      ws.send(queuedInput);
      term.focus();
    }, [queuedInput, queuedInputKey]);

    return (
      <Box ref={containerRef} sx={{
        width: "100%",
        minHeight: 420,
        height: { xs: 420, md: 520 },
        flexGrow: 1,
        bgcolor: "#0d1117",
        overflow: "hidden",
        borderRadius: 2,
        "& .xterm": { height: "100%", padding: "8px" },
        "& .xterm-viewport": { overflowY: "auto !important" },
        "& .xterm-screen": { cursor: "text" },
      }} />
    );
  }

  ns.pages["agent-openclaw"] = function renderOpenClawPage(p) {
    var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
    var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
    var Box = p.Box, Paper = p.Paper, Chip = p.Chip;
    var cfg = p.cfg, run = p.run, serviceBusy = p.serviceBusy;
    var isServiceRunningStatus = p.isServiceRunningStatus, onServiceAction = p.onServiceAction;
    var renderServiceUrls = p.renderServiceUrls;
    var setPage = p.setPage, copyText = p.copyText;

    var ocInfo = p.openclawService || {};
    var ollamaInfo = p.ollamaService || {};
    var lmsInfo = p.lmstudioService || {};
    var services = p.openclawPageServices || [];
    var primaryService = services[0] || { name: String(ocInfo.service_name || "serverinstaller-openclaw").trim() || "serverinstaller-openclaw" };
    var httpUrl = String(ocInfo.http_url || "").trim();
    var httpsUrl = String(ocInfo.https_url || "").trim();
    var httpPort = String(ocInfo.http_port || "").trim();
    var httpsPort = String(ocInfo.https_port || "").trim();
    var hostIp = String(ocInfo.host || "").trim();
    var installed = !!ocInfo.installed;
    var running = !!ocInfo.running;
    var displayHost = (hostIp && hostIp !== "0.0.0.0" && hostIp !== "*") ? hostIp : "";
    var computedHttpUrl = installed && displayHost && httpPort ? "http://" + displayHost + ":" + httpPort : (installed ? httpUrl : "");
    var computedHttpsUrl = installed && displayHost && httpsPort ? "https://" + displayHost + ":" + httpsPort : (installed ? httpsUrl : "");
    var bestUrl = computedHttpsUrl || computedHttpUrl;
    var gatewayToken = String(ocInfo.gateway_token || "").trim();
    var gatewayWsUrl = "";
    if (displayHost && httpsPort) gatewayWsUrl = "wss://" + displayHost + ":" + httpsPort;
    else if (displayHost && httpPort) gatewayWsUrl = "ws://" + displayHost + ":" + httpPort;
    var tokenizedBestUrl = bestUrl;
    if (bestUrl && gatewayToken) {
      var gatewayUrlParam = gatewayWsUrl ? ("?gatewayUrl=" + encodeURIComponent(gatewayWsUrl)) : "";
      tokenizedBestUrl = bestUrl + gatewayUrlParam + "#token=" + encodeURIComponent(gatewayToken);
    }

    var installScriptCommand = cfg.os === "windows"
      ? "powershell -c \"irm https://openclaw.ai/install.ps1 | iex\"\r"
      : "curl -fsSL https://openclaw.ai/install.sh | bash\n";
    var installCwd = String(ocInfo.install_dir || "").trim();
    var _terminalStatus = React.useState("Connecting");
    var terminalStatus = _terminalStatus[0], setTerminalStatus = _terminalStatus[1];
    var _queuedInput = React.useState("");
    var queuedInput = _queuedInput[0], setQueuedInput = _queuedInput[1];
    var _queuedInputKey = React.useState(0);
    var queuedInputKey = _queuedInputKey[0], setQueuedInputKey = _queuedInputKey[1];
    var actionFormRef = React.useRef(null);

    var startInstall = function() {
      setQueuedInput(installScriptCommand);
      setQueuedInputKey(Date.now());
    };

    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", overflow: "hidden" }}>
            <CardContent>
              <Stack direction={{ xs: "column", sm: "row" }} alignItems={{ xs: "stretch", sm: "center" }} spacing={1.5} sx={{ mb: 2 }}>
                <Box sx={{ flexGrow: 1 }}>
                  <Typography variant="h6" fontWeight={800} sx={{ color: "#dc2626" }}>OpenClaw Install</Typography>
                  <Typography variant="body2" color="text.secondary">This is a real terminal. Click Start, then type, press Enter, and answer prompts directly in the shell.</Typography>
                </Box>
                <Chip label={terminalStatus} size="small" sx={{ alignSelf: { xs: "flex-start", sm: "center" }, bgcolor: "#fee2e2", color: "#991b1b", fontWeight: 700 }} />
              </Stack>
              <Box component="form" ref={actionFormRef}>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 2 }}>
                  <Button variant="contained" onClick={startInstall}
                    sx={{ textTransform: "none", bgcolor: "#dc2626", "&:hover": { bgcolor: "#b91c1c" }, fontWeight: 700, px: 3 }}>
                    Start
                  </Button>
                  <Button variant="outlined" onClick={function() { if (copyText) copyText(installScriptCommand.trim(), "Command"); }}
                    sx={{ textTransform: "none", fontWeight: 700 }}>
                    Copy Command
                  </Button>
                </Stack>
              </Box>
              <Paper elevation={0} sx={{ p: 1.5, mb: 2, bgcolor: "#f8fafc", borderRadius: 2, border: "1px solid #e2e8f0" }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>Command</Typography>
                <Typography variant="body2" sx={{ fontFamily: "'Cascadia Code', 'Fira Code', monospace", fontSize: 12, wordBreak: "break-all" }}>
                  {installScriptCommand.trim()}
                </Typography>
              </Paper>
              <Paper elevation={0} sx={{ bgcolor: "#0d1117", borderRadius: 2, border: "1px solid #30363d", overflow: "hidden" }}>
                <OpenClawTerminal
                  cwd={installCwd}
                  queuedInput={queuedInput}
                  queuedInputKey={queuedInputKey}
                  onStatusChange={setTerminalStatus}
                />
              </Paper>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #dc262644" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 2, color: "#dc2626" }}>Connection & Status</Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>Service Status</Typography>
                  <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
                  {installed && <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>}
                  {installed && displayHost && <Typography variant="body2">Host: <b>{displayHost}</b></Typography>}
                  {installed && httpPort && <Typography variant="body2">Port: <b>{httpPort}</b></Typography>}
                  <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
                    {bestUrl && <Button variant="contained" size="small" onClick={function() { window.open(tokenizedBestUrl || bestUrl, "_blank"); }} sx={{ textTransform: "none", bgcolor: "#dc2626", "&:hover": { bgcolor: "#b91c1c" }, fontSize: 12 }}>Open Dashboard</Button>}
                    {installed && <Button variant="outlined" size="small" disabled={serviceBusy} onClick={function() { onServiceAction(running ? "stop" : "start", primaryService); }} sx={{ textTransform: "none", fontSize: 12 }}>{running ? "Stop" : "Start"}</Button>}
                    {installed && <Button variant="outlined" size="small" color="error" disabled={serviceBusy} onClick={function() {
                      if (!window.confirm("Are you sure you want to completely uninstall OpenClaw?\n\nThis action cannot be undone.")) return;
                      run({ preventDefault: function() {}, currentTarget: actionFormRef.current, target: actionFormRef.current }, "/run/openclaw_delete", "Uninstall OpenClaw", actionFormRef.current);
                    }} sx={{ textTransform: "none", fontSize: 12 }}>Uninstall</Button>}
                  </Stack>
                </Grid>

                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>Gateway Connection</Typography>
                  {installed && displayHost && httpPort ? (
                    <Box>
                      <Typography variant="body2" sx={{ mb: 0.5 }}>WebSocket URL:</Typography>
                      <Paper elevation={0} sx={{ p: 1, bgcolor: "#f8fafc", borderRadius: 1, fontFamily: "monospace", fontSize: 12, border: "1px solid #e2e8f0", wordBreak: "break-all", mb: 1 }}>
                        {gatewayWsUrl || "Waiting for gateway URL..."}
                      </Paper>
                      <Typography variant="body2" sx={{ mb: 0.5 }}>Gateway Token:</Typography>
                      <Paper elevation={0} sx={{ p: 1, bgcolor: "#f8fafc", borderRadius: 1, fontFamily: "monospace", fontSize: 12, border: "1px solid #e2e8f0", mb: 1 }}>
                        {gatewayToken || "Open the tokenized dashboard URL once to initialize session auth."}
                      </Paper>
                      <Typography variant="body2" sx={{ mb: 0.5 }}>Dashboard URL:</Typography>
                      <Paper elevation={0} sx={{ p: 1, bgcolor: "#f0fdf4", borderRadius: 1, fontFamily: "monospace", fontSize: 11, border: "1px solid #dcfce7", wordBreak: "break-all", cursor: "pointer" }}
                        onClick={function() { if (tokenizedBestUrl && copyText) copyText(tokenizedBestUrl, "URL"); }}>
                        {tokenizedBestUrl || (bestUrl || "Waiting for installer to save gateway token...")}
                      </Paper>
                    </Box>
                  ) : (
                    <Typography variant="body2" color="text.secondary">Install OpenClaw first to see connection details.</Typography>
                  )}
                </Grid>

                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>LLM Backends</Typography>
                  <Paper variant="outlined" sx={{ p: 1.5, mb: 1, borderRadius: 2, borderColor: ollamaInfo.running ? "#16a34a55" : "#e2e8f0" }}>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Typography variant="body2" fontWeight={700}>Ollama</Typography>
                      <Chip size="small" label={ollamaInfo.running ? "Running" : ollamaInfo.installed ? "Installed" : "Not installed"}
                        color={ollamaInfo.running ? "success" : ollamaInfo.installed ? "warning" : "default"} sx={{ fontSize: 10, height: 18 }} />
                    </Stack>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                      {String(ollamaInfo.api_url || ollamaInfo.https_url || ollamaInfo.http_url || "").trim() || "Install from AI/ML > Ollama"}
                    </Typography>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, borderColor: lmsInfo.running ? "#16a34a55" : "#e2e8f0" }}>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Typography variant="body2" fontWeight={700}>LM Studio</Typography>
                      <Chip size="small" label={lmsInfo.running ? "Running" : lmsInfo.installed ? "Installed" : "Not installed"}
                        color={lmsInfo.running ? "success" : lmsInfo.installed ? "warning" : "default"} sx={{ fontSize: 10, height: 18 }} />
                    </Stack>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                      {String(lmsInfo.api_url || lmsInfo.https_url || lmsInfo.http_url || "").trim() || "Install from AI/ML > LM Studio"}
                    </Typography>
                  </Paper>
                </Grid>
              </Grid>

              {services.length > 0 && (
                <Stack spacing={1} sx={{ mt: 2, pt: 2, borderTop: "1px solid #e8edf6" }}>
                  <Typography variant="subtitle2" fontWeight={700}>Services</Typography>
                  {services.map(function(svc) {
                    var svcRunning = isServiceRunningStatus(svc.status, svc.sub_status);
                    return (
                      <Paper key={"oc-" + svc.name} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                        <Typography variant="body2" fontWeight={700}>{svc.display_name || svc.name}</Typography>
                        <Typography variant="caption" color="text.secondary">{svc.kind} | {svc.status}</Typography>
                        {renderServiceUrls(svc)}
                        <Stack direction="row" spacing={0.5} sx={{ mt: 1 }}>
                          <Button size="small" variant="outlined" color={svcRunning ? "error" : "success"} disabled={serviceBusy} onClick={function() { onServiceAction(svcRunning ? "stop" : "start", svc); }} sx={{ textTransform: "none", fontSize: 11, py: 0.3 }}>{svcRunning ? "Stop" : "Start"}</Button>
                          <Button size="small" variant="outlined" disabled={serviceBusy} onClick={function() { onServiceAction("restart", svc); }} sx={{ textTransform: "none", fontSize: 11, py: 0.3 }}>Restart</Button>
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={function() { onServiceAction("delete", svc); }} sx={{ textTransform: "none", fontSize: 11, py: 0.3 }}>Delete</Button>
                        </Stack>
                      </Paper>
                    );
                  })}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #dc262644", background: "linear-gradient(135deg, #dc262605 0%, #ffffff 100%)" }}>
            <CardContent sx={{ py: 2, "&:last-child": { pb: 2 } }}>
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <Box sx={{ width: 6, height: 36, borderRadius: 3, bgcolor: "#dc2626" }} />
                <Box sx={{ flexGrow: 1 }}>
                  <Typography variant="h6" fontWeight={800} sx={{ color: "#dc2626" }}>OpenClaw API Documentation</Typography>
                  <Typography variant="caption" color="text.secondary">Gateway WebSocket API, REST endpoints</Typography>
                </Box>
                <Button variant="contained" size="small" onClick={function() { setPage("agent-openclaw-api"); }}
                  sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, bgcolor: "#dc2626", "&:hover": { bgcolor: "#b91c1c" }, px: 3 }}>
                  API Documents
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  ns.pages["agent-openclaw-api"] = function renderOpenClawApiPage(p) {
    var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
    var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
    var Box = p.Box, Paper = p.Paper, Chip = p.Chip, Alert = p.Alert;
    var setPage = p.setPage;
    var ocInfo = p.openclawService || {};
    var host = String(ocInfo.host || "").trim();
    var urlHost = (host && host !== "0.0.0.0") ? host : "{host}";
    var httpPort = String(ocInfo.http_port || "18789").trim();
    var httpsPort = String(ocInfo.https_port || "").trim();
    var httpBase = "http://" + urlHost + ":" + httpPort;
    var httpsBase = httpsPort ? "https://" + urlHost + ":" + httpsPort : "";

    var MC = { GET: { bg: "#dcfce7", c: "#166534", b: "#86efac" }, POST: { bg: "#dbeafe", c: "#1e40af", b: "#93c5fd" } };
    var mc = function(m) { return MC[m] || { bg: "#f3f4f6", c: "#374151", b: "#d1d5db" }; };

    var sections = [
      { name: "Gateway", color: "#dc2626", eps: [
        { m: "GET", p: "/", d: "OpenClaw Dashboard - the main web interface with WebChat, channels, skills, and configuration." },
        { m: "GET", p: "/api/health", d: "Health check.", res: '{ "ok": true, "status": "healthy" }' },
      ]},
      { name: "WebSocket", color: "#7c3aed", eps: [
        { m: "GET", p: "ws://host:18789", d: "WebSocket gateway - real-time bidirectional communication for chat, events, and tool execution." },
      ]},
      { name: "CLI Commands", color: "#059669", eps: [
        { m: "GET", p: "openclaw gateway --bind lan --port 18789", d: "Start the gateway server on LAN." },
        { m: "GET", p: "openclaw onboard", d: "Interactive onboarding wizard." },
        { m: "GET", p: "openclaw dashboard --no-open", d: "Get the dashboard URL without opening browser." },
        { m: "GET", p: "openclaw models list", d: "List configured LLM models." },
      ]},
    ];

    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #dc262644" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
                <Button variant="outlined" size="small" onClick={function(){ setPage("agent-openclaw"); }} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, borderColor: "#dc2626", color: "#dc2626" }}>Back to OpenClaw</Button>
                <Typography variant="h5" fontWeight={900} sx={{ color: "#dc2626", flexGrow: 1 }}>OpenClaw API & CLI Reference</Typography>
              </Stack>
              <Alert severity="info" sx={{ borderRadius: 2, mt: 1 }}>
                <b>Gateway:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpBase}</code>
                {httpsBase && <span> | <b>HTTPS:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpsBase}</code></span>}
              </Alert>
            </CardContent>
          </Card>
        </Grid>
        {sections.map(function(sec, si) {
          return (
            <Grid item xs={12} key={si}>
              <Card sx={{ borderRadius: 3, border: "1px solid " + sec.color + "33" }}>
                <CardContent>
                  <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                    <Box sx={{ width: 5, height: 28, borderRadius: 3, bgcolor: sec.color }} />
                    <Typography variant="h6" fontWeight={800} sx={{ color: sec.color }}>{sec.name}</Typography>
                  </Stack>
                  {sec.eps.map(function(ep, ei) {
                    var cl = mc(ep.m);
                    return (
                      <Paper key={ei} variant="outlined" sx={{ p: 2, mb: 1, borderRadius: 2 }}>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Chip label={ep.m} size="small" sx={{ bgcolor: cl.bg, color: cl.c, border: "1px solid " + cl.b, fontWeight: 800, fontFamily: "monospace" }} />
                          <Typography sx={{ fontFamily: "monospace", fontWeight: 600, fontSize: 13 }}>{ep.p}</Typography>
                        </Stack>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{ep.d}</Typography>
                        {ep.res && <Paper elevation={0} sx={{ mt: 1, p: 1, bgcolor: "#f0fdf4", borderRadius: 1, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", border: "1px solid #dcfce7" }}>{ep.res}</Paper>}
                      </Paper>
                    );
                  })}
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>
    );
  };
})();
