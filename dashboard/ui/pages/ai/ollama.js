(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["ai-ollama"] = function renderOllamaPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Alert, Tooltip,
      ActionCard, TextField, FormControl, InputLabel, Select, MenuItem,
      cfg, run, selectableIps, serviceBusy,
      isScopeLoading, scopeErrors,
      isServiceRunningStatus, onServiceAction,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      setPage, setInfoMessage, copyText,
    } = p;

    var ollamaInfo = p.ollamaService || {};
    var services = p.ollamaPageServices || [];
    var loadInfo = p.loadOllamaInfo;
    var loadServices = p.loadOllamaServices;

    var httpUrl = String(ollamaInfo.http_url || "").trim();
    var httpsUrl = String(ollamaInfo.https_url || "").trim();
    var httpPort = String(ollamaInfo.http_port || "").trim();
    var httpsPort = String(ollamaInfo.https_port || "").trim();
    var hostIp = String(ollamaInfo.host || "").trim();
    var installed = !!ollamaInfo.installed;
    var running = !!ollamaInfo.running;
    var webuiUrl = String(ollamaInfo.webui_url || "").trim();
    // Only show URLs when installed — use the user-selected IP
    var displayHost = (hostIp && hostIp !== "0.0.0.0" && hostIp !== "*") ? hostIp : "";
    var computedHttpUrl = installed && displayHost && httpPort ? "http://" + displayHost + ":" + httpPort : (installed ? httpUrl : "");
    var computedHttpsUrl = installed && displayHost && httpsPort ? "https://" + displayHost + ":" + httpsPort : (installed ? httpsUrl : "");
    var computedUrl = computedHttpsUrl || computedHttpUrl;
    var bestUrl = installed ? (webuiUrl || computedUrl) : "";

    var _ms = React.useState([]);
    var models = _ms[0], setModels = _ms[1];
    var _ml = React.useState(false);
    var modelLoading = _ml[0], setModelLoading = _ml[1];
    var _pn = React.useState("llama3.2");
    var pullName = _pn[0], setPullName = _pn[1];
    var _pl = React.useState(false);
    var pulling = _pl[0], setPulling = _pl[1];
    var _cm = React.useState("");
    var chatModel = _cm[0], setChatModel = _cm[1];
    var _ci = React.useState("");
    var chatInput = _ci[0], setChatInput = _ci[1];
    var _msgs = React.useState([]);
    var chatMessages = _msgs[0], setChatMessages = _msgs[1];
    var _cl = React.useState(false);
    var chatLoading = _cl[0], setChatLoading = _cl[1];
    var chatEndRef = React.useRef(null);

    var refreshModels = function() {
      if (!running && !installed) return;
      setModelLoading(true);
      fetch("/api/ollama/tags", { headers: { "X-Requested-With": "fetch" } })
        .then(function(r) { return r.json(); })
        .then(function(j) {
          if (j.ok && j.models) {
            setModels(j.models);
            if (!chatModel && j.models.length > 0) setChatModel(j.models[0].name || j.models[0].model || "");
          }
        })
        .catch(function() {})
        .finally(function() { setModelLoading(false); });
    };

    React.useEffect(function() { if (running) refreshModels(); }, [running]);

    var handlePull = function() {
      if (!pullName.trim()) return;
      setPulling(true);
      // Use the run system to show progress in web terminal
      var fd = new FormData();
      fd.append("OLLAMA_MODEL_NAME", pullName.trim());
      run(null, "/run/ollama_pull_model", "Pull " + pullName, fd);
      // Also try direct API for quick feedback
      fetch("/api/ollama/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
        body: JSON.stringify({ name: pullName.trim() }),
      })
        .then(function(r) { return r.json(); })
        .then(function(j) {
          if (j.ok) {
            if (setInfoMessage) setInfoMessage("Model \"" + pullName + "\" pulled successfully.");
            refreshModels();
          } else {
            var errMsg = j.error || "Unknown error";
            if (errMsg.indexOf("Connection refused") !== -1 || errMsg.indexOf("10061") !== -1 || errMsg.indexOf("111") !== -1) {
              errMsg = "Ollama server is not running. Click Start in the Services list below, or install Ollama first.";
            }
            if (setInfoMessage) setInfoMessage("Pull: " + errMsg);
          }
        })
        .catch(function(e) {
          var errMsg = String(e);
          if (errMsg.indexOf("Connection refused") !== -1 || errMsg.indexOf("10061") !== -1) {
            errMsg = "Ollama server is not running. Start the service first.";
          }
          if (setInfoMessage) setInfoMessage("Pull: " + errMsg);
        })
        .finally(function() { setPulling(false); });
    };

    var handleDelete = function(name) {
      if (!window.confirm("Delete model \"" + name + "\"?")) return;
      fetch("/api/ollama/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
        body: JSON.stringify({ name: name }),
      }).then(function() { refreshModels(); }).catch(function() {});
    };

    var handleChat = function() {
      if (!chatInput.trim() || !chatModel) return;
      var userMsg = { role: "user", content: chatInput.trim() };
      var newMsgs = chatMessages.concat([userMsg]);
      setChatMessages(newMsgs);
      setChatInput("");
      setChatLoading(true);
      fetch("/api/ollama/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
        body: JSON.stringify({ model: chatModel, messages: newMsgs }),
      })
        .then(function(r) { return r.json(); })
        .then(function(j) {
          if (j.ok && j.message) {
            setChatMessages(newMsgs.concat([j.message]));
          } else {
            setChatMessages(newMsgs.concat([{ role: "assistant", content: "Error: " + (j.error || "No response") }]));
          }
        })
        .catch(function(e) {
          setChatMessages(newMsgs.concat([{ role: "assistant", content: "Error: " + e }]));
        })
        .finally(function() { setChatLoading(false); });
    };

    React.useEffect(function() {
      if (chatEndRef.current) chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }, [chatMessages]);

    var installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : (cfg.os === "darwin" ? "macOS" : cfg.os_label));

    var commonFields = [
      { name: "OLLAMA_HOST_IP", label: "Host IP", type: "select", options: selectableIps, defaultValue: selectableIps[0] || "", required: true, placeholder: "Select IP" },
      { name: "OLLAMA_HTTP_PORT", label: "Web UI HTTP Port", defaultValue: httpPort || "", checkPort: true, placeholder: "Default: 11434 (leave empty for HTTPS-only)" },
      { name: "OLLAMA_HTTPS_PORT", label: "Web UI HTTPS Port", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty to skip HTTPS" },
      { name: "OLLAMA_DOMAIN", label: "Domain (optional)", defaultValue: ollamaInfo.domain || "", placeholder: "e.g. ollama.example.com" },
      { name: "OLLAMA_USERNAME", label: "Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "OLLAMA_PASSWORD", label: "Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
    ];

    var popularModels = [
      { name: "llama3.2", desc: "Meta Llama 3.2 (3B)", size: "2 GB" },
      { name: "llama3.1:8b", desc: "Meta Llama 3.1 (8B)", size: "4.7 GB" },
      { name: "mistral", desc: "Mistral 7B", size: "4.1 GB" },
      { name: "gemma2:2b", desc: "Google Gemma 2 (2B)", size: "1.6 GB" },
      { name: "phi3:mini", desc: "Microsoft Phi-3 Mini", size: "2.3 GB" },
      { name: "codellama", desc: "Code Llama", size: "3.8 GB" },
      { name: "deepseek-coder-v2:lite", desc: "DeepSeek Coder V2", size: "8.9 GB" },
      { name: "qwen2.5:7b", desc: "Alibaba Qwen 2.5", size: "4.7 GB" },
      { name: "nomic-embed-text", desc: "Embeddings model", size: "274 MB" },
    ];

    var formatSize = function(bytes) {
      if (!bytes) return "";
      var gb = bytes / 1073741824;
      return gb >= 1 ? gb.toFixed(1) + " GB" : (bytes / 1048576).toFixed(0) + " MB";
    };

    return (
      <Grid container spacing={2}>
        {/* Description */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#1e40af" }}>
                Ollama — Run LLMs Locally
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Ollama runs large language models locally with an OpenAI-compatible API. Chat with Llama 3, Mistral,
                Gemma, Phi, DeepSeek, CodeLlama, and hundreds more. Supports GPU acceleration (NVIDIA, AMD, Apple Silicon).
              </Typography>
              <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                Ollama requires at least 4 GB RAM for small models (3B) and 8+ GB for larger models (7B+).
                GPU acceleration dramatically improves performance — NVIDIA GPUs with 6+ GB VRAM recommended.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* API Documents Button (top) */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #1e40af44", background: "linear-gradient(135deg, #1e40af05 0%, #ffffff 100%)" }}>
            <CardContent sx={{ py: 2, "&:last-child": { pb: 2 } }}>
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <Box sx={{ width: 6, height: 36, borderRadius: 3, bgcolor: "#1e40af" }} />
                <Box sx={{ flexGrow: 1 }}>
                  <Typography variant="h6" fontWeight={800} sx={{ color: "#1e40af" }}>Ollama API Documentation</Typography>
                  <Typography variant="caption" color="text.secondary">OpenAI-compatible API — chat, generate, embeddings, model management</Typography>
                </Box>
                <Chip label="12 endpoints" size="small" sx={{ bgcolor: "#1e40af15", color: "#1e40af", fontWeight: 700, border: "1px solid #1e40af33" }} />
                <Button variant="contained" size="small" onClick={function() { setPage("ai-ollama-api"); }}
                  sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, bgcolor: "#1e40af", "&:hover": { bgcolor: "#1d4ed8" }, px: 3 }}>
                  API Documents
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Install OS */}
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title={"Install Ollama \u2014 OS (" + installOsLabel + ")"}
            description="Install Ollama as a managed OS service with Web UI. Downloads official binary and configures auto-start."
            action={cfg.os === "windows" ? "/run/ollama_windows_os" : "/run/ollama_unix_os"}
            fields={commonFields}
            onRun={run}
            color="#1e40af"
          />
        </Grid>

        {/* Install Docker */}
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title="Install Ollama \u2014 Docker"
            description="Deploy Ollama in a Docker container with optional GPU passthrough (nvidia-container-toolkit)."
            action="/run/ollama_docker"
            fields={commonFields}
            onRun={run}
            color="#0891b2"
          />
        </Grid>

        {/* Install IIS (Windows only) */}
        {cfg.os === "windows" && (
          <Grid item xs={12} md={4}>
            <ActionCard
              title="Install Ollama \u2014 IIS"
              description="Ollama with IIS reverse proxy for HTTPS access."
              action="/run/ollama_windows_iis"
              fields={commonFields}
              onRun={run}
              color="#d97706"
            />
          </Grid>
        )}

        {/* Status */}
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: "#1e40af" }}>Ollama Status</Typography>
              <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
              {installed && <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>}
              {installed && displayHost && <Typography variant="body2">Host: <b>{displayHost}</b></Typography>}
              {installed && httpPort && <Typography variant="body2">API Port: <b>{httpPort}</b></Typography>}
              {ollamaInfo.version && <Typography variant="body2">Version: <b>{ollamaInfo.version}</b></Typography>}
              {computedHttpUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>HTTP: <a href={computedHttpUrl} target="_blank" rel="noopener">{computedHttpUrl}</a></Typography>}
              {computedHttpsUrl && <Typography variant="body2" sx={{ wordBreak: "break-all" }}>HTTPS: <a href={computedHttpsUrl} target="_blank" rel="noopener">{computedHttpsUrl}</a></Typography>}
              {webuiUrl && <Typography variant="body2" sx={{ wordBreak: "break-all" }}>Web UI: <a href={webuiUrl} target="_blank" rel="noopener">{webuiUrl}</a></Typography>}
              {installed && <Typography variant="body2" sx={{ mt: 0.5 }}>Models: <b>{models.length}</b></Typography>}
              {bestUrl && (
                <Button variant="contained" size="small" sx={{ mt: 1.5, textTransform: "none", bgcolor: "#1e40af", "&:hover": { bgcolor: "#1d4ed8" } }}
                  onClick={function() { window.open(bestUrl, "_blank", "noopener,noreferrer"); }}>
                  Open Ollama
                </Button>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Model Management */}
        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                <Typography variant="h6" fontWeight={800} sx={{ flexGrow: 1 }}>Models</Typography>
                <Button variant="outlined" size="small" disabled={modelLoading} onClick={refreshModels} sx={{ textTransform: "none" }}>
                  {modelLoading ? "Loading..." : "Refresh"}
                </Button>
              </Stack>

              {/* Pull */}
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 2 }}>
                <TextField
                  size="small" label="Pull Model" placeholder="e.g. llama3.2, mistral, gemma2"
                  value={pullName} onChange={function(e) { setPullName(e.target.value); }}
                  sx={{ flexGrow: 1 }}
                  onKeyDown={function(e) { if (e.key === "Enter") handlePull(); }}
                />
                <Button variant="contained" disabled={pulling || !pullName.trim()} onClick={handlePull} sx={{ textTransform: "none", bgcolor: "#1e40af", minWidth: 100 }}>
                  {pulling ? "Pulling..." : "Pull"}
                </Button>
              </Stack>

              {/* Popular models */}
              <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ mb: 0.5, display: "block" }}>Popular Models (click to select):</Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
                {popularModels.map(function(m) {
                  return (
                    <Chip
                      key={m.name}
                      label={m.name + " (" + m.size + ")"}
                      size="small" variant="outlined"
                      onClick={function() { setPullName(m.name); }}
                      sx={{ cursor: "pointer", fontSize: 11, "&:hover": { bgcolor: "#eff6ff", borderColor: "#1e40af" } }}
                      title={m.desc}
                    />
                  );
                })}
              </Stack>

              {/* Installed models */}
              {models.length === 0 && !modelLoading && (
                <Typography variant="body2" color="text.secondary">No models downloaded yet. Pull a model to get started.</Typography>
              )}
              {models.map(function(m) {
                var mName = m.name || m.model;
                var mSize = m.size ? formatSize(m.size) : "";
                var mParams = (m.details && m.details.parameter_size) ? m.details.parameter_size : "";
                return (
                  <Paper key={mName} variant="outlined" sx={{ p: 1, mb: 0.5, borderRadius: 2 }}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography variant="body2" sx={{ flexGrow: 1 }}><b>{mName}</b></Typography>
                      {mSize && <Chip label={mSize} size="small" variant="outlined" sx={{ fontSize: 10, height: 18 }} />}
                      {mParams && <Chip label={mParams} size="small" variant="outlined" sx={{ fontSize: 10, height: 18 }} />}
                      <Button size="small" variant="outlined" color="error" onClick={function() { handleDelete(mName); }} sx={{ textTransform: "none", fontSize: 11 }}>
                        Delete
                      </Button>
                    </Stack>
                  </Paper>
                );
              })}
            </CardContent>
          </Card>
        </Grid>

        {/* Chat UI */}
        {running && models.length > 0 && (
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #1e40af33" }}>
              <CardContent>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                  <Typography variant="h6" fontWeight={800} sx={{ color: "#1e40af" }}>Chat</Typography>
                  <FormControl size="small" sx={{ minWidth: 200 }}>
                    <Select value={chatModel} onChange={function(e) { setChatModel(e.target.value); setChatMessages([]); }} size="small">
                      {models.map(function(m) {
                        var n = m.name || m.model;
                        return <MenuItem key={n} value={n}>{n}</MenuItem>;
                      })}
                    </Select>
                  </FormControl>
                  <Box sx={{ flexGrow: 1 }} />
                  <Button size="small" variant="text" onClick={function() { setChatMessages([]); }} sx={{ textTransform: "none" }}>Clear</Button>
                </Stack>

                <Paper elevation={0} sx={{ bgcolor: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 2, p: 2, minHeight: 200, maxHeight: 400, overflowY: "auto", mb: 1.5 }}>
                  {chatMessages.length === 0 && (
                    <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", mt: 6 }}>
                      Start a conversation with {chatModel}
                    </Typography>
                  )}
                  {chatMessages.map(function(msg, i) {
                    return (
                      <Box key={i} sx={{ mb: 1.5, display: "flex", flexDirection: "column", alignItems: msg.role === "user" ? "flex-end" : "flex-start" }}>
                        <Paper elevation={0} sx={{
                          p: 1.5, borderRadius: 2, maxWidth: "80%",
                          bgcolor: msg.role === "user" ? "#1e40af" : "#fff",
                          color: msg.role === "user" ? "#fff" : "#1f2937",
                          border: msg.role === "user" ? "none" : "1px solid #e2e8f0",
                        }}>
                          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{msg.content}</Typography>
                        </Paper>
                      </Box>
                    );
                  })}
                  {chatLoading && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Thinking...</Typography>
                  )}
                  <div ref={chatEndRef} />
                </Paper>

                <Stack direction="row" spacing={1}>
                  <TextField
                    size="small" fullWidth placeholder="Type a message..."
                    value={chatInput} onChange={function(e) { setChatInput(e.target.value); }}
                    onKeyDown={function(e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleChat(); } }}
                    disabled={chatLoading}
                    multiline maxRows={3}
                  />
                  <Button variant="contained" disabled={chatLoading || !chatInput.trim()} onClick={handleChat} sx={{ textTransform: "none", bgcolor: "#1e40af", minWidth: 80 }}>
                    Send
                  </Button>
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
                <Typography variant="h6" fontWeight={800}>Ollama Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                {bestUrl && running && (
                  <Button variant="contained" size="small" onClick={function() { window.open(bestUrl, "_blank"); }}
                    sx={{ textTransform: "none", bgcolor: "#1e40af", "&:hover": { bgcolor: "#1d4ed8" } }}>
                    Open Ollama
                  </Button>
                )}
                <Button variant="outlined" disabled={isScopeLoading("ollama")}
                  onClick={function() { if (loadInfo && loadInfo.current) loadInfo.current(); if (loadServices && loadServices.current) loadServices.current(); }}
                  sx={{ textTransform: "none" }}>
                  {isScopeLoading("ollama") ? "Refreshing..." : "Refresh"}
                </Button>
              </Stack>
              {scopeErrors.ollama && <Alert severity="error" sx={{ mb: 1 }}>{scopeErrors.ollama}</Alert>}
              {services.length === 0 && (
                <Typography variant="body2" color="text.secondary">No Ollama services deployed yet. Use an Install card above.</Typography>
              )}
              {services.map(function(svc) {
                var svcRunning = isServiceRunningStatus(svc.status, svc.sub_status);
                return (
                  <Paper key={"ollama-" + (svc.kind || "") + "-" + svc.name} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                        {renderServiceUrls(svc)}
                        {renderServicePorts(svc)}
                      </Box>
                      {renderServiceStatus(svc)}
                      <Box sx={{ flexGrow: 1 }} />
                      {renderFolderIcon(svc)}
                      <Button size="small" variant="outlined" color={svcRunning ? "error" : "success"} disabled={serviceBusy}
                        onClick={function() { onServiceAction(svcRunning ? "stop" : "start", svc); }} sx={{ textTransform: "none" }}>
                        {svcRunning ? "Stop" : "Start"}
                      </Button>
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

        {/* (API button moved to top) */}
      </Grid>
    );
  };

  // ── Ollama API Documentation Page ───────────────────────────────────────────
  ns.pages["ai-ollama-api"] = function renderOllamaApiPage(p) {
    var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
    var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
    var Box = p.Box, Paper = p.Paper, Chip = p.Chip, Tooltip = p.Tooltip, Alert = p.Alert;
    var setPage = p.setPage, copyText = p.copyText;

    var ollamaInfo = p.ollamaService || {};
    var host = String(ollamaInfo.host || "").trim();
    var urlHost = (host && host !== "0.0.0.0" && host !== "*") ? host : "{host}";
    var httpPort = String(ollamaInfo.http_port || "11434").trim();
    var httpsPort = String(ollamaInfo.https_port || "").trim();
    var httpBase = "http://" + urlHost + ":" + httpPort;
    var httpsBase = httpsPort ? "https://" + urlHost + ":" + httpsPort : "";

    var MC = { GET: { bg: "#dcfce7", c: "#166534", b: "#86efac" }, POST: { bg: "#dbeafe", c: "#1e40af", b: "#93c5fd" }, DELETE: { bg: "#fee2e2", c: "#991b1b", b: "#fca5a5" } };
    var mc = function(m) { return MC[m] || { bg: "#f3f4f6", c: "#374151", b: "#d1d5db" }; };
    var doCopy = function(text) { if (copyText) copyText(text, "cURL"); };

    var sections = [
      { name: "Chat & Generate", color: "#1e40af", eps: [
        { m: "POST", p: "/api/chat", d: "Chat with a model. Send messages and get the assistant response.", body: '{\n  "model": "llama3.2",\n  "messages": [\n    { "role": "user", "content": "Hello!" }\n  ],\n  "stream": false\n}', res: '{\n  "model": "llama3.2",\n  "message": {\n    "role": "assistant",\n    "content": "Hi there!"\n  },\n  "done": true\n}' },
        { m: "POST", p: "/api/generate", d: "Generate text completion from a prompt.", body: '{\n  "model": "llama3.2",\n  "prompt": "Write a haiku about coding",\n  "stream": false\n}', res: '{\n  "response": "Lines of code unfold..."\n}' },
        { m: "POST", p: "/api/embeddings", d: "Generate vector embeddings for text (for RAG, semantic search).", body: '{\n  "model": "llama3.2",\n  "prompt": "Hello world"\n}', res: '{\n  "embedding": [0.123, -0.456, ...]\n}' },
      ]},
      { name: "Model Management", color: "#059669", eps: [
        { m: "GET", p: "/api/tags", d: "List all downloaded models.", res: '{\n  "models": [\n    { "name": "llama3.2:latest", "size": 2000000000 }\n  ]\n}' },
        { m: "POST", p: "/api/pull", d: "Download a model from the registry.", body: '{ "name": "llama3.2" }', res: '{ "status": "success" }' },
        { m: "DELETE", p: "/api/delete", d: "Delete a downloaded model.", body: '{ "name": "llama3.2" }', res: '{ "status": "success" }' },
        { m: "POST", p: "/api/show", d: "Show model details.", body: '{ "name": "llama3.2" }', res: '{ "modelfile": "...", "parameters": "..." }' },
        { m: "GET", p: "/api/ps", d: "List models loaded in memory.", res: '{ "models": [...] }' },
        { m: "POST", p: "/api/copy", d: "Copy/alias a model.", body: '{ "source": "llama3.2", "destination": "my-model" }', res: "200 OK" },
        { m: "POST", p: "/api/create", d: "Create custom model from Modelfile.", body: '{ "name": "my-assistant", "modelfile": "FROM llama3.2\\nSYSTEM You are helpful." }', res: '{ "status": "success" }' },
      ]},
      { name: "OpenAI-Compatible (v1)", color: "#7c3aed", eps: [
        { m: "POST", p: "/v1/chat/completions", d: "OpenAI-compatible chat. Works with any OpenAI SDK.", body: '{\n  "model": "llama3.2",\n  "messages": [{ "role": "user", "content": "Hello" }]\n}', res: '{ "choices": [{ "message": { "content": "Hi!" } }] }' },
        { m: "GET", p: "/v1/models", d: "List models (OpenAI format).", res: '{ "data": [{ "id": "llama3.2" }] }' },
      ]},
    ];

    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #1e40af44" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
                <Button variant="outlined" size="small" onClick={function() { setPage("ai-ollama"); }} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, borderColor: "#1e40af", color: "#1e40af" }}>
                  Back to Ollama
                </Button>
                <Typography variant="h5" fontWeight={900} sx={{ color: "#1e40af", flexGrow: 1 }}>Ollama API Documentation</Typography>
                <Chip label="12 endpoints" size="small" sx={{ bgcolor: "#1e40af15", color: "#1e40af", fontWeight: 700 }} />
              </Stack>
              <Alert severity="info" sx={{ borderRadius: 2, mt: 1 }}>
                <b>HTTP:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpBase}</code>
                {httpsBase && <><br/><b>HTTPS:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpsBase}</code></>}
                {!httpsBase && <><br/><b>HTTPS:</b> <span style={{ color: "#94a3b8" }}>Not configured — set HTTPS Port during install</span></>}
                <br/>Also supports OpenAI /v1/ endpoints. Point any OpenAI SDK to these URLs.
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
                            {httpsBase && (
                              <Typography sx={{ fontFamily: "monospace", fontWeight: 600, wordBreak: "break-all", fontSize: 13, color: "#059669", mt: 0.3 }}>{httpsBase + ep.p}</Typography>
                            )}
                          </Box>
                          <Tooltip title="Copy cURL">
                            <Button size="small" variant="outlined" onClick={function() { doCopy("curl -X " + ep.m + " \"" + httpBase + ep.p + "\""); }} sx={{ textTransform: "none", minWidth: 0, px: 1.5, fontSize: 11, borderColor: "#e2e8f0" }}>cURL</Button>
                          </Tooltip>
                        </Stack>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{ep.d}</Typography>
                        {ep.body && (
                          <Box sx={{ mt: 1.5 }}>
                            <Typography variant="caption" fontWeight={700} sx={{ color: "#475569" }}>Request Body:</Typography>
                            <Paper elevation={0} sx={{ mt: 0.3, p: 1.5, bgcolor: "#f8fafc", borderRadius: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", border: "1px solid #e2e8f0", lineHeight: 1.7 }}>{ep.body}</Paper>
                          </Box>
                        )}
                        {ep.res && (
                          <Box sx={{ mt: 1.5 }}>
                            <Typography variant="caption" fontWeight={700} sx={{ color: "#475569" }}>Response:</Typography>
                            <Paper elevation={0} sx={{ mt: 0.3, p: 1.5, bgcolor: "#f0fdf4", borderRadius: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", border: "1px solid #dcfce7", lineHeight: 1.7 }}>{ep.res}</Paper>
                          </Box>
                        )}
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
