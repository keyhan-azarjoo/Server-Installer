(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.ssl = function renderSslPage(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      TextField, MenuItem, Select, FormControl, InputLabel,
      Dialog, DialogTitle, DialogContent, DialogActions,
      CircularProgress,
      cfg, run, serviceBusy,
      isScopeLoading,
    } = p;

    // ── State ─────────────────────────────────────────────────────────────────
    const [certs, setCerts]         = React.useState([]);
    const [certsLoading, setCL]     = React.useState(false);
    const [certsError, setCE]       = React.useState("");

    // Let's Encrypt form
    const [leTab, setLeTab]         = React.useState("http"); // http | dns
    const [leDomain, setLeDomain]   = React.useState("");
    const [leEmail, setLeEmail]     = React.useState("");
    const [leExtra, setLeExtra]     = React.useState("");
    const [leBusy, setLeBusy]       = React.useState(false);

    // Upload form
    const [upDomain, setUpDomain]   = React.useState("");
    const [upCertPem, setUpCertPem] = React.useState("");
    const [upKeyPem, setUpKeyPem]   = React.useState("");
    const [upChainPem, setUpChainPem] = React.useState("");
    const [upPfxFile, setUpPfxFile] = React.useState(null);
    const [upPfxPwd, setUpPfxPwd]   = React.useState("");
    const [upMode, setUpMode]       = React.useState("pem"); // pem | pfx
    const [upBusy, setUpBusy]       = React.useState(false);
    const [upMsg, setUpMsg]         = React.useState(null); // {ok, text}

    // Assign dialog
    const [assignDlg, setAssignDlg] = React.useState(null); // { certName }
    const [asKind, setAsKind]       = React.useState("custom"); // iis | nginx | custom
    const [asSite, setAsSite]       = React.useState("");
    const [asCertDest, setAsCertDest] = React.useState("");
    const [asKeyDest, setAsKeyDest]   = React.useState("");
    const [asRestart, setAsRestart]   = React.useState(true);
    const assignFormRef = React.useRef(null);
    const assignHiddenRef = React.useRef({});

    // ── Load certs ────────────────────────────────────────────────────────────
    const loadCerts = React.useCallback(async () => {
      setCL(true); setCE("");
      try {
        const r = await fetch("/api/ssl/list", { headers: { "X-Requested-With": "fetch" } });
        const j = await r.json();
        if (j.ok) setCerts(j.certs || []);
        else setCE(j.error || "Failed to load certificates.");
      } catch (ex) {
        setCE(String(ex));
      } finally {
        setCL(false);
      }
    }, []);

    React.useEffect(() => { loadCerts(); }, []);

    // ── Delete cert ───────────────────────────────────────────────────────────
    const deleteCert = React.useCallback(async (name) => {
      if (!window.confirm(`Delete certificate '${name}'? This cannot be undone.`)) return;
      try {
        const fd = new FormData();
        fd.append("SSL_CERT_NAME", name);
        const r = await fetch("/api/ssl/delete", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
        const j = await r.json();
        if (j.ok) loadCerts();
        else alert(j.message || j.error || "Delete failed.");
      } catch (ex) {
        alert(String(ex));
      }
    }, [loadCerts]);

    // ── Let's Encrypt submit ──────────────────────────────────────────────────
    const leFormRef = React.useRef(null);
    const handleLeSubmit = React.useCallback((e) => {
      e.preventDefault();
      run(e, "/run/ssl_letsencrypt", `Let's Encrypt — ${leDomain}`, leFormRef.current);
    }, [run, leDomain]);

    // ── Upload submit ─────────────────────────────────────────────────────────
    const handleUpload = React.useCallback(async (e) => {
      e.preventDefault();
      setUpBusy(true); setUpMsg(null);
      try {
        const fd = new FormData();
        fd.append("SSL_DOMAIN", upDomain);
        fd.append("SSL_CERT_NAME", upDomain);
        if (upMode === "pem") {
          fd.append("SSL_CERT_PEM", upCertPem);
          fd.append("SSL_KEY_PEM", upKeyPem);
          fd.append("SSL_CHAIN_PEM", upChainPem);
        } else {
          if (upPfxFile) fd.append("pfx_file", upPfxFile, upPfxFile.name);
          fd.append("SSL_PFX_PASSWORD", upPfxPwd);
        }
        const r = await fetch("/api/ssl/upload", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
        const j = await r.json();
        setUpMsg({ ok: j.ok, text: j.message || j.error || (j.ok ? "Saved." : "Failed.") });
        if (j.ok) {
          loadCerts();
          setUpCertPem(""); setUpKeyPem(""); setUpChainPem("");
          setUpPfxFile(null); setUpPfxPwd("");
        }
      } catch (ex) {
        setUpMsg({ ok: false, text: String(ex) });
      } finally {
        setUpBusy(false);
      }
    }, [upMode, upDomain, upCertPem, upKeyPem, upChainPem, upPfxFile, upPfxPwd, loadCerts]);

    // ── Assign cert ───────────────────────────────────────────────────────────
    const handleAssign = React.useCallback((e) => {
      e.preventDefault();
      if (!assignDlg) return;
      run(e, "/run/ssl_assign", `Assign certificate — ${assignDlg.certName}`, assignFormRef.current);
      setAssignDlg(null);
    }, [run, assignDlg]);

    // ── Renew all ─────────────────────────────────────────────────────────────
    const renewFormRef = React.useRef(null);
    const handleRenew = React.useCallback((e) => {
      e.preventDefault();
      run(e, "/run/ssl_renew", "Renew SSL Certificates", renewFormRef.current);
    }, [run]);

    // ── Helpers ───────────────────────────────────────────────────────────────
    const isExpiringSoon = (notAfter) => {
      if (!notAfter) return false;
      try {
        const d = new Date(notAfter);
        const diff = (d - Date.now()) / 86400000;
        return diff < 30;
      } catch (_) { return false; }
    };
    const isExpired = (notAfter) => {
      if (!notAfter) return false;
      try { return new Date(notAfter) < new Date(); } catch (_) { return false; }
    };

    return (
      <Grid container spacing={2}>

        {/* ── Managed Certificates list ── */}
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Managed Certificates</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <form ref={renewFormRef} style={{ display: "inline" }}>
                  <Button variant="outlined" onClick={handleRenew} disabled={serviceBusy}
                    sx={{ textTransform: "none" }}>
                    Renew All (Let's Encrypt)
                  </Button>
                </form>
                <Button variant="outlined" onClick={loadCerts} disabled={certsLoading} sx={{ textTransform: "none" }}>
                  {certsLoading ? "Loading…" : "Refresh"}
                </Button>
              </Stack>
              {certsError && <Alert severity="error" sx={{ mt: 1 }}>{certsError}</Alert>}
              <Box sx={{ mt: 1.5, flexGrow: 1, minHeight: "calc(100vh - 620px)", overflow: "auto" }}>
                {certs.length === 0 && !certsLoading && (
                  <Typography variant="body2" color="text.secondary">
                    No managed certificates yet. Use Let's Encrypt or upload your own below.
                  </Typography>
                )}
                {certs.map((cert) => {
                  const expired = isExpired(cert.not_after);
                  const expiringSoon = !expired && isExpiringSoon(cert.not_after);
                  return (
                    <Paper key={cert.name} variant="outlined"
                      sx={{ p: 1.25, mb: 1, borderRadius: 2, borderColor: expired ? "#ef4444" : expiringSoon ? "#f59e0b" : undefined }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                        <Box sx={{ minWidth: 300 }}>
                          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.25 }}>
                            <Typography variant="body2" fontWeight={700}>{cert.domain}</Typography>
                            {cert.self_signed && <Chip label="Self-Signed" size="small" color="warning" />}
                            {!cert.self_signed && <Chip label="CA-Signed" size="small" color="success" />}
                            {cert.source === "letsencrypt" && <Chip label="Let's Encrypt" size="small" color="info" />}
                          </Stack>
                          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                            Issuer: {cert.issuer || "unknown"}
                          </Typography>
                          <Typography variant="caption"
                            color={expired ? "error" : expiringSoon ? "warning.main" : "text.secondary"}
                            sx={{ display: "block" }}>
                            Expires: {cert.not_after || "unknown"}
                            {expired && " — EXPIRED"}
                            {expiringSoon && !expired && " — expiring soon"}
                          </Typography>
                          {cert.sans && cert.sans.length > 0 && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", wordBreak: "break-all" }}>
                              SANs: {cert.sans.join(", ")}
                            </Typography>
                          )}
                          <Typography variant="caption" color="text.secondary"
                            sx={{ display: "block", wordBreak: "break-all", mt: 0.25 }}>
                            {cert.cert_path}
                          </Typography>
                        </Box>
                        <Box sx={{ flexGrow: 1 }} />
                        <Button size="small" variant="contained" color="primary"
                          onClick={() => {
                            setAssignDlg({ certName: cert.name });
                            setAsKind(cfg.os === "windows" ? "iis" : "nginx");
                            setAsSite(""); setAsCertDest(""); setAsKeyDest("");
                          }}
                          sx={{ textTransform: "none" }}>
                          Assign to Service
                        </Button>
                        <Button size="small" variant="outlined" color="error"
                          onClick={() => deleteCert(cert.name)}
                          sx={{ textTransform: "none" }}>
                          Delete
                        </Button>
                      </Stack>
                    </Paper>
                  );
                })}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Let's Encrypt ── */}
        <Grid item xs={12} md={6}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>
                Free Certificate — Let's Encrypt
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Get a trusted, free 90-day certificate from Let's Encrypt using certbot.
                Requires certbot to be installed (auto-installed if missing on Linux).
              </Typography>

              {/* Challenge type tabs */}
              <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
                {[{ id: "http", label: "HTTP-01 Challenge" }, { id: "dns", label: "DNS-01 Challenge" }].map((t) => (
                  <Button key={t.id} size="small" variant={leTab === t.id ? "contained" : "outlined"}
                    onClick={() => setLeTab(t.id)}
                    sx={{ textTransform: "none" }}>
                    {t.label}
                  </Button>
                ))}
              </Stack>

              {leTab === "http" && (
                <Alert severity="info" sx={{ mb: 2, py: 0.5 }}>
                  HTTP-01: certbot temporarily listens on port 80. Port 80 must be open and your domain's A/AAAA record must point to this server's public IP.
                </Alert>
              )}
              {leTab === "dns" && (
                <Alert severity="info" sx={{ mb: 2, py: 0.5 }}>
                  DNS-01: You'll be prompted to add a TXT record to your DNS provider. Works even without port 80 open. Best for wildcard certs (*.example.com).
                </Alert>
              )}

              <form ref={leFormRef} onSubmit={handleLeSubmit}>
                <input type="hidden" name="SSL_CHALLENGE" value={leTab} />
                <Stack spacing={2}>
                  <TextField label="Domain (e.g. example.com or *.example.com)" size="small" required fullWidth
                    name="SSL_DOMAIN" value={leDomain}
                    onChange={(e) => setLeDomain(e.target.value)}
                    placeholder="example.com" />
                  <TextField label="Email (for Let's Encrypt notifications)" size="small" required fullWidth
                    name="SSL_EMAIL" value={leEmail}
                    onChange={(e) => setLeEmail(e.target.value)}
                    placeholder="admin@example.com" />
                  <TextField label="Additional domains (comma-separated, optional)" size="small" fullWidth
                    name="SSL_EXTRA_DOMAINS" value={leExtra}
                    onChange={(e) => setLeExtra(e.target.value)}
                    placeholder="www.example.com, api.example.com" />
                  <Button type="submit" variant="contained" disabled={serviceBusy || !leDomain || !leEmail}
                    sx={{ textTransform: "none", bgcolor: "#1d4ed8", "&:hover": { bgcolor: "#1e40af" }, fontWeight: 700 }}>
                    Get Certificate via Let's Encrypt
                  </Button>
                </Stack>
              </form>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Upload / Paste Certificate ── */}
        <Grid item xs={12} md={6}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>Upload Your Certificate</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Upload PEM files (.crt + .key + optional chain) or a PFX/P12 bundle.
                Certificates from any CA (Comodo, DigiCert, ZeroSSL, etc.) are supported.
              </Typography>

              <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
                {[{ id: "pem", label: "PEM / CRT + KEY" }, { id: "pfx", label: "PFX / P12" }].map((t) => (
                  <Button key={t.id} size="small" variant={upMode === t.id ? "contained" : "outlined"}
                    onClick={() => setUpMode(t.id)}
                    sx={{ textTransform: "none" }}>
                    {t.label}
                  </Button>
                ))}
              </Stack>

              {upMsg && (
                <Alert severity={upMsg.ok ? "success" : "error"} sx={{ mb: 1.5 }}
                  onClose={() => setUpMsg(null)}>
                  {upMsg.text}
                </Alert>
              )}

              <form onSubmit={handleUpload}>
                <Stack spacing={2}>
                  <TextField label="Domain / Certificate name" size="small" fullWidth
                    value={upDomain} onChange={(e) => setUpDomain(e.target.value)}
                    placeholder="example.com (auto-detected from cert if blank)" />

                  {upMode === "pem" && (<>
                    <Box>
                      <Typography variant="caption" fontWeight={700} sx={{ mb: 0.5, display: "block" }}>
                        Certificate (.crt / .pem) — paste PEM or upload file
                      </Typography>
                      <Stack direction="row" spacing={1} alignItems="flex-start">
                        <TextField multiline minRows={3} maxRows={6} size="small" fullWidth
                          value={upCertPem} onChange={(e) => setUpCertPem(e.target.value)}
                          placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                          sx={{ "& textarea": { fontFamily: "Consolas, monospace", fontSize: 11 } }} />
                        <Button component="label" size="small" variant="outlined" sx={{ textTransform: "none", flexShrink: 0 }}>
                          Browse
                          <input hidden type="file" accept=".pem,.crt,.cer"
                            onChange={(e) => { const f = e.target.files[0]; if (f) f.text().then(setUpCertPem); }} />
                        </Button>
                      </Stack>
                    </Box>
                    <Box>
                      <Typography variant="caption" fontWeight={700} sx={{ mb: 0.5, display: "block" }}>
                        Private Key (.key / .pem) — paste PEM or upload file
                      </Typography>
                      <Stack direction="row" spacing={1} alignItems="flex-start">
                        <TextField multiline minRows={3} maxRows={6} size="small" fullWidth
                          value={upKeyPem} onChange={(e) => setUpKeyPem(e.target.value)}
                          placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----"
                          sx={{ "& textarea": { fontFamily: "Consolas, monospace", fontSize: 11 } }} />
                        <Button component="label" size="small" variant="outlined" sx={{ textTransform: "none", flexShrink: 0 }}>
                          Browse
                          <input hidden type="file" accept=".pem,.key"
                            onChange={(e) => { const f = e.target.files[0]; if (f) f.text().then(setUpKeyPem); }} />
                        </Button>
                      </Stack>
                    </Box>
                    <Box>
                      <Typography variant="caption" fontWeight={700} sx={{ mb: 0.5, display: "block" }}>
                        CA Chain / Intermediate (optional — improves browser trust)
                      </Typography>
                      <Stack direction="row" spacing={1} alignItems="flex-start">
                        <TextField multiline minRows={2} maxRows={4} size="small" fullWidth
                          value={upChainPem} onChange={(e) => setUpChainPem(e.target.value)}
                          placeholder="-----BEGIN CERTIFICATE-----&#10;(intermediate/chain cert)&#10;-----END CERTIFICATE-----"
                          sx={{ "& textarea": { fontFamily: "Consolas, monospace", fontSize: 11 } }} />
                        <Button component="label" size="small" variant="outlined" sx={{ textTransform: "none", flexShrink: 0 }}>
                          Browse
                          <input hidden type="file" accept=".pem,.crt,.cer,.ca-bundle"
                            onChange={(e) => { const f = e.target.files[0]; if (f) f.text().then(setUpChainPem); }} />
                        </Button>
                      </Stack>
                    </Box>
                  </>)}

                  {upMode === "pfx" && (<>
                    <Box>
                      <Typography variant="caption" fontWeight={700} sx={{ mb: 0.5, display: "block" }}>
                        PFX / P12 file
                      </Typography>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" color={upPfxFile ? "text.primary" : "text.secondary"} sx={{ flexGrow: 1 }}>
                          {upPfxFile ? upPfxFile.name : "No file selected"}
                        </Typography>
                        <Button component="label" size="small" variant="outlined" sx={{ textTransform: "none", flexShrink: 0 }}>
                          Browse .pfx / .p12
                          <input hidden type="file" accept=".pfx,.p12"
                            onChange={(e) => setUpPfxFile(e.target.files[0] || null)} />
                        </Button>
                      </Stack>
                    </Box>
                    <TextField label="PFX Password (leave blank if none)" size="small" fullWidth type="password"
                      value={upPfxPwd} onChange={(e) => setUpPfxPwd(e.target.value)} />
                    <Alert severity="info" sx={{ py: 0.5 }}>
                      openssl must be installed on the server to convert PFX to PEM format.
                    </Alert>
                  </>)}

                  <Button type="submit" variant="contained" disabled={upBusy ||
                    (upMode === "pem" && (!upCertPem.trim() || !upKeyPem.trim())) ||
                    (upMode === "pfx" && !upPfxFile)}
                    sx={{ textTransform: "none", bgcolor: "#0f766e", "&:hover": { bgcolor: "#115e59" }, fontWeight: 700 }}>
                    {upBusy ? "Saving…" : "Save Certificate"}
                  </Button>
                </Stack>
              </form>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Info card ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>How to Use</Typography>
              <Grid container spacing={2}>
                {[
                  {
                    title: "1. Get or upload a certificate",
                    text: "Use Let's Encrypt for a free trusted cert (requires domain pointing to this server), or upload a cert you already have from any CA (Comodo, DigiCert, ZeroSSL, etc.).",
                  },
                  {
                    title: "2. Assign to a service",
                    text: "Click 'Assign to Service' on any saved cert. Choose the target: IIS (Windows — imports to Windows cert store + binds to site), nginx (updates ssl_certificate directives in config), or Custom Path (copies cert/key files to any location you specify).",
                  },
                  {
                    title: "3. Verify and restart",
                    text: "After assignment the service is optionally restarted automatically. Visit your domain over HTTPS to confirm the certificate is working. Let's Encrypt certs expire after 90 days — use 'Renew All' to refresh them.",
                  },
                ].map((item) => (
                  <Grid key={item.title} item xs={12} md={4}>
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, height: "100%" }}>
                      <Typography variant="body2" fontWeight={700} sx={{ mb: 0.5 }}>{item.title}</Typography>
                      <Typography variant="body2" color="text.secondary">{item.text}</Typography>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Assign to Service dialog ── */}
        {assignDlg && (
          <Dialog open onClose={() => setAssignDlg(null)} maxWidth="sm" fullWidth>
            <DialogTitle>Assign Certificate — {assignDlg.certName}</DialogTitle>
            <DialogContent>
              <form ref={assignFormRef} onSubmit={handleAssign} id="assignForm">
                <input type="hidden" name="SSL_CERT_NAME" value={assignDlg.certName} />
                <input type="hidden" name="SSL_SERVICE_KIND" value={asKind} />
                <input type="hidden" name="SSL_SITE_NAME" value={asSite} />
                <input type="hidden" name="SSL_CUSTOM_CERT_DEST" value={asCertDest} />
                <input type="hidden" name="SSL_CUSTOM_KEY_DEST" value={asKeyDest} />
                <input type="hidden" name="SSL_RESTART_SERVICE" value={String(asRestart)} />
                <Stack spacing={2} sx={{ mt: 1 }}>
                  <FormControl size="small" fullWidth>
                    <InputLabel>Service Type</InputLabel>
                    <Select label="Service Type" value={asKind} onChange={(e) => setAsKind(e.target.value)}>
                      {cfg.os === "windows" && <MenuItem value="iis">IIS (Windows — imports to cert store)</MenuItem>}
                      {(cfg.os === "linux" || cfg.os === "darwin") && <MenuItem value="nginx">nginx (updates ssl_certificate in config)</MenuItem>}
                      <MenuItem value="custom">Custom Path (copy files to any location)</MenuItem>
                    </Select>
                  </FormControl>

                  {asKind === "iis" && (
                    <TextField label="IIS Site Name (leave blank to import to store only)" size="small" fullWidth
                      value={asSite} onChange={(e) => setAsSite(e.target.value)}
                      placeholder="Default Web Site" />
                  )}

                  {asKind === "nginx" && (
                    <Alert severity="info" sx={{ py: 0.5 }}>
                      All nginx config files containing <code>ssl_certificate</code> will be updated to point to the new cert. nginx will be reloaded after.
                    </Alert>
                  )}

                  {asKind === "custom" && (<>
                    <TextField label="Destination path for certificate (cert.pem / fullchain.pem)" size="small" fullWidth required
                      value={asCertDest} onChange={(e) => setAsCertDest(e.target.value)}
                      placeholder={cfg.os === "windows" ? "C:\\certs\\cert.pem" : "/etc/myapp/cert.pem"} />
                    <TextField label="Destination path for private key (key.pem)" size="small" fullWidth required
                      value={asKeyDest} onChange={(e) => setAsKeyDest(e.target.value)}
                      placeholder={cfg.os === "windows" ? "C:\\certs\\key.pem" : "/etc/myapp/key.pem"} />
                  </>)}

                  <Stack direction="row" spacing={1} alignItems="center">
                    <input type="checkbox" id="asRestart" checked={asRestart}
                      onChange={(e) => setAsRestart(e.target.checked)} />
                    <Typography component="label" htmlFor="asRestart" variant="body2" sx={{ cursor: "pointer" }}>
                      Restart service after assignment
                    </Typography>
                  </Stack>
                </Stack>
              </form>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setAssignDlg(null)} sx={{ textTransform: "none" }}>Cancel</Button>
              <Button type="submit" form="assignForm" variant="contained" disabled={serviceBusy ||
                (asKind === "custom" && (!asCertDest.trim() || !asKeyDest.trim()))}
                onClick={handleAssign}
                sx={{ textTransform: "none" }}>
                Assign Certificate
              </Button>
            </DialogActions>
          </Dialog>
        )}
      </Grid>
    );
  };
})();
