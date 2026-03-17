(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  // Default ports auto-increment across instances
  function makeDefaultInstance(index, selectableIps) {
    const base = index * 10;
    return {
      id: Date.now() + index,
      instanceName: index === 0 ? "localmongo" : `localmongo${index + 1}`,
      hostIp: selectableIps.length === 1 ? selectableIps[0] : "",
      mongoPort: String(27017 + base),
      httpsPort: String(9445 + base),
      httpPort: "",
      webPort: String(8081 + base),
      adminUser: "admin",
      adminPassword: "StrongPassword123",
      uiUser: "admin",
      uiPassword: "StrongPassword123",
    };
  }

  function MongoNativeInner(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      TextField, Select, MenuItem, FormControl, InputLabel, Alert,
      ActionIcon,
      cfg, run, selectableIps, serviceBusy,
      mongo, mongoWebsiteUrl, mongoDisplayServices,
      mongoCompassDownloadUrl, mongoCompassUri,
      isScopeLoading, loadMongoInfo, loadMongoServices,
      hasStoppedServices, batchServiceAction, copyText, tryOpenCompass, promptOpenMongoWebsite,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts,
      DownloadCompassIcon, CopyCompassIcon, TryOpenCompassIcon, OpenCompassStyleIcon,
      setPage, setFileManagerPath,
    } = p;

    const nativeServices = (mongoDisplayServices || []).filter(
      (s) => String(s.kind || "").toLowerCase() !== "docker"
    );

    const [instances, setInstances] = React.useState(() => [makeDefaultInstance(0, selectableIps)]);
    const [deployingIdx, setDeployingIdx] = React.useState(null);
    const [deployErrors, setDeployErrors] = React.useState({});

    // Keep first instance's IP in sync when selectableIps loads
    React.useEffect(() => {
      if (selectableIps.length === 1) {
        setInstances((prev) => prev.map((inst) =>
          inst.hostIp ? inst : { ...inst, hostIp: selectableIps[0] }
        ));
      }
    }, [selectableIps]);

    function updateInstance(id, field, value) {
      setInstances((prev) => prev.map((inst) => inst.id === id ? { ...inst, [field]: value } : inst));
    }

    function addInstance() {
      setInstances((prev) => [...prev, makeDefaultInstance(prev.length, selectableIps)]);
    }

    function removeInstance(id) {
      setInstances((prev) => prev.length > 1 ? prev.filter((i) => i.id !== id) : prev);
    }

    // Deploy one instance by building a hidden form and calling run()
    function deployOne(inst, e) {
      const form = document.createElement("form");
      const fields = {
        LOCALMONGO_INSTANCE_NAME: inst.instanceName,
        LOCALMONGO_HOST_IP: inst.hostIp,
        LOCALMONGO_MONGO_PORT: inst.mongoPort,
        LOCALMONGO_HTTPS_PORT: inst.httpsPort,
        LOCALMONGO_HTTP_PORT: inst.httpPort,
        LOCALMONGO_WEB_PORT: inst.webPort,
        LOCALMONGO_ADMIN_USER: inst.adminUser,
        LOCALMONGO_ADMIN_PASSWORD: inst.adminPassword,
        LOCALMONGO_UI_USER: inst.uiUser,
        LOCALMONGO_UI_PASSWORD: inst.uiPassword,
      };
      Object.entries(fields).forEach(([name, value]) => {
        const inp = document.createElement("input");
        inp.name = name; inp.value = value || "";
        form.appendChild(inp);
      });
      const action = cfg.os === "windows" ? "/run/mongo_windows" : "/run/mongo_unix";
      const title = `Install MongoDB — ${inst.instanceName}`;
      run(e, action, title, form);
    }

    // Deploy all instances sequentially (fire first immediately, rest depend on UI streaming)
    function deployAll(e) {
      instances.forEach((inst, idx) => {
        // Each fires a separate run() — they will queue or open separate output windows
        // We fire them all; the streaming pane shows the last one
        deployOne(inst, e);
      });
    }

    function InstanceRow({ inst, idx }) {
      return (
        <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, borderRadius: 2, border: "1px solid #e0e7ff" }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems="flex-start" flexWrap="wrap">
            {/* Instance name */}
            <TextField
              label="Instance Name" size="small" sx={{ minWidth: 160 }}
              value={inst.instanceName}
              onChange={(e) => updateInstance(inst.id, "instanceName", e.target.value)}
              helperText="Unique ID (letters, numbers, -)"
            />
            {/* IP */}
            {selectableIps.length > 1 ? (
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <InputLabel>Bind IP</InputLabel>
                <Select label="Bind IP" value={inst.hostIp} onChange={(e) => updateInstance(inst.id, "hostIp", e.target.value)}>
                  {selectableIps.map((ip) => <MenuItem key={ip} value={ip}>{ip}</MenuItem>)}
                </Select>
              </FormControl>
            ) : (
              <TextField label="Bind IP" size="small" sx={{ minWidth: 140 }} value={inst.hostIp} disabled />
            )}
            {/* Ports */}
            <TextField label="MongoDB Port" size="small" sx={{ minWidth: 120 }} value={inst.mongoPort} onChange={(e) => updateInstance(inst.id, "mongoPort", e.target.value)} />
            <TextField label="HTTPS Port" size="small" sx={{ minWidth: 110 }} value={inst.httpsPort} onChange={(e) => updateInstance(inst.id, "httpsPort", e.target.value)} placeholder="skip if empty" />
            <TextField label="HTTP Port" size="small" sx={{ minWidth: 110 }} value={inst.httpPort} onChange={(e) => updateInstance(inst.id, "httpPort", e.target.value)} placeholder="skip if empty" />
            <TextField label="Web UI Port" size="small" sx={{ minWidth: 110 }} value={inst.webPort} onChange={(e) => updateInstance(inst.id, "webPort", e.target.value)} />
            {/* Credentials */}
            <TextField label="Admin User" size="small" sx={{ minWidth: 110 }} value={inst.adminUser} onChange={(e) => updateInstance(inst.id, "adminUser", e.target.value)} />
            <TextField label="Admin Password" size="small" sx={{ minWidth: 140 }} type="password" value={inst.adminPassword} onChange={(e) => updateInstance(inst.id, "adminPassword", e.target.value)} />
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} alignItems="center">
            <Button
              size="small" variant="contained"
              disabled={serviceBusy || !inst.instanceName.trim() || !inst.mongoPort.trim()}
              onClick={(e) => deployOne(inst, e)}
              sx={{ textTransform: "none", bgcolor: "#7c3aed", "&:hover": { bgcolor: "#6d28d9" }, fontWeight: 700 }}
            >
              Deploy Instance
            </Button>
            {instances.length > 1 && (
              <Button size="small" variant="outlined" color="error" onClick={() => removeInstance(inst.id)} sx={{ textTransform: "none" }}>
                Remove
              </Button>
            )}
            <Typography variant="caption" color="text.secondary">
              Instance #{idx + 1}
            </Typography>
          </Stack>
        </Paper>
      );
    }

    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                <Typography variant="h6" fontWeight={800}>
                  {cfg.os === "windows" ? "Install MongoDB (Windows Native)" : `Install MongoDB (${cfg.os === "linux" ? "Linux" : "macOS"})`}
                </Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button
                  size="small" variant="outlined"
                  onClick={addInstance}
                  sx={{ textTransform: "none", fontWeight: 700 }}
                >
                  + Add Instance
                </Button>
                {instances.length > 1 && (
                  <Button
                    size="small" variant="contained"
                    disabled={serviceBusy}
                    onClick={deployAll}
                    sx={{ textTransform: "none", bgcolor: "#7c3aed", "&:hover": { bgcolor: "#6d28d9" }, fontWeight: 700 }}
                  >
                    Deploy All ({instances.length})
                  </Button>
                )}
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Each instance gets its own service name and ports. Add as many as you need — each will run as a separate MongoDB service.
              </Typography>
              {instances.map((inst, idx) => (
                <InstanceRow key={inst.id} inst={inst} idx={idx} />
              ))}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Status</Typography>
              <Typography variant="body2">MongoDB: {mongo.installed ? `Installed (${mongo.server_version || "native"})` : "Not installed yet"}</Typography>
              {!!mongo.web_version && <Typography variant="body2">Web Version: {mongo.web_version}</Typography>}
              {!!mongoWebsiteUrl && <Typography variant="body2" sx={{ mt: 1 }}>HTTPS URL: {mongoWebsiteUrl}</Typography>}
              {!!mongo.connection_string && <Typography variant="body2">Connection: {mongo.connection_string}</Typography>}
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1.5, display: "block" }}>
                Instances planned: {instances.length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Native MongoDB Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <ActionIcon title="Download Compass" onClick={() => window.open(mongoCompassDownloadUrl, "_blank", "noopener,noreferrer")} IconComp={DownloadCompassIcon} fallback="DL" />
                <ActionIcon title="Copy Compass URI" onClick={() => copyText(mongoCompassUri, "Compass connection URI")} IconComp={CopyCompassIcon} fallback="CP" />
                <ActionIcon title="Try Open Compass" onClick={tryOpenCompass} IconComp={TryOpenCompassIcon} fallback="OP" />
                {!!mongoWebsiteUrl && (
                  <ActionIcon title="Open Compass-Style UI" disabled={serviceBusy} onClick={promptOpenMongoWebsite} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                )}
                <Button variant="outlined" disabled={isScopeLoading("mongo")} onClick={() => Promise.all([loadMongoInfo.current(), loadMongoServices.current()])} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}>
                  Refresh
                </Button>
                {nativeServices.length > 0 && (
                  <Button
                    variant="contained"
                    color={hasStoppedServices(nativeServices) ? "success" : "error"}
                    disabled={serviceBusy}
                    onClick={() => batchServiceAction(nativeServices, "MongoDB", hasStoppedServices(nativeServices) ? "start" : "stop")}
                    sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                  >
                    {hasStoppedServices(nativeServices) ? "Start All" : "Stop All"}
                  </Button>
                )}
              </Stack>
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
                {nativeServices.length === 0 && (
                  <Typography variant="body2" color="text.secondary">No native MongoDB services found. Install above to see services here.</Typography>
                )}
                {nativeServices.map((svc) => (
                  <Paper key={`mgn-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Typography variant="body2"><b>{svc.name}</b> <Typography component="span" variant="caption" color="text.secondary">({svc.kind || "service"})</Typography></Typography>
                        {renderServiceUrls(svc)}
                        {renderServicePorts(svc)}
                      </Box>
                      <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status) || "-"} />
                      <Box sx={{ flexGrow: 1 }} />
                      {!!(svc.project_path && setFileManagerPath && setPage) && (
                        <Button size="small" variant="outlined" onClick={() => { setFileManagerPath(svc.project_path); setPage("files"); }} sx={{ textTransform: "none" }}>Open Folder</Button>
                      )}
                      <Button size="small" variant="outlined" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"} disabled={serviceBusy} onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)} sx={{ textTransform: "none" }}>
                        {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                      </Button>
                      <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>Restart</Button>
                      <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                    </Stack>
                  </Paper>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  }

  ns.pages["mongo-native"] = function renderMongoNativePage(p) {
    return React.createElement(MongoNativeInner, p);
  };
})();
