(() => {
  var ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["ai-lmstudio"] = function renderLMStudioPage(p) {
    var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
    var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
    var Box = p.Box, Paper = p.Paper, Chip = p.Chip, Alert = p.Alert, Tooltip = p.Tooltip;
    var ActionCard = p.ActionCard, TextField = p.TextField;
    var FormControl = p.FormControl, InputLabel = p.InputLabel, Select = p.Select, MenuItem = p.MenuItem;
    var cfg = p.cfg, run = p.run, selectableIps = p.selectableIps, serviceBusy = p.serviceBusy;
    var isScopeLoading = p.isScopeLoading, scopeErrors = p.scopeErrors;
    var isServiceRunningStatus = p.isServiceRunningStatus, onServiceAction = p.onServiceAction;
    var renderServiceUrls = p.renderServiceUrls, renderServicePorts = p.renderServicePorts;
    var renderServiceStatus = p.renderServiceStatus, renderFolderIcon = p.renderFolderIcon;
    var setPage = p.setPage, setInfoMessage = p.setInfoMessage, copyText = p.copyText;

    var lmsInfo = p.lmstudioService || {};
    var services = p.lmstudioPageServices || [];
    var loadInfo = p.loadLmstudioInfo;
    var loadServices = p.loadLmstudioServices;

    var httpUrl = String(lmsInfo.http_url || "").trim();
    var httpsUrl = String(lmsInfo.https_url || "").trim();
    var httpPort = String(lmsInfo.http_port || "").trim();
    var httpsPort = String(lmsInfo.https_port || "").trim();
    var hostIp = String(lmsInfo.host || "").trim();
    var installed = !!lmsInfo.installed;
    var running = !!lmsInfo.running;

    var displayHost = (hostIp && hostIp !== "0.0.0.0" && hostIp !== "*") ? hostIp : "";
    var computedHttpUrl = installed && displayHost && httpPort ? "http://" + displayHost + ":" + httpPort : (installed ? httpUrl : "");
    var computedHttpsUrl = installed && displayHost && httpsPort ? "https://" + displayHost + ":" + httpsPort : (installed ? httpsUrl : "");
    var bestUrl = computedHttpsUrl || computedHttpUrl;

    var _ms = React.useState([]);
    var models = _ms[0], setModels = _ms[1];
    var _ci = React.useState("");
    var chatInput = _ci[0], setChatInput = _ci[1];
    var _cm = React.useState("");
    var chatModel = _cm[0], setChatModel = _cm[1];
    var _msgs = React.useState([]);
    var chatMessages = _msgs[0], setChatMessages = _msgs[1];
    var _cl = React.useState(false);
    var chatLoading = _cl[0], setChatLoading = _cl[1];

    var refreshModels = function() {
      if (!running && !installed) return;
      var url = bestUrl || "http://127.0.0.1:1234";
      fetch("/api/ollama/tags", { headers: { "X-Requested-With": "fetch" } }).catch(function(){});
      // Try LM Studio v1/models
      fetch(url + "/v1/models").then(function(r) { return r.json(); }).then(function(j) {
        var m = j.data || j.models || [];
        setModels(m);
        if (!chatModel && m.length > 0) setChatModel(m[0].id || m[0].name || "");
      }).catch(function(){});
    };

    React.useEffect(function() { if (running || installed) refreshModels(); }, [running, installed]);

    var handleChat = function() {
      if (!chatInput.trim() || !chatModel) return;
      var userMsg = { role: "user", content: chatInput.trim() };
      var newMsgs = chatMessages.concat([userMsg]);
      setChatMessages(newMsgs);
      setChatInput("");
      setChatLoading(true);
      var url = bestUrl || "http://127.0.0.1:1234";
      fetch(url + "/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: chatModel, messages: newMsgs }),
      })
        .then(function(r) { return r.json(); })
        .then(function(j) {
          if (j.choices && j.choices[0]) {
            setChatMessages(newMsgs.concat([j.choices[0].message]));
          } else {
            setChatMessages(newMsgs.concat([{ role: "assistant", content: "Error: " + (j.error || "No response") }]));
          }
        })
        .catch(function(e) { setChatMessages(newMsgs.concat([{ role: "assistant", content: "Error: " + e }])); })
        .finally(function() { setChatLoading(false); });
    };

    var installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : "macOS");

    var commonFields = [
      { name: "LMSTUDIO_HOST_IP", label: "Host IP", type: "select", options: selectableIps, defaultValue: selectableIps[0] || "", required: true, placeholder: "Select IP" },
      { name: "LMSTUDIO_HTTP_PORT", label: "Web UI HTTP Port", defaultValue: httpPort || "8080", checkPort: true, placeholder: "Leave empty for no web UI" },
      { name: "LMSTUDIO_HTTPS_PORT", label: "Web UI HTTPS Port", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty to skip HTTPS" },
      { name: "LMSTUDIO_DOMAIN", label: "Domain (optional)", defaultValue: lmsInfo.domain || "", placeholder: "e.g. lmstudio.example.com" },
      { name: "LMSTUDIO_USERNAME", label: "Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "LMSTUDIO_PASSWORD", label: "Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
    ];

    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#7c3aed" }}>LM Studio — Run LLMs Locally</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                LM Studio provides a desktop application for running LLMs locally with a beautiful UI and OpenAI-compatible API server.
                Supports GGUF models, GPU acceleration, and multiple concurrent models. The web UI proxy makes it accessible remotely.
              </Typography>
              <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                LM Studio must be installed separately from lmstudio.ai. This installer sets up the web UI proxy and configures remote access.
                Download models inside the LM Studio desktop app, then start the local server.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* API Docs */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #7c3aed44", background: "linear-gradient(135deg, #7c3aed05 0%, #ffffff 100%)" }}>
            <CardContent sx={{ py: 2, "&:last-child": { pb: 2 } }}>
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <Box sx={{ width: 6, height: 36, borderRadius: 3, bgcolor: "#7c3aed" }} />
                <Box sx={{ flexGrow: 1 }}>
                  <Typography variant="h6" fontWeight={800} sx={{ color: "#7c3aed" }}>LM Studio API Documentation</Typography>
                  <Typography variant="caption" color="text.secondary">OpenAI-compatible API — chat, completions, embeddings, models</Typography>
                </Box>
                <Chip label="6 endpoints" size="small" sx={{ bgcolor: "#7c3aed15", color: "#7c3aed", fontWeight: 700, border: "1px solid #7c3aed33" }} />
                <Button variant="contained" size="small" onClick={function() { setPage("ai-lmstudio-api"); }}
                  sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, bgcolor: "#7c3aed", "&:hover": { bgcolor: "#6d28d9" }, px: 3 }}>
                  API Documents
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Install */}
        <Grid item xs={12} md={6}>
          <ActionCard
            title={"Install LM Studio \u2014 OS (" + installOsLabel + ")"}
            description="Set up LM Studio with web UI proxy. Installs CLI, configures remote access on your selected port."
            action={cfg.os === "windows" ? "/run/lmstudio_windows_os" : "/run/lmstudio_unix_os"}
            fields={commonFields} onRun={run} color="#7c3aed"
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <ActionCard
            title="Install LM Studio \u2014 Docker"
            description="Deploy LM Studio Web UI as a Docker container. Connects to the LM Studio desktop app running on the host."
            action="/run/lmstudio_docker"
            fields={commonFields} onRun={run} color="#7c3aed"
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: "#7c3aed" }}>LM Studio Status</Typography>
              <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
              {installed && <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>}
              {installed && displayHost && <Typography variant="body2">Host: <b>{displayHost}</b></Typography>}
              {installed && httpPort && <Typography variant="body2">Web UI Port: <b>{httpPort}</b></Typography>}
              {computedHttpUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>HTTP: <a href={computedHttpUrl} target="_blank" rel="noopener">{computedHttpUrl}</a></Typography>}
              {computedHttpsUrl && <Typography variant="body2" sx={{ wordBreak: "break-all" }}>HTTPS: <a href={computedHttpsUrl} target="_blank" rel="noopener">{computedHttpsUrl}</a></Typography>}
              {installed && <Typography variant="body2" sx={{ mt: 0.5 }}>Models: <b>{models.length}</b></Typography>}
              {bestUrl && (
                <Button variant="contained" size="small" sx={{ mt: 1.5, textTransform: "none", bgcolor: "#7c3aed", "&:hover": { bgcolor: "#6d28d9" } }}
                  onClick={function() { window.open(bestUrl, "_blank"); }}>Open LM Studio</Button>
              )}
              <Box sx={{ mt: 2, pt: 1.5, borderTop: "1px solid #e8edf6" }}>
                <Typography variant="caption" color="text.secondary">
                  Download LM Studio: <a href="https://lmstudio.ai/download" target="_blank" rel="noopener">lmstudio.ai/download</a>
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Chat */}
        {installed && models.length > 0 && (
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #7c3aed33" }}>
              <CardContent>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                  <Typography variant="h6" fontWeight={800} sx={{ color: "#7c3aed" }}>Chat</Typography>
                  <FormControl size="small" sx={{ minWidth: 200 }}>
                    <Select value={chatModel} onChange={function(e) { setChatModel(e.target.value); setChatMessages([]); }} size="small">
                      {models.map(function(m) { var n = m.id || m.name; return <MenuItem key={n} value={n}>{n}</MenuItem>; })}
                    </Select>
                  </FormControl>
                  <Box sx={{ flexGrow: 1 }} />
                  <Button size="small" variant="text" onClick={function() { setChatMessages([]); }} sx={{ textTransform: "none" }}>Clear</Button>
                </Stack>
                <Paper elevation={0} sx={{ bgcolor: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 2, p: 2, minHeight: 200, maxHeight: 400, overflowY: "auto", mb: 1.5 }}>
                  {chatMessages.length === 0 && <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", mt: 6 }}>Start chatting with {chatModel}</Typography>}
                  {chatMessages.map(function(msg, i) {
                    return (
                      <Box key={i} sx={{ mb: 1.5, display: "flex", flexDirection: "column", alignItems: msg.role === "user" ? "flex-end" : "flex-start" }}>
                        <Paper elevation={0} sx={{ p: 1.5, borderRadius: 2, maxWidth: "80%", bgcolor: msg.role === "user" ? "#7c3aed" : "#fff", color: msg.role === "user" ? "#fff" : "#1f2937", border: msg.role === "user" ? "none" : "1px solid #e2e8f0" }}>
                          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{msg.content}</Typography>
                        </Paper>
                      </Box>
                    );
                  })}
                  {chatLoading && <Typography variant="body2" color="text.secondary">Thinking...</Typography>}
                </Paper>
                <Stack direction="row" spacing={1}>
                  <TextField size="small" fullWidth placeholder="Type a message..." value={chatInput}
                    onChange={function(e) { setChatInput(e.target.value); }}
                    onKeyDown={function(e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleChat(); } }}
                    disabled={chatLoading} multiline maxRows={3} />
                  <Button variant="contained" disabled={chatLoading || !chatInput.trim()} onClick={handleChat}
                    sx={{ textTransform: "none", bgcolor: "#7c3aed", minWidth: 80 }}>Send</Button>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* Services */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6" fontWeight={800}>LM Studio Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading("lmstudio")}
                  onClick={function() { if (loadInfo && loadInfo.current) loadInfo.current(); if (loadServices && loadServices.current) loadServices.current(); }}
                  sx={{ textTransform: "none" }}>Refresh</Button>
              </Stack>
              {services.length === 0 && <Typography variant="body2" color="text.secondary">No LM Studio services deployed yet.</Typography>}
              {services.map(function(svc) {
                var svcRunning = isServiceRunningStatus(svc.status, svc.sub_status);
                return (
                  <Paper key={"lms-" + (svc.kind || "") + "-" + svc.name} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                        {renderServiceUrls(svc)}{renderServicePorts(svc)}
                      </Box>
                      {renderServiceStatus(svc)}<Box sx={{ flexGrow: 1 }} />{renderFolderIcon(svc)}
                      <Button size="small" variant="outlined" color={svcRunning ? "error" : "success"} disabled={serviceBusy}
                        onClick={function() { onServiceAction(svcRunning ? "stop" : "start", svc); }} sx={{ textTransform: "none" }}>
                        {svcRunning ? "Stop" : "Start"}</Button>
                      <Button size="small" variant="outlined" disabled={serviceBusy}
                        onClick={function() { onServiceAction("restart", svc); }} sx={{ textTransform: "none" }}>Restart</Button>
                      <Button size="small" variant="outlined" color="error" disabled={serviceBusy}
                        onClick={function() { onServiceAction("delete", svc); }} sx={{ textTransform: "none" }}>Delete</Button>
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

  // ── LM Studio API Docs Page ─────────────────────────────────────────────────
  ns.pages["ai-lmstudio-api"] = function renderLMStudioApiPage(p) {
    var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
    var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
    var Box = p.Box, Paper = p.Paper, Chip = p.Chip, Tooltip = p.Tooltip, Alert = p.Alert;
    var setPage = p.setPage, copyText = p.copyText;
    var lmsInfo = p.lmstudioService || {};
    var host = String(lmsInfo.host || "").trim();
    var urlHost = (host && host !== "0.0.0.0") ? host : "{host}";
    var httpPort = String(lmsInfo.http_port || "8080").trim();
    var httpsPort = String(lmsInfo.https_port || "").trim();
    var httpBase = "http://" + urlHost + ":" + httpPort;
    var httpsBase = httpsPort ? "https://" + urlHost + ":" + httpsPort : "";

    var MC = { GET: { bg: "#dcfce7", c: "#166534", b: "#86efac" }, POST: { bg: "#dbeafe", c: "#1e40af", b: "#93c5fd" } };
    var mc = function(m) { return MC[m] || { bg: "#f3f4f6", c: "#374151", b: "#d1d5db" }; };
    var doCopy = function(text) { if (copyText) copyText(text, "cURL"); };

    var sections = [
      { name: "Chat & Completions (OpenAI-Compatible)", color: "#7c3aed", eps: [
        { m: "POST", p: "/v1/chat/completions", d: "Chat with a loaded model. Fully OpenAI-compatible — works with any OpenAI SDK.", body: '{\n  "model": "your-model-name",\n  "messages": [\n    { "role": "user", "content": "Hello!" }\n  ]\n}', res: '{\n  "choices": [{\n    "message": { "role": "assistant", "content": "Hi!" }\n  }]\n}' },
        { m: "POST", p: "/v1/completions", d: "Text completion from a prompt.", body: '{\n  "model": "your-model-name",\n  "prompt": "Write a poem",\n  "max_tokens": 200\n}', res: '{\n  "choices": [{ "text": "..." }]\n}' },
        { m: "POST", p: "/v1/embeddings", d: "Generate vector embeddings for text.", body: '{\n  "model": "your-model-name",\n  "input": "Hello world"\n}', res: '{\n  "data": [{ "embedding": [0.1, -0.2, ...] }]\n}' },
      ]},
      { name: "Model Management", color: "#059669", eps: [
        { m: "GET", p: "/v1/models", d: "List all loaded models.", res: '{\n  "data": [\n    { "id": "model-name", "object": "model" }\n  ]\n}' },
      ]},
      { name: "Health & Proxy", color: "#b45309", eps: [
        { m: "GET", p: "/api/health", d: "Health check — shows connection status to LM Studio.", res: '{ "ok": true, "status": "healthy" }' },
        { m: "GET", p: "/api/models", d: "List models (proxy format).", res: '{ "ok": true, "models": [...] }' },
      ]},
    ];

    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #7c3aed44" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
                <Button variant="outlined" size="small" onClick={function() { setPage("ai-lmstudio"); }} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, borderColor: "#7c3aed", color: "#7c3aed" }}>Back to LM Studio</Button>
                <Typography variant="h5" fontWeight={900} sx={{ color: "#7c3aed", flexGrow: 1 }}>LM Studio API Documentation</Typography>
              </Stack>
              <Alert severity="info" sx={{ borderRadius: 2, mt: 1 }}>
                <b>HTTP:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpBase}</code>
                {httpsBase && <span><br/><b>HTTPS:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpsBase}</code></span>}
                <br/>LM Studio is fully OpenAI-compatible. Point any OpenAI SDK to these URLs.
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
                          <Tooltip title="Copy cURL"><Button size="small" variant="outlined" onClick={function() { doCopy("curl -X " + ep.m + " \"" + httpBase + ep.p + "\""); }} sx={{ textTransform: "none", minWidth: 0, px: 1.5, fontSize: 11, borderColor: "#e2e8f0" }}>cURL</Button></Tooltip>
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
