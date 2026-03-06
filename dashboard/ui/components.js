const {
  Box, Button, Card, CardContent, FormControl, InputLabel, MenuItem, Select, TextField, Typography
} = MaterialUI;

function Field({ field }) {
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
      name={field.name}
      label={field.label}
      defaultValue={field.defaultValue || ""}
      placeholder={field.placeholder || ""}
      required={!!field.required}
      sx={{ mb: 1.5 }}
    />
  );
}

function ActionCard({ title, description, action, fields, onRun, color }) {
  const [uploading, setUploading] = React.useState(false);
  const [uploadInfo, setUploadInfo] = React.useState("");
  const [uploadedPath, setUploadedPath] = React.useState("");
  const uploadInputRef = React.useRef(null);

  const doUpload = async () => {
    const input = uploadInputRef.current;
    if (!input || !input.files || input.files.length === 0) {
      setUploadInfo("Select a folder or archive first.");
      return;
    }
    setUploading(true);
    setUploadInfo("Uploading...");
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
      const json = await res.json();
      if (!json.ok) {
        throw new Error(json.error || "Upload failed");
      }
      setUploadedPath(json.path || "");
      setUploadInfo("Uploaded and extracted on server.");
    } catch (err) {
      setUploadInfo(`Upload failed: ${err}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", boxShadow: "0 10px 26px rgba(15,23,42,.08)" }}>
      <CardContent>
        <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{description}</Typography>
        <Box component="form" onSubmit={(e) => onRun(e, action, title)}>
          {(fields || []).map((f) => <Field key={f.name} field={f} />)}
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
              {!!uploadedPath && (
                <input
                  type="hidden"
                  name={(fields.find((f) => f.enableUpload) || {}).uploadTargetKey || "SourceFolder"}
                  value={uploadedPath}
                  readOnly
                />
              )}
            </Box>
          )}
          <Button type="submit" variant="contained" fullWidth sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2, bgcolor: color || "#1d4ed8" }}>
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
