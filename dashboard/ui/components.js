const {
  Box, Button, Card, CardContent, FormControl, InputAdornment, InputLabel, MenuItem, Select, TextField, Typography
} = MaterialUI;

function Field({ field, value, onChange, error, helperText, formHelperTextProps }) {
  const isPassword = field.type === "password";
  const [showPassword, setShowPassword] = React.useState(false);
  const controlled = typeof value !== "undefined";
  const trailingAction = field.trailingAction || null;
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
      <FormControl fullWidth size="small" required={!!field.required} sx={{ mb: 1.5 }} disabled={!!field.disabled}>
        <InputLabel>{field.label}</InputLabel>
        <Select
          name={field.name}
          {...(controlled ? { value: value ?? "" } : { defaultValue: field.defaultValue || "" })}
          label={field.label}
          required={!!field.required}
          onChange={onChange}
          error={!!error}
        >
          {((field.required && !field.defaultValue) || !(field.options || []).length) && (
            <MenuItem value="" disabled>{field.placeholder || `Select ${field.label}`}</MenuItem>
          )}
          {(field.options || []).map((opt) => (
            <MenuItem key={opt} value={opt}>{opt}</MenuItem>
          ))}
        </Select>
      </FormControl>
    );
  }
  const endActions = [];
  if (isPassword) {
    endActions.push(
      <Button
        key="toggle-password"
        type="button"
        size="small"
        onClick={() => setShowPassword((v) => !v)}
        sx={{ minWidth: 0, px: 1, textTransform: "none", fontWeight: 700 }}
      >
        {showPassword ? "Hide" : "Show"}
      </Button>
    );
  }
  if (trailingAction) {
    endActions.push(
      <Button
        key="trailing-action"
        type="button"
        size="small"
        onClick={() => {
          if (typeof trailingAction.onClick === "function") {
            trailingAction.onClick();
          } else if (trailingAction.href) {
            window.open(trailingAction.href, trailingAction.target || "_blank", "noopener,noreferrer");
          }
        }}
        sx={{ minWidth: 0, px: 1, textTransform: "none", fontWeight: 700 }}
      >
        {trailingAction.label || "Open"}
      </Button>
    );
  }
  return (
    <TextField
      fullWidth
      size="small"
      type={isPassword && showPassword ? "text" : (isPassword ? "password" : "text")}
      name={field.name}
      label={field.label}
      {...(controlled ? { value: value ?? "" } : { defaultValue: field.defaultValue || "" })}
      placeholder={field.placeholder || ""}
      required={!!field.required}
      onChange={onChange}
      error={!!error}
      helperText={helperText}
      FormHelperTextProps={formHelperTextProps}
      InputProps={endActions.length ? {
        endAdornment: (
          <InputAdornment position="end">
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
              {endActions}
            </Box>
          </InputAdornment>
        ),
      } : undefined}
      sx={{ mb: 1.5 }}
    />
  );
}

function ActionCard({ title, description, action, fields, onRun, color, runDisabled, runDisabledReason }) {
  const [uploading, setUploading] = React.useState(false);
  const [uploadInfo, setUploadInfo] = React.useState("");
  const [uploadedPath, setUploadedPath] = React.useState("");

  // All fields with checkPort: true get live port validation.
  const fieldSignature = React.useMemo(
    () => JSON.stringify((fields || []).map((f) => ({
      name: f.name,
      defaultValue: f.defaultValue ?? "",
      required: !!f.required,
      placeholder: f.placeholder ?? "",
      type: f.type ?? "text",
      checkPort: !!f.checkPort,
    }))),
    [fields]
  );
  const portFields = React.useMemo(
    () => (fields || []).filter((f) => f.checkPort),
    [fieldSignature]
  );
  const initialPortValues = React.useMemo(() => {
    const next = {};
    for (const field of portFields) {
      next[field.name] = field.defaultValue ? String(field.defaultValue) : "";
    }
    return next;
  }, [fieldSignature]);
  const initialPortStates = React.useMemo(() => {
    const next = {};
    for (const field of portFields) {
      next[field.name] = { checking: false, usable: true, error: false, message: "" };
    }
    return next;
  }, [fieldSignature]);
  const [portValues, setPortValues] = React.useState(initialPortValues);
  const [portStates, setPortStates] = React.useState(initialPortStates);
  const uploadInputRef = React.useRef(null);
  const formRef = React.useRef(null);
  const portValidationRunRef = React.useRef(0);
  const sourcePathField = (fields || []).find((f) => (
    f.name === "SourceValue" ||
    f.name === "SOURCE_VALUE" ||
    f.name === "PYTHON_API_SOURCE"
  ));
  const sourcePathKey = sourcePathField ? sourcePathField.name : "";

  React.useEffect(() => {
    setPortValues(initialPortValues);
    setPortStates(initialPortStates);
  }, [initialPortStates, initialPortValues]);

  const emitTerminal = React.useCallback((state, line) => {
    if (!window.ServerInstallerTerminalHook) return;
    window.ServerInstallerTerminalHook({ open: true, state, line });
  }, []);

  const setSourcePathInForm = (pathValue) => {
    if (!formRef.current || !sourcePathKey) return;
    const pathInput = formRef.current.querySelector(`[name="${sourcePathKey}"]`);
    if (pathInput) {
      pathInput.value = pathValue || "";
      pathInput.dispatchEvent(new Event("input", { bubbles: true }));
      pathInput.dispatchEvent(new Event("change", { bubbles: true }));
    }
  };

  const validatePorts = React.useCallback(async (nextValues) => {
    if (portFields.length === 0) return;
    const fieldNames = portFields.map((f) => f.name);
    const nextStates = {};
    const numericValues = {};
    const duplicates = new Set();

    for (const fieldName of fieldNames) {
      const field = portFields.find((f) => f.name === fieldName);
      const rawValue = String(nextValues[fieldName] || "").trim();

      // Empty field: error if required, neutral if optional (empty = skip protocol)
      if (!rawValue) {
        if (field && field.required) {
          nextStates[fieldName] = { checking: false, usable: false, error: true, message: "Port is required." };
        } else {
          nextStates[fieldName] = { checking: false, usable: true, error: false, message: "" };
        }
        continue;
      }
      if (!/^\d+$/.test(rawValue) || Number(rawValue) < 1 || Number(rawValue) > 65535) {
        nextStates[fieldName] = { checking: false, usable: false, error: true, message: "Port must be between 1 and 65535." };
        continue;
      }
      const key = Number(rawValue);
      if (Object.prototype.hasOwnProperty.call(numericValues, key)) {
        duplicates.add(fieldName);
        duplicates.add(numericValues[key]);
      } else {
        numericValues[key] = fieldName;
      }
      nextStates[fieldName] = { checking: true, usable: false, error: false, message: "Checking availability..." };
    }

    duplicates.forEach((fieldName) => {
      nextStates[fieldName] = { checking: false, usable: false, error: true, message: "Each port must be unique." };
    });
    setPortStates({ ...nextStates });

    const fieldsToCheck = fieldNames.filter((fn) => nextStates[fn] && nextStates[fn].checking);
    if (fieldsToCheck.length === 0) return;

    const validationRun = ++portValidationRunRef.current;
    const resolvedStates = { ...nextStates };

    await Promise.all(fieldsToCheck.map(async (fieldName) => {
      const port = String(nextValues[fieldName] || "").trim();
      try {
        const fd = new FormData();
        fd.append("port", port);
        fd.append("protocol", "tcp");
        const resp = await fetch("/api/system/port_check", {
          method: "POST",
          headers: { "X-Requested-With": "fetch" },
          body: fd,
        });
        const j = await resp.json();
        if (!j.ok) {
          resolvedStates[fieldName] = { checking: false, usable: false, error: true, message: j.error || "Could not check port." };
          return;
        }
        if (j.busy && !j.managed_owner) {
          resolvedStates[fieldName] = { checking: false, usable: false, error: true, message: `Port ${port} is already in use by another service.` };
          return;
        }
        if (j.busy && j.managed_owner) {
          resolvedStates[fieldName] = { checking: false, usable: true, error: false, message: `Port ${port} is used by this service (will be reused).` };
          return;
        }
        resolvedStates[fieldName] = { checking: false, usable: true, error: false, message: `Port ${port} is available.` };
      } catch (err) {
        resolvedStates[fieldName] = { checking: false, usable: false, error: true, message: `Port check failed: ${err}` };
      }
    }));

    if (validationRun === portValidationRunRef.current) {
      setPortStates(resolvedStates);
    }
  }, [portFields]);

  React.useEffect(() => {
    if (portFields.length === 0) return;
    validatePorts(initialPortValues);
  }, [initialPortValues, portFields.length, validatePorts]);

  const doUpload = async () => {
    const input = uploadInputRef.current;
    if (!input || !input.files || input.files.length === 0) {
      setUploadInfo("Select a folder or archive first.");
      return "";
    }
    const fileCount = input.files.length;
    const totalBytes = Array.from(input.files).reduce((sum, file) => sum + Number(file.size || 0), 0);
    setUploading(true);
    setUploadInfo("Uploading...");
    if (window.ServerInstallerTerminalHook) {
      window.ServerInstallerTerminalHook({
        open: true,
        state: `Uploading for: ${title}`,
        line: `[${new Date().toLocaleTimeString()}] Upload started for ${title} (${fileCount} file(s), ${totalBytes} bytes)`,
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
      try { json = JSON.parse(rawText); } catch (_) { json = { ok: false, error: rawText || `HTTP ${res.status}` }; }
      if (!json.ok) {
        throw new Error(`Upload failed (HTTP ${res.status}): ${json.error || rawText || "Unknown server error"}`);
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
      const message = String(err);
      const extra = message.includes("Failed to fetch")
        ? " The dashboard could not reach /upload/source. Check browser devtools Network tab."
        : "";
      setUploadInfo(`Upload failed: ${message}${extra}`);
      if (window.ServerInstallerTerminalHook) {
        window.ServerInstallerTerminalHook({
          open: true, state: "Error",
          line: `[${new Date().toLocaleTimeString()}] Upload failed: ${message}${extra}`,
        });
      }
      return "";
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const formEl = formRef.current || e.currentTarget;
    emitTerminal(`Starting: ${title}`, "============================================================");
    emitTerminal(`Starting: ${title}`, `[${new Date().toLocaleTimeString()}] ${title} requested`);
    if (formEl && typeof formEl.reportValidity === "function" && !formEl.reportValidity()) {
      const firstInvalid = formEl.querySelector(":invalid");
      const invalidLabel = firstInvalid ? (firstInvalid.getAttribute("aria-label") || firstInvalid.getAttribute("name") || "required field") : "required field";
      emitTerminal("Validation", `[${new Date().toLocaleTimeString()}] ${title} blocked: fill in ${invalidLabel}.`);
      return;
    }
    // Block if any port field is still checking or has an error
    for (const field of portFields) {
      const state = portStates[field.name];
      if (state && (state.checking || !state.usable)) {
        emitTerminal("Validation", `[${new Date().toLocaleTimeString()}] ${title} blocked: ${state.message || `${field.label} is not ready.`}`);
        return;
      }
    }
    // Ensure uniqueness of all non-empty port values
    const portEntries = [];
    for (const field of portFields) {
      const input = formEl.querySelector(`[name="${field.name}"]`);
      const value = String(input && input.value ? input.value : "").trim();
      if (!value) continue;
      if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65535) {
        emitTerminal("Validation", `[${new Date().toLocaleTimeString()}] ${title} blocked: ${field.label} must be between 1 and 65535.`);
        return;
      }
      portEntries.push({ fieldName: field.name, value: Number(value) });
    }
    const seen = new Set();
    for (const item of portEntries) {
      if (seen.has(item.value)) {
        emitTerminal("Validation", `[${new Date().toLocaleTimeString()}] ${title} blocked: all ports must be unique.`);
        window.alert("All ports must be unique.");
        return;
      }
      seen.add(item.value);
    }

    let sourcePathValue = "";
    if (sourcePathKey) {
      const sourcePathInput = formEl.querySelector(`[name="${sourcePathKey}"]`);
      sourcePathValue = (sourcePathInput && sourcePathInput.value ? sourcePathInput.value : "").trim();
    }
    const input = uploadInputRef.current;
    const hasSelectedUpload = !!(input && input.files && input.files.length > 0);
    if (hasSelectedUpload) {
      let effectiveUploadPath = uploadedPath;
      if (!effectiveUploadPath) {
        emitTerminal(`Uploading for: ${title}`, "============================================================");
        effectiveUploadPath = await doUpload();
        if (!effectiveUploadPath) return;
      }
      setSourcePathInForm(effectiveUploadPath);
      sourcePathValue = effectiveUploadPath;
      emitTerminal(`Starting: ${title}`, `[${new Date().toLocaleTimeString()}] Upload finished, using: ${effectiveUploadPath}`);
    }

    onRun(e, action, title, formEl);
  };

  const portBlocksSubmit = portFields.some((field) => {
    const state = portStates[field.name];
    return state && (state.checking || !state.usable);
  });

  return (
    <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", boxShadow: "0 10px 26px rgba(15,23,42,.08)" }}>
      <CardContent>
        <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{description}</Typography>
        <Box ref={formRef} component="form" onSubmit={handleSubmit}>
          {(fields || []).map((f) => {
            if (f.checkPort) {
              const fieldState = portStates[f.name] || { checking: false, usable: true, error: false, message: "" };
              return (
                <Field
                  key={f.name}
                  field={f}
                  value={portValues[f.name] ?? ""}
                  onChange={(ev) => {
                    const nextValues = { ...portValues, [f.name]: ev.target.value };
                    setPortValues(nextValues);
                    validatePorts(nextValues);
                  }}
                  error={fieldState.error}
                  helperText={fieldState.message || " "}
                  formHelperTextProps={{
                    sx: fieldState.error
                      ? { color: "error.main", fontWeight: 700 }
                      : fieldState.message && !fieldState.checking
                        ? { color: "success.main" }
                        : {},
                  }}
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
            disabled={!!runDisabled || uploading || portBlocksSubmit}
            sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2, bgcolor: color || "#1d4ed8" }}
          >
            Start
          </Button>
          {!!runDisabledReason && (
            <Typography variant="caption" color="error" sx={{ display: "block", mt: 1 }}>
              {runDisabledReason}
            </Typography>
          )}
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
