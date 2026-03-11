const {
  Box, Button, Card, CardContent, FormControl, InputAdornment, InputLabel, MenuItem, Select, TextField, Typography
} = MaterialUI;

function Field({ field }) {
  const isPassword = field.type === "password";
  const [showPassword, setShowPassword] = React.useState(false);
  if (field.type === "folder") {
    return (
      <Box sx={{ mb: 1.5 }}>
        <Typography variant="caption" sx={{ display: "block", mb: 0.5, color: "text.secondary" }}>
          {field.label}
        </Typography>
        <input type="file" name={field.name} webkitdirectory="" directory="" multiple />
      </Box>
    );
  }
  if (field.type === "file") {
    return (
      <Box sx={{ mb: 1.5 }}>
        <Typography variant="caption" sx={{ display: "block", mb: 0.5, color: "text.secondary" }}>
          {field.label}
        </Typography>
        <input type="file" name={field.name} />
      </Box>
    );
  }
  if (field.type === "select") {
    return (
      <FormControl fullWidth size="small" sx={{ mb: 1.5 }}>
        <InputLabel>{field.label}</InputLabel>
        <Select name={field.name} defaultValue={field.defaultValue} label={field.label}>
          {(field.options || []).map((opt) => (
            <MenuItem key={opt} value={opt}>{opt}</MenuItem>
          ))}
        </Select>
      </FormControl>
    );
  }
  return (
    <TextField
      fullWidth
      size="small"
      type={isPassword && showPassword ? "text" : (isPassword ? "password" : "text")}
      name={field.name}
      label={field.label}
      defaultValue={field.defaultValue || ""}
      placeholder={field.placeholder || ""}
      required={!!field.required}
      InputProps={isPassword ? {
        endAdornment: (
          <InputAdornment position="end">
            <Button
              type="button"
              size="small"
              onClick={() => setShowPassword((v) => !v)}
              sx={{ minWidth: 0, px: 1, textTransform: "none", fontWeight: 700 }}
            >
              {showPassword ? "Hide" : "Show"}
            </Button>
          </InputAdornment>
        ),
      } : undefined}
      sx={{ mb: 1.5 }}
    />
  );
}

function ActionCard({ title, description, action, fields, onRun, color }) {
  const [uploading, setUploading] = React.useState(false);
  const [uploadInfo, setUploadInfo] = React.useState("");
  const [uploadedPath, setUploadedPath] = React.useState("");
  const s3Actions = ["/run/s3_linux", "/run/s3_windows", "/run/s3_windows_iis", "/run/s3_windows_docker"];
  const isS3Install = s3Actions.includes(action);
  const httpsPortField = (fields || []).find((f) => f.name === "LOCALS3_HTTPS_PORT");
  const [httpsPort, setHttpsPort] = React.useState((httpsPortField && httpsPortField.defaultValue) ? String(httpsPortField.defaultValue) : "");
  const [httpsPortState, setHttpsPortState] = React.useState({
    checking: false,
    usable: true,
    error: false,
    message: "",
  });
  const uploadInputRef = React.useRef(null);
  const formRef = React.useRef(null);
  const sourcePathField = (fields || []).find((f) => f.name === "SourceValue" || f.name === "SOURCE_VALUE");
  const sourcePathKey = sourcePathField ? sourcePathField.name : "";

  const setSourcePathInForm = (pathValue) => {
    if (!formRef.current || !sourcePathKey) return;
    const pathInput = formRef.current.querySelector(`[name="${sourcePathKey}"]`);
    if (pathInput) {
      pathInput.value = pathValue || "";
      pathInput.dispatchEvent(new Event("input", { bubbles: true }));
      pathInput.dispatchEvent(new Event("change", { bubbles: true }));
    }
  };

  const doUpload = async () => {
    const input = uploadInputRef.current;
    if (!input || !input.files || input.files.length === 0) {
      setUploadInfo("Select a folder or archive first.");
      return "";
    }
    setUploading(true);
    setUploadInfo("Uploading...");
    if (window.ServerInstallerTerminalHook) {
      window.ServerInstallerTerminalHook({
        open: true,
        state: `Uploading for: ${title}`,
        line: `[${new Date().toLocaleTimeString()}] Upload started for ${title}`,
      });
    }
    try {
      const fd = new FormData();
      for (const f of input.files) {
        const rel = (f.webkitRelativePath && f.webkitRelativePath.length > 0) ? f.webkitRelativePath : f.name;
        fd.append("SourceUpload", f, rel);
      }
      const res = await fetch("/upload/source", {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: fd,
      });
      const rawText = await res.text();
      let json = {};
      try {
        json = JSON.parse(rawText);
      } catch (_) {
        json = { ok: false, error: rawText || `HTTP ${res.status}` };
      }
      if (!json.ok) {
        console.error("Upload failed response:", { status: res.status, body: rawText, parsed: json });
        throw new Error(json.error || "Upload failed");
      }
      setUploadedPath(json.path || "");
      setSourcePathInForm(json.path || "");
      setUploadInfo("Uploaded and extracted on server.");
      if (window.ServerInstallerTerminalHook) {
        window.ServerInstallerTerminalHook({
          open: true,
          state: `Uploading for: ${title}`,
          line: `[${new Date().toLocaleTimeString()}] Upload completed. Server path: ${json.path || ""}`,
        });
      }
      return json.path || "";
    } catch (err) {
      console.error("Upload exception:", err);
      setUploadInfo(`Upload failed: ${err}`);
      if (window.ServerInstallerTerminalHook) {
        window.ServerInstallerTerminalHook({
          open: true,
          state: "Error",
          line: `[${new Date().toLocaleTimeString()}] Upload failed: ${err}`,
        });
      }
      return "";
    } finally {
      setUploading(false);
    }
  };

  React.useEffect(() => {
    if (!isS3Install || !httpsPortField) return undefined;
    const p = String(httpsPort || "").trim();

    if (!p) {
      setHttpsPortState({
        checking: false,
        usable: false,
        error: true,
        message: "HTTPS port is required.",
      });
      return undefined;
    }
    if (!/^\d+$/.test(p) || Number(p) < 1 || Number(p) > 65535) {
      setHttpsPortState({
        checking: false,
        usable: false,
        error: true,
        message: "Port must be a number between 1 and 65535.",
      });
      return undefined;
    }

    let canceled = false;
    const timer = setTimeout(async () => {
      try {
        setHttpsPortState((prev) => ({ ...prev, checking: true }));
        const fd = new FormData();
        fd.append("port", p);
        fd.append("protocol", "tcp");
        const resp = await fetch("/api/system/port_check", {
          method: "POST",
          headers: { "X-Requested-With": "fetch" },
          body: fd,
        });
        const j = await resp.json();
        if (canceled) return;
        if (!j.ok) {
          setHttpsPortState({
            checking: false,
            usable: false,
            error: true,
            message: j.error || "Could not validate port availability.",
          });
          return;
        }
        if (j.busy && !j.managed_owner) {
          setHttpsPortState({
            checking: false,
            usable: false,
            error: true,
            message: `Port ${p} is already in use by another service.`,
          });
          return;
        }
        if (j.busy && j.managed_owner) {
          setHttpsPortState({
            checking: false,
            usable: true,
            error: false,
            message: `Port ${p} is used by existing S3 and can be replaced.`,
          });
          return;
        }
        setHttpsPortState({
          checking: false,
          usable: true,
          error: false,
          message: `Port ${p} is available.`,
        });
      } catch (err) {
        if (canceled) return;
        setHttpsPortState({
          checking: false,
          usable: false,
          error: true,
          message: `Port check failed: ${err}`,
        });
      }
    }, 250);

    return () => {
      canceled = true;
      clearTimeout(timer);
    };
  }, [httpsPort, isS3Install, !!httpsPortField]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isS3Install && httpsPortField && (httpsPortState.checking || !httpsPortState.usable)) {
      return;
    }
    const formEl = formRef.current || e.currentTarget;
    let sourcePathValue = "";
    if (sourcePathKey) {
      const sourcePathInput = formEl.querySelector(`[name="${sourcePathKey}"]`);
      sourcePathValue = (sourcePathInput && sourcePathInput.value ? sourcePathInput.value : "").trim();
    }

    const input = uploadInputRef.current;
    const hasSelectedUpload = !!(input && input.files && input.files.length > 0);

    if (!sourcePathValue && hasSelectedUpload && !uploadedPath) {
      if (window.ServerInstallerTerminalHook) {
        window.ServerInstallerTerminalHook({
          open: true,
          state: `Uploading for: ${title}`,
          line: "============================================================",
        });
      }
      const autoPath = await doUpload();
      if (!autoPath) {
        return;
      }
      sourcePathValue = autoPath;
      if (window.ServerInstallerTerminalHook) {
        window.ServerInstallerTerminalHook({
          open: true,
          state: `Starting: ${title}`,
          line: `[${new Date().toLocaleTimeString()}] Upload finished, continuing deployment...`,
        });
      }
    }

    onRun(e, action, title);
  };

  return (
    <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", boxShadow: "0 10px 26px rgba(15,23,42,.08)" }}>
      <CardContent>
        <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{description}</Typography>
        <Box ref={formRef} component="form" onSubmit={handleSubmit}>
          {(fields || []).map((f) => {
            if (isS3Install && f.name === "LOCALS3_HTTPS_PORT") {
              return (
                <TextField
                  key={f.name}
                  fullWidth
                  size="small"
                  name={f.name}
                  label={f.label}
                  value={httpsPort}
                  placeholder={f.placeholder || ""}
                  required
                  onChange={(ev) => setHttpsPort(ev.target.value)}
                  error={httpsPortState.error}
                  helperText={httpsPortState.checking ? "Checking port availability..." : (httpsPortState.message || " ")}
                  FormHelperTextProps={{
                    sx: httpsPortState.error ? { color: "error.main", fontWeight: 700 } : {},
                  }}
                  sx={{ mb: 1.5 }}
                />
              );
            }
            return <Field key={f.name} field={f} />;
          })}
          {(fields || []).some((f) => f.enableUpload) && (
            <Box sx={{ mb: 1.5 }}>
              <Typography variant="caption" sx={{ display: "block", mb: 0.5, color: "text.secondary" }}>
                Upload Published Folder or Archive
              </Typography>
              <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                <input ref={uploadInputRef} type="file" webkitdirectory="" directory="" multiple />
                <Button type="button" variant="outlined" onClick={doUpload} disabled={uploading} sx={{ textTransform: "none", fontWeight: 700 }}>
                  {uploading ? "Uploading..." : "Upload"}
                </Button>
              </Box>
              {!!uploadInfo && <Typography variant="caption" sx={{ color: "text.secondary" }}>{uploadInfo}</Typography>}
              {!!uploadedPath && <Typography variant="caption" sx={{ display: "block", color: "success.main" }}>Server path: {uploadedPath}</Typography>}
            </Box>
          )}
          <Button
            type="submit"
            variant="contained"
            fullWidth
            disabled={uploading || (isS3Install && !!httpsPortField && (httpsPortState.checking || !httpsPortState.usable))}
            sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2, bgcolor: color || "#1d4ed8" }}
          >
            Start
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}

function NavCard({ title, text, onClick, outlined }) {
  return (
    <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
      <CardContent>
        <Typography variant="h6" fontWeight={800} sx={{ mb: 0.8 }}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{text}</Typography>
        <Button
          fullWidth
          variant={outlined ? "outlined" : "contained"}
          sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2 }}
          onClick={onClick}
        >
          Open
        </Button>
      </CardContent>
    </Card>
  );
}

window.ServerInstallerUI = window.ServerInstallerUI || {};
window.ServerInstallerUI.components = { Field, ActionCard, NavCard };
