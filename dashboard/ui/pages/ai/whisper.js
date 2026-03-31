(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["ai-whisper"] = function renderWhisperPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Alert,
      ActionCard, NavCard, TextField, FormControl, InputLabel, Select, MenuItem,
      cfg, run, selectableIps, serviceBusy,
      isScopeLoading, scopeErrors,
      isServiceRunningStatus, formatServiceState, onServiceAction, IconOnlyAction, FolderIcon,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      setPage, setInfoMessage, setFileManagerPath,
    } = p;

    const whisperInfo = (p.whisperService) || {};
    const services = p.whisperPageServices || [];
    const loadInfo = p.loadWhisperInfo;
    const loadServices = p.loadWhisperServices;

    const httpUrl = String(whisperInfo.http_url || "").trim();
    const httpsUrl = String(whisperInfo.https_url || "").trim();
    const httpPort = String(whisperInfo.http_port || "9000").trim();
    const installed = !!whisperInfo.installed;
    const running = !!whisperInfo.running;
    const modelSize = String(whisperInfo.model_size || "base").trim();
    const httpsPort = String(whisperInfo.https_port || "").trim();
    const bestUrl = httpsUrl || httpUrl || (installed && httpsPort ? `https://127.0.0.1:${httpsPort}` : installed ? `http://127.0.0.1:${httpPort}` : "");

    // Test transcription state
    const [audioFile, setAudioFile] = React.useState(null);
    const [transcribing, setTranscribing] = React.useState(false);
    const [transcription, setTranscription] = React.useState("");
    const [transcriptionError, setTranscriptionError] = React.useState("");
    const fileInputRef = React.useRef(null);

    // Handle file selection
    const handleFileSelect = React.useCallback((e) => {
      const file = e.target.files && e.target.files[0];
      if (file) {
        setAudioFile(file);
        setTranscription("");
        setTranscriptionError("");
      }
    }, []);

    // Handle transcription
    const handleTranscribe = React.useCallback(async () => {
      if (!audioFile) return;
      setTranscribing(true);
      setTranscription("");
      setTranscriptionError("");
      try {
        const formData = new FormData();
        formData.append("file", audioFile);
        formData.append("model", "whisper-1");
        const url = bestUrl.replace(/\/$/, "") + "/v1/audio/transcriptions";
        const r = await fetch(url, {
          method: "POST",
          body: formData,
        });
        if (!r.ok) {
          const errText = await r.text();
          setTranscriptionError(`HTTP ${r.status}: ${errText}`);
        } else {
          const j = await r.json();
          setTranscription(j.text || JSON.stringify(j, null, 2));
        }
      } catch (e) {
        setTranscriptionError(`Error: ${e}`);
      }
      setTranscribing(false);
    }, [audioFile, bestUrl]);

    const installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : (cfg.os === "darwin" ? "macOS" : cfg.os_label));

    const commonFields = [
      { name: "WHISPER_HOST_IP", label: "Host IP", type: "select", options: selectableIps, defaultValue: selectableIps[0] || "", required: true, placeholder: "Select IP" },
      { name: "WHISPER_HTTP_PORT", label: "HTTP Port", defaultValue: httpPort || "9000", checkPort: true },
      { name: "WHISPER_HTTPS_PORT", label: "HTTPS Port (optional)", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty to skip HTTPS" },
      { name: "WHISPER_DOMAIN", label: "Domain (optional)", defaultValue: whisperInfo.domain || "", placeholder: "e.g. whisper.example.com" },
      { name: "WHISPER_USERNAME", label: "Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "WHISPER_PASSWORD", label: "Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "WHISPER_MODEL_SIZE", label: "Model Size", type: "select", options: [
        { value: "tiny", label: "tiny" },
        { value: "base", label: "base" },
        { value: "small", label: "small" },
        { value: "medium", label: "medium" },
        { value: "large-v3", label: "large-v3" },
      ], defaultValue: "base" },
    ];

    return (
      <Grid container spacing={2}>
        {/* ── Description ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#0d9488" }}>
                Whisper — Speech to Text
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                OpenAI's Whisper model for automatic speech recognition. Transcribe and translate audio in 99+ languages.
                Runs locally with GPU acceleration or CPU fallback.
              </Typography>
              <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                Whisper 'tiny' and 'base' models run well on CPU. For 'medium' and 'large' models, a GPU with 4+ GB VRAM is recommended.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Install Cards ── */}
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title={`Install Whisper — OS (${installOsLabel})`}
            description="Install Whisper as a managed OS service. Downloads the model and configures auto-start."
            action={cfg.os === "windows" ? "/run/whisper_windows_os" : "/run/whisper_unix_os"}
            fields={commonFields}
            onRun={run}
            color="#0d9488"
          />
        </Grid>
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title="Install Whisper — Docker"
            description="Deploy Whisper in a Docker container with optional GPU passthrough."
            action="/run/whisper_docker"
            fields={commonFields}
            onRun={run}
            color="#0891b2"
          />
        </Grid>
        {cfg.os === "windows" && (
          <Grid item xs={12} md={4}>
            <ActionCard
              title="Install Whisper — IIS"
              description="Whisper with IIS reverse proxy for HTTPS."
              action="/run/whisper_windows_iis"
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
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: "#0d9488" }}>Whisper Status</Typography>
              <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
              <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>
              <Typography variant="body2">Port: <b>{httpPort}</b></Typography>
              {httpUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>URL: <a href={httpUrl} target="_blank" rel="noopener">{httpUrl}</a></Typography>}
              <Typography variant="body2">Model Size: <b>{modelSize}</b></Typography>
              {bestUrl && running && (
                <Button
                  variant="contained" size="small" sx={{ mt: 1, textTransform: "none", bgcolor: "#0d9488" }}
                  onClick={() => window.open(bestUrl, "_blank", "noopener,noreferrer")}
                >
                  Open Whisper API
                </Button>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* ── Test Transcription ── */}
        {running && (
          <Grid item xs={12} md={8}>
            <Card sx={{ borderRadius: 3, border: "1px solid #0d948833" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1.5, color: "#0d9488" }}>Test Transcription</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Upload an audio file to test speech-to-text transcription. Supports mp3, wav, m4a, webm, mp4, flac, ogg, and more.
                </Typography>

                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems="center" sx={{ mb: 2 }}>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="audio/*,.mp3,.wav,.m4a,.webm,.mp4,.flac,.ogg"
                    style={{ display: "none" }}
                    onChange={handleFileSelect}
                  />
                  <Button
                    variant="outlined"
                    onClick={() => fileInputRef.current && fileInputRef.current.click()}
                    sx={{ textTransform: "none", borderColor: "#0d9488", color: "#0d9488" }}
                  >
                    {audioFile ? "Change File" : "Select Audio File"}
                  </Button>
                  {audioFile && (
                    <Chip label={audioFile.name} size="small" onDelete={() => { setAudioFile(null); setTranscription(""); setTranscriptionError(""); if (fileInputRef.current) fileInputRef.current.value = ""; }} />
                  )}
                  <Button
                    variant="contained"
                    disabled={!audioFile || transcribing}
                    onClick={handleTranscribe}
                    sx={{ textTransform: "none", bgcolor: "#0d9488", minWidth: 120 }}
                  >
                    {transcribing ? "Transcribing..." : "Transcribe"}
                  </Button>
                </Stack>

                {transcriptionError && (
                  <Alert severity="error" sx={{ mb: 1.5, borderRadius: 2 }}>{transcriptionError}</Alert>
                )}

                {transcription && (
                  <Paper elevation={0} sx={{ bgcolor: "#f0fdfa", border: "1px solid #99f6e4", borderRadius: 2, p: 2 }}>
                    <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ display: "block", mb: 0.5 }}>Transcription Result:</Typography>
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{transcription}</Typography>
                  </Paper>
                )}

                {!transcription && !transcriptionError && !transcribing && (
                  <Paper elevation={0} sx={{ bgcolor: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 2, p: 2, textAlign: "center" }}>
                    <Typography variant="body2" color="text.secondary">
                      Select an audio file and click "Transcribe" to see the result here.
                    </Typography>
                  </Paper>
                )}
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* ── Services List ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6" fontWeight={800}>Whisper Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading("whisper")} onClick={() => { if (loadInfo?.current) loadInfo.current(); if (loadServices?.current) loadServices.current(); }} sx={{ textTransform: "none" }}>
                  {isScopeLoading("whisper") ? "Refreshing..." : "Refresh"}
                </Button>
              </Stack>
              {scopeErrors.whisper && <Alert severity="error" sx={{ mb: 1 }}>{scopeErrors.whisper}</Alert>}
              {services.length === 0 && (
                <Typography variant="body2" color="text.secondary">No Whisper services deployed yet. Use an Install card above.</Typography>
              )}
              {services.map((svc) => (
                <Paper key={`whisper-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
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
        {ns.renderApiDocs && ns.apiDocs && ns.apiDocs.whisper && ns.renderApiDocs(p, ns.apiDocs.whisper)}
      </Grid>
    );
  };
})();
