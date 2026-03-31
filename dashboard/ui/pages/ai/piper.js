(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["ai-piper"] = function renderPiperPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Alert,
      ActionCard, NavCard, TextField, FormControl, InputLabel, Select, MenuItem,
      cfg, run, selectableIps, serviceBusy,
      isScopeLoading, scopeErrors,
      isServiceRunningStatus, formatServiceState, onServiceAction, IconOnlyAction, FolderIcon,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      setPage, setInfoMessage, setFileManagerPath,
    } = p;

    const piperInfo = (p.piperService) || {};
    const services = p.piperPageServices || [];
    const loadInfo = p.loadPiperInfo;
    const loadServices = p.loadPiperServices;

    const httpUrl = String(piperInfo.http_url || "").trim();
    const httpsUrl = String(piperInfo.https_url || "").trim();
    const httpPort = String(piperInfo.http_port || "5500").trim();
    const installed = !!piperInfo.installed;
    const running = !!piperInfo.running;
    const voice = String(piperInfo.voice || "en_US-lessac-medium").trim();
    const httpsPort = String(piperInfo.https_port || "").trim();
    const bestUrl = httpsUrl || httpUrl || (installed && httpsPort ? `https://127.0.0.1:${httpsPort}` : installed ? `http://127.0.0.1:${httpPort}` : "");

    // TTS test state
    const [ttsText, setTtsText] = React.useState("Hello! This is a test of the Piper text to speech engine.");
    const [ttsLoading, setTtsLoading] = React.useState(false);
    const [ttsAudioUrl, setTtsAudioUrl] = React.useState("");
    const audioRef = React.useRef(null);

    const handleSpeak = React.useCallback(async () => {
      if (!ttsText.trim() || !bestUrl) return;
      setTtsLoading(true);
      setTtsAudioUrl("");
      try {
        const apiBase = bestUrl.replace(/\/+$/, "");
        const r = await fetch(`${apiBase}/api/tts`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
          body: JSON.stringify({ text: ttsText.trim() }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        setTtsAudioUrl(url);
        if (audioRef.current) {
          audioRef.current.src = url;
          audioRef.current.play().catch(() => {});
        }
      } catch (e) {
        if (setInfoMessage) setInfoMessage(`TTS error: ${e}`);
      }
      setTtsLoading(false);
    }, [ttsText, bestUrl, setInfoMessage]);

    // Clean up object URL on unmount
    React.useEffect(() => {
      return () => { if (ttsAudioUrl) URL.revokeObjectURL(ttsAudioUrl); };
    }, [ttsAudioUrl]);

    const installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : (cfg.os === "darwin" ? "macOS" : cfg.os_label));

    const commonFields = [
      { name: "PIPER_HOST_IP", label: "Host IP", type: "select", options: selectableIps, defaultValue: selectableIps[0] || "", required: true, placeholder: "Select IP" },
      { name: "PIPER_HTTP_PORT", label: "HTTP Port", defaultValue: httpPort || "5500", checkPort: true },
      { name: "PIPER_HTTPS_PORT", label: "HTTPS Port (optional)", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty to skip HTTPS" },
      { name: "PIPER_DOMAIN", label: "Domain (optional)", defaultValue: piperInfo.domain || "", placeholder: "e.g. piper.example.com" },
      { name: "PIPER_USERNAME", label: "Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "PIPER_PASSWORD", label: "Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "PIPER_VOICE", label: "Voice", defaultValue: voice, placeholder: "e.g. en_US-lessac-medium" },
    ];

    return (
      <Grid container spacing={2}>
        {/* ── Description ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#b45309" }}>
                Piper TTS — Text to Speech
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Fast, local text-to-speech engine with natural-sounding voices. Supports 30+ languages
                with multiple voice options. Runs entirely on CPU — no GPU needed.
              </Typography>
              <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                Piper runs on CPU with minimal resource requirements. Most voices need less than 100 MB RAM.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Install Cards ── */}
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title={`Install Piper TTS — OS (${installOsLabel})`}
            description="Install Piper as a managed OS service. Downloads the official binary and configures auto-start."
            action={cfg.os === "windows" ? "/run/piper_windows_os" : "/run/piper_unix_os"}
            fields={commonFields}
            onRun={run}
            color="#b45309"
          />
        </Grid>
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title="Install Piper TTS — Docker"
            description="Deploy Piper in a Docker container for easy isolation and portability."
            action="/run/piper_docker"
            fields={commonFields}
            onRun={run}
            color="#0891b2"
          />
        </Grid>
        {cfg.os === "windows" && (
          <Grid item xs={12} md={4}>
            <ActionCard
              title="Install Piper TTS — IIS"
              description="Piper with IIS reverse proxy for HTTPS."
              action="/run/piper_windows_iis"
              fields={commonFields}
              onRun={run}
              color="#d97706"
            />
          </Grid>
        )}

        {/* ── Status ── */}
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: "#b45309" }}>Piper Status</Typography>
              <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
              <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>
              <Typography variant="body2">Port: <b>{httpPort}</b></Typography>
              {httpUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>URL: <a href={httpUrl} target="_blank" rel="noopener">{httpUrl}</a></Typography>}
              <Typography variant="body2">Voice: <b>{voice}</b></Typography>
              {bestUrl && running && (
                <Button
                  variant="contained" size="small" sx={{ mt: 1, textTransform: "none", bgcolor: "#b45309" }}
                  onClick={() => window.open(bestUrl, "_blank", "noopener,noreferrer")}
                >
                  Open Piper API
                </Button>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* ── Test TTS ── */}
        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 3, border: running ? "1px solid #b4530933" : "1px solid #dbe5f6", opacity: running ? 1 : 0.6 }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1.5, color: "#b45309" }}>Test TTS</Typography>
              {!running && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Start Piper to test text-to-speech.
                </Typography>
              )}
              <Stack spacing={1.5}>
                <TextField
                  size="small"
                  label="Text to speak"
                  placeholder="Enter text to convert to speech..."
                  value={ttsText}
                  onChange={(e) => setTtsText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSpeak(); } }}
                  disabled={!running || ttsLoading}
                  multiline
                  minRows={2}
                  maxRows={5}
                  fullWidth
                />
                <Stack direction="row" spacing={1} alignItems="center">
                  <Button
                    variant="contained"
                    disabled={!running || ttsLoading || !ttsText.trim()}
                    onClick={handleSpeak}
                    sx={{ textTransform: "none", bgcolor: "#b45309", minWidth: 100 }}
                  >
                    {ttsLoading ? "Generating..." : "Speak"}
                  </Button>
                  {ttsAudioUrl && (
                    <Typography variant="caption" color="text.secondary">Audio ready — use the player below.</Typography>
                  )}
                </Stack>
                <Box>
                  <audio ref={audioRef} controls style={{ width: "100%", display: ttsAudioUrl ? "block" : "none" }} src={ttsAudioUrl} />
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Services List ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6" fontWeight={800}>Piper Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading("piper")} onClick={() => { if (loadInfo?.current) loadInfo.current(); if (loadServices?.current) loadServices.current(); }} sx={{ textTransform: "none" }}>
                  {isScopeLoading("piper") ? "Refreshing..." : "Refresh"}
                </Button>
              </Stack>
              {scopeErrors.piper && <Alert severity="error" sx={{ mb: 1 }}>{scopeErrors.piper}</Alert>}
              {services.length === 0 && (
                <Typography variant="body2" color="text.secondary">No Piper services deployed yet. Use an Install card above.</Typography>
              )}
              {services.map((svc) => (
                <Paper key={`piper-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                    <Box sx={{ minWidth: 250 }}>
                      <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                      {renderServiceUrls(svc)}
                      {renderServicePorts(svc)}
                    </Box>
                    {renderServiceStatus(svc)}
                    <Box sx={{ flexGrow: 1 }} />
                    {renderFolderIcon(svc)}
                    {svc.manageable !== false && (
                      <>
                        <Button size="small" variant="outlined" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"} disabled={serviceBusy} onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)} sx={{ textTransform: "none" }}>
                          {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                        </Button>
                        <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>Restart</Button>
                      </>
                    )}
                    {svc.deletable && (
                      <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                    )}
                  </Stack>
                </Paper>
              ))}
            </CardContent>
          </Card>
        </Grid>

        {/* ── API Docs ── */}
        {ns.renderApiDocs && ns.apiDocs && ns.apiDocs.piper && ns.renderApiDocs(p, ns.apiDocs.piper)}
      </Grid>
    );
  };
})();
