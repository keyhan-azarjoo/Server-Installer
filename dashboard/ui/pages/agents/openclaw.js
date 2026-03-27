(() => {
  var ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["agent-openclaw"] = function renderOpenClawPage(p) {
    var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
    var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
    var Box = p.Box, Paper = p.Paper, Chip = p.Chip, Alert = p.Alert, Tooltip = p.Tooltip;
    var ActionCard = p.ActionCard;
    var cfg = p.cfg, run = p.run, selectableIps = p.selectableIps, serviceBusy = p.serviceBusy;
    var isScopeLoading = p.isScopeLoading, scopeErrors = p.scopeErrors;
    var isServiceRunningStatus = p.isServiceRunningStatus, onServiceAction = p.onServiceAction;
    var renderServiceUrls = p.renderServiceUrls, renderServicePorts = p.renderServicePorts;
    var renderServiceStatus = p.renderServiceStatus, renderFolderIcon = p.renderFolderIcon;
    var setPage = p.setPage, copyText = p.copyText;

    var ocInfo = p.openclawService || {};
    var services = p.openclawPageServices || [];
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

    var installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : "macOS");
    var commonFields = [
      { name: "OPENCLAW_HOST_IP", label: "Host IP", type: "select", options: selectableIps, defaultValue: selectableIps[0] || "", required: true, placeholder: "Select IP" },
      { name: "OPENCLAW_HTTP_PORT", label: "Web UI HTTP Port", defaultValue: httpPort || "8088", checkPort: true, placeholder: "Leave empty for CLI only" },
      { name: "OPENCLAW_HTTPS_PORT", label: "Web UI HTTPS Port", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty to skip HTTPS" },
      { name: "OPENCLAW_DOMAIN", label: "Domain (optional)", defaultValue: "", placeholder: "e.g. openclaw.example.com" },
      { name: "OPENCLAW_USERNAME", label: "Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "OPENCLAW_PASSWORD", label: "Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
    ];

    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#dc2626" }}>OpenClaw — AI Agent Framework</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Open-source AI agent framework with tool use, memory, planning, and self-reflection.
                Modular plugin architecture supports custom tools, multiple LLM backends, and persistent memory.
                Includes a web UI for running agent tasks remotely.
              </Typography>
              <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                OpenClaw requires an LLM backend (Ollama, OpenAI API, or Claude API). Install Ollama first for fully local operation.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* API Docs */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #dc262644", background: "linear-gradient(135deg, #dc262605 0%, #ffffff 100%)" }}>
            <CardContent sx={{ py: 2, "&:last-child": { pb: 2 } }}>
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <Box sx={{ width: 6, height: 36, borderRadius: 3, bgcolor: "#dc2626" }} />
                <Box sx={{ flexGrow: 1 }}>
                  <Typography variant="h6" fontWeight={800} sx={{ color: "#dc2626" }}>OpenClaw API Documentation</Typography>
                  <Typography variant="caption" color="text.secondary">Run tasks, manage plugins, stream output</Typography>
                </Box>
                <Chip label="6 endpoints" size="small" sx={{ bgcolor: "#dc262615", color: "#dc2626", fontWeight: 700, border: "1px solid #dc262633" }} />
                <Button variant="contained" size="small" onClick={function() { setPage("agent-openclaw-api"); }}
                  sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, bgcolor: "#dc2626", "&:hover": { bgcolor: "#b91c1c" }, px: 3 }}>
                  API Documents
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Install */}
        <Grid item xs={12} md={6}>
          <ActionCard
            title={"Install OpenClaw \u2014 OS (" + installOsLabel + ")"}
            description="Install OpenClaw with web UI. Sets up Python venv, installs openclaw package, and starts web server on selected port."
            action={cfg.os === "windows" ? "/run/openclaw_windows_os" : "/run/openclaw_unix_os"}
            fields={commonFields} onRun={run} color="#dc2626"
          />
        </Grid>

        {/* Status */}
        <Grid item xs={12} md={6}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: "#dc2626" }}>OpenClaw Status</Typography>
              <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
              {installed && <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>}
              {installed && displayHost && <Typography variant="body2">Host: <b>{displayHost}</b></Typography>}
              {installed && httpPort && <Typography variant="body2">Port: <b>{httpPort}</b></Typography>}
              {computedHttpUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>HTTP: <a href={computedHttpUrl} target="_blank" rel="noopener">{computedHttpUrl}</a></Typography>}
              {computedHttpsUrl && <Typography variant="body2" sx={{ wordBreak: "break-all" }}>HTTPS: <a href={computedHttpsUrl} target="_blank" rel="noopener">{computedHttpsUrl}</a></Typography>}
              {bestUrl && (
                <Button variant="contained" size="small" sx={{ mt: 1.5, textTransform: "none", bgcolor: "#dc2626", "&:hover": { bgcolor: "#b91c1c" } }}
                  onClick={function() { window.open(bestUrl, "_blank"); }}>Open OpenClaw</Button>
              )}
              <Box sx={{ mt: 2, pt: 1.5, borderTop: "1px solid #e8edf6" }}>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Button variant="outlined" size="small" href="https://github.com/openclaw-ai/openclaw" target="_blank" rel="noopener" sx={{ textTransform: "none", borderRadius: 2, fontWeight: 600, borderColor: "#dc262644", color: "#dc2626" }}>GitHub</Button>
                  <Button variant="outlined" size="small" href="https://pypi.org/project/openclaw/" target="_blank" rel="noopener" sx={{ textTransform: "none", borderRadius: 2, fontWeight: 600, borderColor: "#dc262644", color: "#dc2626" }}>PyPI</Button>
                  <Button variant="outlined" size="small" href="https://openclaw-ai.github.io/openclaw/" target="_blank" rel="noopener" sx={{ textTransform: "none", borderRadius: 2, fontWeight: 600, borderColor: "#dc262644", color: "#dc2626" }}>Documentation</Button>
                </Stack>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Services */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6" fontWeight={800}>OpenClaw Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                {bestUrl && running && <Button variant="contained" size="small" onClick={function(){ window.open(bestUrl, "_blank"); }} sx={{ textTransform: "none", bgcolor: "#dc2626" }}>Open</Button>}
                <Button variant="outlined" sx={{ textTransform: "none" }}>Refresh</Button>
              </Stack>
              {services.length === 0 && <Typography variant="body2" color="text.secondary">No OpenClaw services deployed yet.</Typography>}
              {services.map(function(svc) {
                var svcRunning = isServiceRunningStatus(svc.status, svc.sub_status);
                return (
                  <Paper key={"oc-" + (svc.kind || "") + "-" + svc.name} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}><Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>{renderServiceUrls(svc)}{renderServicePorts(svc)}</Box>
                      {renderServiceStatus(svc)}<Box sx={{ flexGrow: 1 }} />{renderFolderIcon(svc)}
                      <Button size="small" variant="outlined" color={svcRunning ? "error" : "success"} disabled={serviceBusy} onClick={function(){ onServiceAction(svcRunning ? "stop" : "start", svc); }} sx={{ textTransform: "none" }}>{svcRunning ? "Stop" : "Start"}</Button>
                      <Button size="small" variant="outlined" disabled={serviceBusy} onClick={function(){ onServiceAction("restart", svc); }} sx={{ textTransform: "none" }}>Restart</Button>
                      <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={function(){ onServiceAction("delete", svc); }} sx={{ textTransform: "none" }}>Delete</Button>
                    </Stack>
                  </Paper>
                );
              })}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  // ── OpenClaw API Docs Page ──────────────────────────────────────────────────
  ns.pages["agent-openclaw-api"] = function renderOpenClawApiPage(p) {
    var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
    var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
    var Box = p.Box, Paper = p.Paper, Chip = p.Chip, Tooltip = p.Tooltip, Alert = p.Alert;
    var setPage = p.setPage, copyText = p.copyText;
    var ocInfo = p.openclawService || {};
    var host = String(ocInfo.host || "").trim();
    var urlHost = (host && host !== "0.0.0.0") ? host : "{host}";
    var httpPort = String(ocInfo.http_port || "8088").trim();
    var httpsPort = String(ocInfo.https_port || "").trim();
    var httpBase = "http://" + urlHost + ":" + httpPort;
    var httpsBase = httpsPort ? "https://" + urlHost + ":" + httpsPort : "";

    var MC = { GET: { bg: "#dcfce7", c: "#166534", b: "#86efac" }, POST: { bg: "#dbeafe", c: "#1e40af", b: "#93c5fd" } };
    var mc = function(m) { return MC[m] || { bg: "#f3f4f6", c: "#374151", b: "#d1d5db" }; };
    var doCopy = function(text) { if (copyText) copyText(text, "cURL"); };

    var sections = [
      { name: "Agent Tasks", color: "#dc2626", eps: [
        { m: "POST", p: "/api/run", d: "Run an agent task. The agent will plan and execute steps to complete the task.", body: '{\n  "task": "List all Python files in the current directory"\n}', res: '{\n  "ok": true,\n  "output": "found 5 Python files:\\n  app.py\\n  ...",\n  "error": ""\n}' },
        { m: "POST", p: "/api/run/stream", d: "Run a task with streaming output (SSE). Each line of agent output is streamed in real-time.", body: '{\n  "task": "Create a hello world Flask app"\n}', res: 'text/event-stream:\\n  data: {"line": "Planning task..."}\n  data: {"line": "Creating app.py..."}\n  data: {"done": true, "exit_code": 0}' },
      ]},
      { name: "Management", color: "#059669", eps: [
        { m: "GET", p: "/api/plugins", d: "List available OpenClaw plugins.", res: '{\n  "ok": true,\n  "output": "web_search\\nfile_manager\\ncode_runner"\n}' },
        { m: "GET", p: "/api/config", d: "Show current OpenClaw configuration.", res: '{\n  "ok": true,\n  "output": "llm_backend: ollama\\nmodel: llama3.2"\n}' },
      ]},
      { name: "Health", color: "#b45309", eps: [
        { m: "GET", p: "/api/health", d: "Health check — shows status and version.", res: '{\n  "ok": true,\n  "status": "healthy",\n  "version": "2026.3.20"\n}' },
        { m: "GET", p: "/api/version", d: "Get OpenClaw version.", res: '{\n  "ok": true,\n  "version": "2026.3.20"\n}' },
      ]},
    ];

    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #dc262644" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
                <Button variant="outlined" size="small" onClick={function(){ setPage("agent-openclaw"); }} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, borderColor: "#dc2626", color: "#dc2626" }}>Back to OpenClaw</Button>
                <Typography variant="h5" fontWeight={900} sx={{ color: "#dc2626", flexGrow: 1 }}>OpenClaw API Documentation</Typography>
              </Stack>
              <Alert severity="info" sx={{ borderRadius: 2, mt: 1 }}>
                <b>HTTP:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpBase}</code>
                {httpsBase && <span><br/><b>HTTPS:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpsBase}</code></span>}
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
                    <Typography variant="h6" fontWeight={800} sx={{ color: sec.color, flexGrow: 1 }}>{sec.name}</Typography>
                    <Chip label={sec.eps.length + " endpoints"} size="small" variant="outlined" sx={{ fontSize: 10, height: 20 }} />
                  </Stack>
                  {sec.eps.map(function(ep, ei) {
                    var cl = mc(ep.m);
                    return (
                      <Paper key={ei} variant="outlined" sx={{ p: 2, mb: 1.5, borderRadius: 2, "&:hover": { borderColor: sec.color + "66" } }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "flex-start", md: "center" }}>
                          <Chip label={ep.m} size="small" sx={{ bgcolor: cl.bg, color: cl.c, border: "1px solid " + cl.b, fontWeight: 800, fontFamily: "monospace", minWidth: 70, justifyContent: "center" }} />
                          <Box sx={{ flexGrow: 1 }}>
                            <Typography sx={{ fontFamily: "monospace", fontWeight: 600, wordBreak: "break-all", fontSize: 14 }}>{httpBase + ep.p}</Typography>
                            {httpsBase && <Typography sx={{ fontFamily: "monospace", fontWeight: 600, wordBreak: "break-all", fontSize: 13, color: "#059669", mt: 0.3 }}>{httpsBase + ep.p}</Typography>}
                          </Box>
                          <Tooltip title="Copy cURL"><Button size="small" variant="outlined" onClick={function(){ doCopy("curl -X " + ep.m + " \"" + httpBase + ep.p + "\""); }} sx={{ textTransform: "none", minWidth: 0, px: 1.5, fontSize: 11, borderColor: "#e2e8f0" }}>cURL</Button></Tooltip>
                        </Stack>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{ep.d}</Typography>
                        {ep.body && <Box sx={{ mt: 1.5 }}><Typography variant="caption" fontWeight={700} sx={{ color: "#475569" }}>Request Body:</Typography><Paper elevation={0} sx={{ mt: 0.3, p: 1.5, bgcolor: "#f8fafc", borderRadius: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", border: "1px solid #e2e8f0", lineHeight: 1.7 }}>{ep.body}</Paper></Box>}
                        {ep.res && <Box sx={{ mt: 1.5 }}><Typography variant="caption" fontWeight={700} sx={{ color: "#475569" }}>Response:</Typography><Paper elevation={0} sx={{ mt: 0.3, p: 1.5, bgcolor: "#f0fdf4", borderRadius: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", border: "1px solid #dcfce7", lineHeight: 1.7 }}>{ep.res}</Paper></Box>}
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
