(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  function makeDefaultDockerInstance(index) {
    const base = index * 10;
    return {
      id: Date.now() + index,
      instanceName: index === 0 ? "localmongo" : `localmongo${index + 1}`,
      mongoPort: String(27017 + base),
      httpsPort: String(9445 + base),
      httpPort: "",
      webPort: String(8081 + base),
      adminUser: "admin",
      adminPassword: "StrongPassword123",
    };
  }

  // Eye icons (same as Native tab)
  const EyeOpenSvg = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
    </svg>
  );
  const EyeOffSvg = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
    </svg>
  );

  // Defined OUTSIDE MongoDockerInner so React never remounts it on parent re-render
  function InstanceRow({ inst, idx, instances, cfg, serviceBusy, updateInstance, removeInstance, deployOne,
    existingInstanceNames,
    TextField, Stack, Button, Paper, Typography, InputAdornment, IconButton, Alert }) {
    const [showPwd, setShowPwd] = React.useState(false);
    const nameExists = existingInstanceNames && existingInstanceNames.has((inst.instanceName || "").trim().toLowerCase());
    return (
      <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, borderRadius: 2, border: "1px solid #d1fae5" }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems="flex-start" flexWrap="wrap">
          <TextField
            label="Instance Name" size="small" sx={{ minWidth: 160 }}
            value={inst.instanceName}
            onChange={(e) => updateInstance(inst.id, "instanceName", e.target.value)}
            helperText={nameExists ? "⚠ Name already exists" : "Unique ID (letters, numbers, -)"}
            FormHelperTextProps={{ sx: nameExists ? { color: "warning.main", fontWeight: 600 } : {} }}
            color={nameExists ? "warning" : undefined}
            focused={nameExists ? true : undefined}
          />
          <TextField label="MongoDB Port" size="small" sx={{ minWidth: 120 }} value={inst.mongoPort} onChange={(e) => updateInstance(inst.id, "mongoPort", e.target.value)} />
          <TextField
            label={cfg.os === "windows" ? "HTTPS Port (skip on Win)" : "HTTPS Port"}
            size="small" sx={{ minWidth: 130 }}
            value={inst.httpsPort}
            onChange={(e) => updateInstance(inst.id, "httpsPort", e.target.value)}
            placeholder="skip if empty"
          />
          <TextField label="HTTP Port" size="small" sx={{ minWidth: 110 }} value={inst.httpPort} onChange={(e) => updateInstance(inst.id, "httpPort", e.target.value)} placeholder="skip if empty" />
          <TextField label="Web UI Port" size="small" sx={{ minWidth: 110 }} value={inst.webPort} onChange={(e) => updateInstance(inst.id, "webPort", e.target.value)} />
          <TextField label="Admin User" size="small" sx={{ minWidth: 110 }} value={inst.adminUser} onChange={(e) => updateInstance(inst.id, "adminUser", e.target.value)} />
          <TextField
            label="Admin Password" size="small" sx={{ minWidth: 160 }}
            type={showPwd ? "text" : "password"}
            value={inst.adminPassword}
            onChange={(e) => updateInstance(inst.id, "adminPassword", e.target.value)}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton size="small" onClick={() => setShowPwd((v) => !v)} tabIndex={-1} edge="end">
                    {showPwd ? <EyeOffSvg /> : <EyeOpenSvg />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
        </Stack>
        {nameExists && (
          <Alert severity="warning" sx={{ mt: 1, py: 0.3, fontSize: "0.8rem" }}>
            An instance named <b>{inst.instanceName}</b> already exists. Deploying will overwrite it.
          </Alert>
        )}
        <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} alignItems="center">
          <Button
            size="small" variant="contained"
            disabled={serviceBusy || !inst.instanceName.trim() || !inst.mongoPort.trim()}
            onClick={(e) => deployOne(inst, e)}
            sx={{ textTransform: "none", bgcolor: "#166534", "&:hover": { bgcolor: "#14532d" }, fontWeight: 700 }}
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

  function MongoDockerInner(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      TextField, InputAdornment, IconButton, Alert,
      ActionIcon,
      cfg, run, serviceBusy,
      mongo, mongoWebsiteUrl, mongoDisplayServices,
      mongoCompassDownloadUrl, mongoCompassUri,
      isScopeLoading, loadMongoInfo, loadMongoServices,
      hasStoppedServices, batchServiceAction, copyText, tryOpenCompass, promptOpenMongoWebsite,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      DownloadCompassIcon, CopyCompassIcon, TryOpenCompassIcon, OpenCompassStyleIcon,
      setPage, setFileManagerPath,
    } = p;

    const dockerServices = (mongoDisplayServices || []).filter(
      (s) => String(s.kind || "").toLowerCase() === "docker"
    );

    function groupDockerServices(svcs) {
      const groups = {};
      svcs.forEach((svc) => {
        const raw = String(svc.name || "");
        const key = raw.includes("-") ? raw.split("-").slice(0, -1).join("-") || raw : raw;
        if (!groups[key]) groups[key] = [];
        groups[key].push(svc);
      });
      return groups;
    }

    const groups = groupDockerServices(dockerServices);

    const [instances, setInstances] = React.useState(() => [makeDefaultDockerInstance(0)]);

    // Set of existing instance names derived from live Docker services
    const existingInstanceNames = React.useMemo(() => {
      return new Set(
        dockerServices.map((s) => {
          const parts = s.name.split("-");
          return parts.slice(1).join("-").toLowerCase();
        })
      );
    }, [dockerServices]);

    function updateInstance(id, field, value) {
      setInstances((prev) => prev.map((inst) => inst.id === id ? { ...inst, [field]: value } : inst));
    }

    function addInstance() {
      setInstances((prev) => [...prev, makeDefaultDockerInstance(prev.length)]);
    }

    function removeInstance(id) {
      setInstances((prev) => prev.length > 1 ? prev.filter((i) => i.id !== id) : prev);
    }

    function deployOne(inst, e) {
      const form = document.createElement("form");
      const fields = {
        LOCALMONGO_INSTANCE_NAME: inst.instanceName,
        LOCALMONGO_MONGO_PORT: inst.mongoPort,
        LOCALMONGO_HTTPS_PORT: inst.httpsPort,
        LOCALMONGO_HTTP_PORT: inst.httpPort,
        LOCALMONGO_WEB_PORT: inst.webPort,
        LOCALMONGO_ADMIN_USER: inst.adminUser,
        LOCALMONGO_ADMIN_PASSWORD: inst.adminPassword,
        LOCALMONGO_UI_USER: inst.adminUser,
        LOCALMONGO_UI_PASSWORD: inst.adminPassword,
      };
      Object.entries(fields).forEach(([name, value]) => {
        const inp = document.createElement("input");
        inp.name = name; inp.value = value || "";
        form.appendChild(inp);
      });
      run(e, "/run/mongo_docker", `Deploy MongoDB Docker — ${inst.instanceName}`, form);
    }

    function deployAll(e) {
      instances.forEach((inst) => deployOne(inst, e));
    }

    const rowProps = {
      cfg, serviceBusy, updateInstance, removeInstance, deployOne, instances, existingInstanceNames,
      TextField, Stack, Button, Paper, Typography, InputAdornment, IconButton, Alert,
    };

    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                <Typography variant="h6" fontWeight={800}>Deploy MongoDB (Docker)</Typography>
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
                    sx={{ textTransform: "none", bgcolor: "#166534", "&:hover": { bgcolor: "#14532d" }, fontWeight: 700 }}
                  >
                    Deploy All ({instances.length})
                  </Button>
                )}
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {cfg.os === "windows"
                  ? "Each instance runs as separate Docker containers (MongoDB + mongo-express). HTTPS proxy is skipped on Windows — access directly via the Web UI port."
                  : "Each instance runs as separate Docker containers with an optional nginx HTTPS proxy. Add as many as you need — each gets its own ports and containers."}
              </Typography>
              {instances.map((inst, idx) => (
                <InstanceRow key={inst.id} inst={inst} idx={idx} {...rowProps} />
              ))}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Status</Typography>
              <Typography variant="body2">MongoDB: {mongo.installed ? `Installed (${mongo.server_version || "docker"})` : "Not deployed yet"}</Typography>
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
                <Typography variant="h6" fontWeight={800}>Docker MongoDB Containers</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <ActionIcon title="Download Compass" onClick={() => window.open(mongoCompassDownloadUrl, "_blank", "noopener,noreferrer")} IconComp={DownloadCompassIcon} fallback="DL" />
                <Button variant="outlined" disabled={isScopeLoading("mongo")} onClick={() => Promise.all([loadMongoInfo.current(), loadMongoServices.current()])} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}>
                  Refresh
                </Button>
                {dockerServices.length > 0 && (
                  <Button
                    variant="contained"
                    color={hasStoppedServices(dockerServices) ? "success" : "error"}
                    disabled={serviceBusy}
                    onClick={() => batchServiceAction(dockerServices, "MongoDB", hasStoppedServices(dockerServices) ? "start" : "stop")}
                    sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                  >
                    {hasStoppedServices(dockerServices) ? "Start All" : "Stop All"}
                  </Button>
                )}
              </Stack>
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
                {dockerServices.length === 0 && (
                  <Typography variant="body2" color="text.secondary">No Docker MongoDB containers found. Deploy above to see containers here.</Typography>
                )}
                {Object.entries(groups).map(([groupKey, svcs]) => (
                  <Paper key={groupKey} variant="outlined" sx={{ p: 1.5, mb: 1.5, borderRadius: 2, border: "1px solid #dbe5f6" }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }} sx={{ mb: 1 }}>
                      <Typography variant="subtitle2" fontWeight={700} sx={{ flexGrow: 1 }}>{groupKey}</Typography>
                      <ActionIcon title="Copy Compass URI" onClick={() => copyText(mongoCompassUri, "Compass connection URI")} IconComp={CopyCompassIcon} fallback="CP" />
                      <ActionIcon title="Try Open Compass" onClick={tryOpenCompass} IconComp={TryOpenCompassIcon} fallback="OP" />
                      {!!mongoWebsiteUrl && (
                        <ActionIcon title="Open UI" disabled={serviceBusy} onClick={promptOpenMongoWebsite} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                      )}
                      <Button size="small" variant="outlined" color={hasStoppedServices(svcs) ? "success" : "error"} disabled={serviceBusy} onClick={() => batchServiceAction(svcs, "MongoDB", hasStoppedServices(svcs) ? "start" : "stop")} sx={{ textTransform: "none", fontSize: 12 }}>
                        {hasStoppedServices(svcs) ? "Start Group" : "Stop Group"}
                      </Button>
                    </Stack>
                    {svcs.map((svc) => (
                      <Paper key={`mgd-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 0.75, borderRadius: 1.5, bgcolor: "#f8faff" }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 200 }}>
                            <Typography variant="body2"><b>{svc.name}</b> <Typography component="span" variant="caption" color="text.secondary">({svc.kind || "docker"})</Typography></Typography>
                            {svc.image && <Typography variant="caption" color="text.secondary">Image: {svc.image}</Typography>}
                            {renderServiceUrls(svc)}
                            {renderServicePorts(svc)}
                          </Box>
                          {renderServiceStatus(svc)}
                          <Box sx={{ flexGrow: 1 }} />
                          {renderFolderIcon(svc)}
                          <Button size="small" variant="outlined" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"} disabled={serviceBusy} onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)} sx={{ textTransform: "none" }}>
                            {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                          </Button>
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                        </Stack>
                      </Paper>
                    ))}
                  </Paper>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  }

  ns.pages["mongo-docker"] = function renderMongoDockerPage(p) {
    return React.createElement(MongoDockerInner, p);
  };
})();
