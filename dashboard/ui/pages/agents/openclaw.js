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
    var ollamaInfo = p.ollamaService || {};
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
      { name: "OPENCLAW_HTTP_PORT", label: "Gateway Port (HTTP, for OS install)", defaultValue: httpPort || "18789", checkPort: true, placeholder: "Default: 18789" },
      { name: "OPENCLAW_HTTPS_PORT", label: "HTTPS Port (Docker uses this)", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Default: same as Gateway Port" },
      { name: "OPENCLAW_DOMAIN", label: "Domain (optional)", defaultValue: "", placeholder: "e.g. openclaw.example.com" },
      { name: "OPENCLAW_USERNAME", label: "Dashboard Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "OPENCLAW_PASSWORD", label: "Dashboard Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "OPENCLAW_LLM_PROVIDER", label: "LLM Provider", type: "select", options: ["ollama (local)", "openai", "anthropic"], defaultValue: "ollama (local)", placeholder: "Select LLM" },
      { name: "OPENCLAW_LLM_MODEL", label: "Ollama Model (auto-installed if local)", type: "select", options: ["ministral:3b", "llama3.2:3b", "llama3.2:1b", "mistral:7b", "qwen2.5:3b", "qwen2.5:7b", "gemma2:2b", "phi3:3.8b", "deepseek-r1:1.5b", "deepseek-r1:7b", "codellama:7b", "custom"], defaultValue: "ministral:3b", placeholder: "Select model" },
      { name: "OPENCLAW_LLM_MODEL_CUSTOM", label: "Custom Model Name (if 'custom' selected above)", defaultValue: "", placeholder: "e.g. my-model:latest or any ollama model name" },
      { name: "OPENCLAW_OLLAMA_URL", label: "Ollama Server URL (auto-detected)", defaultValue: (ollamaInfo.https_url || ollamaInfo.http_url || "").trim() || "", placeholder: "Leave empty for local. Or: https://other-server:11436" },
      { name: "OPENCLAW_OPENAI_KEY", label: "OpenAI API Key (if using OpenAI)", type: "password", defaultValue: "", placeholder: "sk-..." },
      { name: "OPENCLAW_ANTHROPIC_KEY", label: "Anthropic API Key (if using Claude)", type: "password", defaultValue: "", placeholder: "sk-ant-..." },
      { name: "OPENCLAW_TELEGRAM_TOKEN", label: "Telegram Bot Token (optional)", defaultValue: "", placeholder: "123456:ABC-DEF... (from @BotFather)" },
      { name: "OPENCLAW_DISCORD_TOKEN", label: "Discord Bot Token (optional)", type: "password", defaultValue: "", placeholder: "From Discord Developer Portal" },
      { name: "OPENCLAW_SLACK_TOKEN", label: "Slack Bot Token (optional)", type: "password", defaultValue: "", placeholder: "xoxb-... (from Slack API)" },
      { name: "OPENCLAW_WHATSAPP_PHONE", label: "WhatsApp Phone Number (optional)", defaultValue: "", placeholder: "+1234567890 (will show QR code)" },
    ];

    var CodeBlock = function(props) {
      return React.createElement(Paper, { elevation: 0, sx: { bgcolor: "#0f172a", borderRadius: 2, p: 2, mt: 0.5, mb: 1.5, position: "relative", overflow: "auto" } },
        React.createElement(Button, { size: "small", onClick: function() { if (copyText) copyText(props.code, "Code"); },
          sx: { position: "absolute", top: 8, right: 8, minWidth: 0, px: 1.5, py: 0.3, color: "#94a3b8", bgcolor: "#1e293b", textTransform: "none", fontSize: 11, "&:hover": { bgcolor: "#334155" } } }, "Copy"),
        React.createElement("pre", { style: { margin: 0, color: "#e2e8f0", fontSize: 12, lineHeight: 1.7, fontFamily: "'Fira Code',monospace", whiteSpace: "pre-wrap", wordBreak: "break-all" } }, props.code)
      );
    };

    return (
      <Grid container spacing={2}>
        {/* Header */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={2}>
                <Box>
                  <Typography variant="h5" fontWeight={900} sx={{ color: "#dc2626" }}>OpenClaw</Typography>
                  <Typography variant="body2" color="text.secondary">Free, open-source, self-hosted AI agent platform</Typography>
                </Box>
                <Box sx={{ flexGrow: 1 }} />
                <Chip label="Node.js" size="small" sx={{ bgcolor: "#dcfce7", color: "#166534", fontWeight: 700 }} />
                <Chip label="20+ Channels" size="small" sx={{ bgcolor: "#dbeafe", color: "#1e40af", fontWeight: 700 }} />
                <Chip label="MIT License" size="small" sx={{ bgcolor: "#fef3c7", color: "#92400e", fontWeight: 700 }} />
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5, lineHeight: 1.8 }}>
                OpenClaw connects to WhatsApp, Telegram, Discord, Slack, Signal, iMessage, and 15+ more channels.
                Features browser automation, code execution, file management, persistent memory, cron jobs, voice support, and multi-agent workflows.
                Powered by local LLMs via Ollama or cloud APIs (OpenAI, Anthropic).
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Install Cards */}
        <Grid item xs={12} md={6}>
          <ActionCard
            title={"Install OpenClaw \u2014 OS (" + installOsLabel + ")"}
            description="Full automated setup: Node.js, OpenClaw, Ollama, systemd service, dashboard. Follows the official remote server guide."
            action={cfg.os === "windows" ? "/run/openclaw_windows_os" : "/run/openclaw_unix_os"}
            fields={commonFields} onRun={run} color="#dc2626"
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <ActionCard
            title="Install OpenClaw \u2014 Docker"
            description="Deploy OpenClaw gateway as a Docker container with Node.js. Runs the real OpenClaw dashboard on your selected port."
            action="/run/openclaw_docker"
            fields={commonFields} onRun={run} color="#dc2626"
          />
        </Grid>

        {/* Connection & Status */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #dc262644" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 2, color: "#dc2626" }}>Connection & Status</Typography>
              <Grid container spacing={2}>
                {/* Status Column */}
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>Service Status</Typography>
                  <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
                  {installed && <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>}
                  {installed && displayHost && <Typography variant="body2">Host: <b>{displayHost}</b></Typography>}
                  {installed && httpPort && <Typography variant="body2">Port: <b>{httpPort}</b></Typography>}
                  <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
                    {bestUrl && <Button variant="contained" size="small" onClick={function() { var dashUrl = bestUrl.indexOf("#") === -1 ? bestUrl + "/#token=serverinstaller" : bestUrl; window.open(dashUrl, "_blank"); }} sx={{ textTransform: "none", bgcolor: "#dc2626", "&:hover": { bgcolor: "#b91c1c" }, fontSize: 12 }}>Open Dashboard</Button>}
                    {installed && <Button variant="outlined" size="small" color="error" disabled={serviceBusy} onClick={function() {
                      if (!window.confirm("Are you sure you want to completely uninstall OpenClaw?\n\nThis will remove:\n- All Docker containers\n- All configuration and data\n- Firewall rules\n\nThis action cannot be undone.")) return;
                      run(null, "/run/openclaw_delete", "Uninstall OpenClaw");
                    }} sx={{ textTransform: "none", fontSize: 12 }}>Uninstall</Button>}
                  </Stack>
                </Grid>

                {/* Connection Info Column */}
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>Gateway Connection</Typography>
                  {installed && displayHost && httpPort ? (
                    <Box>
                      <Typography variant="body2" sx={{ mb: 0.5 }}>WebSocket URL:</Typography>
                      <Paper elevation={0} sx={{ p: 1, bgcolor: "#f8fafc", borderRadius: 1, fontFamily: "monospace", fontSize: 12, border: "1px solid #e2e8f0", wordBreak: "break-all", mb: 1 }}>
                        {"wss://" + displayHost + ":" + httpPort}
                      </Paper>
                      <Typography variant="body2" sx={{ mb: 0.5 }}>Gateway Token:</Typography>
                      <Paper elevation={0} sx={{ p: 1, bgcolor: "#f8fafc", borderRadius: 1, fontFamily: "monospace", fontSize: 12, border: "1px solid #e2e8f0", mb: 1 }}>
                        serverinstaller
                      </Paper>
                      <Typography variant="body2" sx={{ mb: 0.5 }}>Dashboard URL (with token):</Typography>
                      <Paper elevation={0} sx={{ p: 1, bgcolor: "#f0fdf4", borderRadius: 1, fontFamily: "monospace", fontSize: 11, border: "1px solid #dcfce7", wordBreak: "break-all", cursor: "pointer" }}
                        onClick={function() { if (copyText) copyText("https://" + displayHost + ":" + httpPort + "/#token=serverinstaller", "URL"); }}>
                        {"https://" + displayHost + ":" + httpPort + "/#token=serverinstaller"}
                        <Typography variant="caption" sx={{ display: "block", color: "#059669", mt: 0.5 }}>Click to copy</Typography>
                      </Paper>
                    </Box>
                  ) : (
                    <Typography variant="body2" color="text.secondary">Install OpenClaw first to see connection details.</Typography>
                  )}
                </Grid>

                {/* Ollama Column */}
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>Ollama (LLM Backend)</Typography>
                  {React.createElement(function OllamaStatus() {
                    var _os = React.useState("checking");
                    var ollamaStatus = _os[0], setOllamaStatus = _os[1];
                    var _om = React.useState([]);
                    var ollamaModels = _om[0], setOllamaModels = _om[1];
                    var _ou = React.useState("");
                    var ollamaUrl = _ou[0], setOllamaUrl = _ou[1];

                    React.useEffect(function() {
                      // Use Ollama service info from dashboard props
                      var ollamaHttpsUrl = String(ollamaInfo.https_url || "").trim();
                      var ollamaHttpUrl = String(ollamaInfo.http_url || "").trim();
                      var ollamaHttpsPort = String(ollamaInfo.https_port || "").trim();
                      var ollamaPort = String(ollamaInfo.http_port || "").trim();
                      var ollamaHost = String(ollamaInfo.host || "").trim();
                      var ollamaInstalled = !!ollamaInfo.installed;
                      var ollamaRunning = !!ollamaInfo.running;

                      // Build detected URL — prefer HTTPS when available
                      var detectedUrl = ollamaHttpsUrl || ollamaHttpUrl
                        || (ollamaHost && ollamaHttpsPort ? "https://" + ollamaHost + ":" + ollamaHttpsPort : "")
                        || (ollamaHost && ollamaPort ? "http://" + ollamaHost + ":" + ollamaPort : "");

                      if (ollamaInstalled || ollamaRunning || detectedUrl) {
                        setOllamaUrl(detectedUrl || "http://127.0.0.1:11434");
                        setOllamaStatus(ollamaRunning ? "ready" : "no-models");
                      }

                      // Always try to fetch models via dashboard API (works regardless of CORS)
                      fetch("/run/get_software", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "fetch" } })
                        .then(function(r) { return r.json(); })
                        .then(function(j) {
                          var oi = (j.ollama_service || j.software && j.software.ollama_service || {});
                          if (oi.installed || oi.running || oi.http_url || oi.https_url) {
                            var url = String(oi.https_url || "").trim()
                              || String(oi.http_url || "").trim()
                              || (oi.host && oi.https_port ? "https://" + oi.host + ":" + oi.https_port : "")
                              || (oi.host && oi.http_port ? "http://" + oi.host + ":" + oi.http_port : "");
                            if (url) setOllamaUrl(url);
                            setOllamaStatus(oi.running ? "ready" : oi.installed ? "no-models" : "offline");
                          }
                        })
                        .catch(function() {});
                    }, []);

                    return React.createElement("div", null,
                      React.createElement(Typography, { variant: "body2" },
                        "Status: ",
                        React.createElement(Chip, { size: "small", sx: { ml: 0.5 },
                          label: ollamaStatus === "ready" ? "Connected" : ollamaStatus === "no-models" ? "No models" : ollamaStatus === "checking" ? "Checking..." : "Not connected",
                          color: ollamaStatus === "ready" ? "success" : ollamaStatus === "no-models" ? "warning" : "default"
                        })
                      ),
                      ollamaUrl && React.createElement(Typography, { variant: "body2", sx: { mt: 0.5 } }, "URL: ", React.createElement("b", null, ollamaUrl)),
                      ollamaModels.length > 0 && React.createElement(Typography, { variant: "body2", sx: { mt: 0.5 } },
                        "Models: ", React.createElement("b", null, ollamaModels.map(function(m) { return m.name || m.model; }).join(", "))
                      ),
                      ollamaStatus === "offline" && React.createElement(Alert, { severity: "warning", sx: { mt: 1, borderRadius: 2, fontSize: 12 } },
                        "Ollama not detected. Install Ollama from the AI/ML page or enter a remote Ollama URL in the install form."
                      )
                    );
                  })}
                </Grid>
              </Grid>

              {/* Links */}
              <Stack direction="row" spacing={1} sx={{ mt: 2, pt: 1.5, borderTop: "1px solid #e8edf6" }} flexWrap="wrap" useFlexGap>
                <Button variant="outlined" size="small" href="https://github.com/openclaw/openclaw" target="_blank" rel="noopener" sx={{ textTransform: "none", borderRadius: 2, fontWeight: 600, borderColor: "#dc262644", color: "#dc2626" }}>GitHub</Button>
                <Button variant="outlined" size="small" href="https://openclaw.ai" target="_blank" rel="noopener" sx={{ textTransform: "none", borderRadius: 2, fontWeight: 600, borderColor: "#dc262644", color: "#dc2626" }}>Website</Button>
                <Button variant="outlined" size="small" href="https://mer.vin/2026/02/openclaw-remote-server-setup/" target="_blank" rel="noopener" sx={{ textTransform: "none", borderRadius: 2, fontWeight: 600, borderColor: "#dc262644", color: "#dc2626" }}>Setup Guide</Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Services */}
        <Grid item xs={12} md={6}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Services</Typography>
              {services.length === 0 && <Typography variant="body2" color="text.secondary">No services running. Install OpenClaw first.</Typography>}
              {services.map(function(svc) {
                var svcRunning = isServiceRunningStatus(svc.status, svc.sub_status);
                return (
                  <Paper key={"oc-" + svc.name} variant="outlined" sx={{ p: 1.5, mb: 1, borderRadius: 2 }}>
                    <Typography variant="body2" fontWeight={700}>{svc.display_name || svc.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{svc.kind} &middot; {svc.status}</Typography>
                    {renderServiceUrls(svc)}
                    <Stack direction="row" spacing={0.5} sx={{ mt: 1 }}>
                      <Button size="small" variant="outlined" color={svcRunning ? "error" : "success"} disabled={serviceBusy} onClick={function() { onServiceAction(svcRunning ? "stop" : "start", svc); }} sx={{ textTransform: "none", fontSize: 11, py: 0.3 }}>{svcRunning ? "Stop" : "Start"}</Button>
                      <Button size="small" variant="outlined" disabled={serviceBusy} onClick={function() { onServiceAction("restart", svc); }} sx={{ textTransform: "none", fontSize: 11, py: 0.3 }}>Restart</Button>
                      <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={function() { onServiceAction("delete", svc); }} sx={{ textTransform: "none", fontSize: 11, py: 0.3 }}>Delete</Button>
                    </Stack>
                  </Paper>
                );
              })}
            </CardContent>
          </Card>
        </Grid>

        {/* How to Get Tokens */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #f59e0b33" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
                <Box sx={{ width: 5, height: 32, borderRadius: 3, bgcolor: "#f59e0b" }} />
                <Typography variant="h6" fontWeight={800} sx={{ color: "#f59e0b" }}>How to Get Tokens & API Keys</Typography>
              </Stack>

              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, height: "100%" }}>
                    <Typography variant="subtitle2" fontWeight={800} sx={{ color: "#dc2626", mb: 1 }}>Telegram Bot Token</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
                      1. Open Telegram and search for <b>@BotFather</b><br/>
                      2. Send <code>/newbot</code><br/>
                      3. Choose a name and username for your bot<br/>
                      4. Copy the token (format: <code>123456:ABC-DEF...</code>)
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, height: "100%" }}>
                    <Typography variant="subtitle2" fontWeight={800} sx={{ color: "#5865F2", mb: 1 }}>Discord Bot Token</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
                      1. Go to <a href="https://discord.com/developers/applications" target="_blank" rel="noopener">Discord Developer Portal</a><br/>
                      2. Click "New Application" &rarr; name it<br/>
                      3. Go to "Bot" tab &rarr; "Add Bot"<br/>
                      4. Click "Reset Token" &rarr; copy the token<br/>
                      5. Enable "Message Content Intent" under Privileged Intents
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, height: "100%" }}>
                    <Typography variant="subtitle2" fontWeight={800} sx={{ color: "#25D366", mb: 1 }}>WhatsApp</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
                      OpenClaw uses <b>Baileys</b> (no API key needed).<br/>
                      1. Enter your phone number in the config<br/>
                      2. On first start, a QR code will appear in the logs<br/>
                      3. Scan it with WhatsApp on your phone<br/>
                      4. Run: <code>docker logs serverinstaller-openclaw</code> to see QR
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, height: "100%" }}>
                    <Typography variant="subtitle2" fontWeight={800} sx={{ color: "#4A154B", mb: 1 }}>Slack Bot Token</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
                      1. Go to <a href="https://api.slack.com/apps" target="_blank" rel="noopener">Slack API</a> &rarr; "Create New App"<br/>
                      2. Choose "From scratch" &rarr; name it &rarr; select workspace<br/>
                      3. Go to "OAuth & Permissions" &rarr; add scopes:<br/>
                      &nbsp;&nbsp;<code>chat:write</code>, <code>channels:history</code>, <code>im:history</code><br/>
                      4. Install to workspace &rarr; copy <code>xoxb-...</code> token
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, height: "100%" }}>
                    <Typography variant="subtitle2" fontWeight={800} sx={{ color: "#10a37f", mb: 1 }}>OpenAI API Key</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
                      1. Go to <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener">OpenAI API Keys</a><br/>
                      2. Click "Create new secret key"<br/>
                      3. Copy the key (starts with <code>sk-...</code>)<br/>
                      4. Add billing at platform.openai.com/settings/billing
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, height: "100%" }}>
                    <Typography variant="subtitle2" fontWeight={800} sx={{ color: "#d97706", mb: 1 }}>Anthropic (Claude) API Key</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
                      1. Go to <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">Anthropic Console</a><br/>
                      2. Click "Create Key"<br/>
                      3. Copy the key (starts with <code>sk-ant-...</code>)<br/>
                      4. Add billing at console.anthropic.com/settings/billing
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, height: "100%" }}>
                    <Typography variant="subtitle2" fontWeight={800} sx={{ color: "#6366f1", mb: 1 }}>Ollama (Local — Free)</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
                      No API key needed! Ollama runs locally.<br/>
                      1. Install Ollama from the AI/ML page<br/>
                      2. Pull a model: <code>ollama pull llama3.2:3b</code><br/>
                      3. OpenClaw auto-detects Ollama at localhost:11434
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, height: "100%" }}>
                    <Typography variant="subtitle2" fontWeight={800} sx={{ color: "#0088cc", mb: 1 }}>Signal, iMessage, Matrix, IRC...</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.8 }}>
                      Other channels are configured via the OpenClaw dashboard<br/>
                      after installation. Open the gateway URL and go to<br/>
                      <b>Channels</b> to add more messaging platforms.<br/>
                      See: <a href="https://docs.openclaw.ai" target="_blank" rel="noopener">docs.openclaw.ai</a>
                    </Typography>
                  </Paper>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Manual Setup Guide */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #dc262633" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
                <Box sx={{ width: 5, height: 32, borderRadius: 3, bgcolor: "#dc2626" }} />
                <Typography variant="h6" fontWeight={800} sx={{ color: "#dc2626" }}>Manual Setup Guide</Typography>
                <Chip label="Remote Server" size="small" sx={{ bgcolor: "#dc262610", color: "#dc2626", fontWeight: 600 }} />
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="text" size="small" href="https://mer.vin/2026/02/openclaw-remote-server-setup/" target="_blank" sx={{ textTransform: "none", color: "#dc2626" }}>Source Article</Button>
              </Stack>

              <Typography variant="subtitle2" fontWeight={800} sx={{ mt: 2, mb: 0.5, color: "#1e293b" }}>1. Create User</Typography>
              {React.createElement(CodeBlock, { code: 'adduser --disabled-password --gecos "" openclaw\nusermod -aG sudo openclaw\necho "openclaw ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/openclaw\nchmod 440 /etc/sudoers.d/openclaw\npasswd openclaw' })}

              <Typography variant="subtitle2" fontWeight={800} sx={{ mt: 2, mb: 0.5, color: "#1e293b" }}>2. Install Required Packages</Typography>
              {React.createElement(CodeBlock, { code: 'curl -fsSL https://deb.nodesource.com/setup_22.x | bash -\napt-get install -y nodejs build-essential python3' })}

              <Typography variant="subtitle2" fontWeight={800} sx={{ mt: 2, mb: 0.5, color: "#1e293b" }}>3a. Install OpenClaw</Typography>
              {React.createElement(CodeBlock, { code: "su - openclaw -c 'npm config set prefix ~/.npm-global && npm install -g openclaw@latest && echo \"export PATH=\\\"\\$HOME/.npm-global/bin:\\$PATH\\\"\" >> ~/.bashrc'\nls -la /home/openclaw/.npm-global/bin/openclaw" })}

              <Typography variant="subtitle2" fontWeight={800} sx={{ mt: 2, mb: 0.5, color: "#1e293b" }}>3b. Create Systemd Service</Typography>
              {React.createElement(CodeBlock, { code: "tee /etc/systemd/system/clawdbot-gateway.service > /dev/null << 'EOF'\n[Unit]\nDescription=Clawdbot Gateway (always-on)\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nUser=openclaw\nWorkingDirectory=/home/openclaw\nEnvironment=PATH=/usr/bin:/bin:/home/openclaw/.npm-global/bin\nExecStart=/home/openclaw/.npm-global/bin/openclaw gateway --bind loopback --port 18789 --verbose\nRestart=always\nRestartSec=5\n\n[Install]\nWantedBy=multi-user.target\nEOF" })}

              <Typography variant="subtitle2" fontWeight={800} sx={{ mt: 2, mb: 0.5, color: "#1e293b" }}>3c. Configure OpenClaw</Typography>
              {React.createElement(CodeBlock, { code: "su - openclaw -c '/home/openclaw/.npm-global/bin/openclaw onboard'" })}

              <Typography variant="subtitle2" fontWeight={800} sx={{ mt: 2, mb: 0.5, color: "#1e293b" }}>3d. Enable & Start Service</Typography>
              {React.createElement(CodeBlock, { code: 'systemctl daemon-reload\nsystemctl enable clawdbot-gateway.service\nsystemctl start clawdbot-gateway.service\nsystemctl status clawdbot-gateway.service' })}

              <Typography variant="subtitle2" fontWeight={800} sx={{ mt: 2, mb: 0.5, color: "#1e293b" }}>4a. Install Ollama & Configure Model</Typography>
              {React.createElement(CodeBlock, { code: "curl -fsSL https://ollama.com/install.sh | sh\nollama pull llama3.2:3b\nsystemctl stop clawdbot-gateway.service\nmkdir -p /tmp/ollama-backups && chmod 1777 /tmp/ollama-backups\nsu - openclaw -c 'ollama launch openclaw --model llama3.2:3b --config'" })}

              <Typography variant="subtitle2" fontWeight={800} sx={{ mt: 2, mb: 0.5, color: "#1e293b" }}>4b. Get Dashboard URL</Typography>
              {React.createElement(CodeBlock, { code: "systemctl start clawdbot-gateway.service\nsystemctl status clawdbot-gateway.service\nsu - openclaw -c '/home/openclaw/.npm-global/bin/openclaw dashboard --no-open'" })}

              <Typography variant="subtitle2" fontWeight={800} sx={{ mt: 2, mb: 0.5, color: "#1e293b" }}>5. SSH Tunnel (run from your local machine)</Typography>
              {React.createElement(CodeBlock, { code: 'ssh -N -L 18789:127.0.0.1:18789 openclaw@YOUR_SERVER_IP' })}

              <Alert severity="info" sx={{ mt: 2, borderRadius: 2 }}>
                <Typography variant="body2"><b>Notes:</b> To remove a previously configured OpenAI model:</Typography>
                <Paper elevation={0} sx={{ bgcolor: "#0f172a", borderRadius: 1, p: 1, mt: 1 }}>
                  <pre style={{ margin: 0, color: "#e2e8f0", fontSize: 12, fontFamily: "monospace" }}>{"su - openclaw -c '/home/openclaw/.npm-global/bin/openclaw models list'\nsu - openclaw -c '/home/openclaw/.npm-global/bin/openclaw models aliases remove GPT'"}</pre>
                </Paper>
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

  // ── OpenClaw API Docs Page ──────────────────────────────────────────────────
  ns.pages["agent-openclaw-api"] = function renderOpenClawApiPage(p) {
    var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
    var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
    var Box = p.Box, Paper = p.Paper, Chip = p.Chip, Tooltip = p.Tooltip, Alert = p.Alert;
    var setPage = p.setPage, copyText = p.copyText;
    var ocInfo = p.openclawService || {};
    var host = String(ocInfo.host || "").trim();
    var urlHost = (host && host !== "0.0.0.0") ? host : "{host}";
    var httpPort = String(ocInfo.http_port || "18789").trim();
    var httpsPort = String(ocInfo.https_port || "").trim();
    var httpBase = "http://" + urlHost + ":" + httpPort;
    var httpsBase = httpsPort ? "https://" + urlHost + ":" + httpsPort : "";

    var MC = { GET: { bg: "#dcfce7", c: "#166534", b: "#86efac" }, POST: { bg: "#dbeafe", c: "#1e40af", b: "#93c5fd" } };
    var mc = function(m) { return MC[m] || { bg: "#f3f4f6", c: "#374151", b: "#d1d5db" }; };
    var doCopy = function(text) { if (copyText) copyText(text, "cURL"); };

    var sections = [
      { name: "Gateway", color: "#dc2626", eps: [
        { m: "GET", p: "/", d: "OpenClaw Dashboard — the main web interface with WebChat, channels, skills, and configuration." },
        { m: "GET", p: "/api/health", d: "Health check.", res: '{ "ok": true, "status": "healthy" }' },
      ]},
      { name: "WebSocket", color: "#7c3aed", eps: [
        { m: "GET", p: "ws://host:18789", d: "WebSocket gateway — real-time bidirectional communication for chat, events, and tool execution." },
      ]},
      { name: "CLI Commands", color: "#059669", eps: [
        { m: "GET", p: "openclaw gateway --bind lan --port 18789", d: "Start the gateway server on LAN." },
        { m: "GET", p: "openclaw onboard", d: "Interactive onboarding wizard." },
        { m: "GET", p: "openclaw dashboard --no-open", d: "Get the dashboard URL without opening browser." },
        { m: "GET", p: "openclaw models list", d: "List configured LLM models." },
        { m: "GET", p: "openclaw models aliases remove GPT", d: "Remove a model alias." },
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
