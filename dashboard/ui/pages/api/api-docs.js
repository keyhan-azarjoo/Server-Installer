(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};

  // ── Method badge colors ──────────────────────────────────────────────────
  const MC = {
    GET:    { bg: "#dcfce7", color: "#166534", border: "#86efac" },
    POST:   { bg: "#dbeafe", color: "#1e40af", border: "#93c5fd" },
    PUT:    { bg: "#fef9c3", color: "#854d0e", border: "#fde047" },
    DELETE: { bg: "#fee2e2", color: "#991b1b", border: "#fca5a5" },
  };

  /**
   * Render an inline, collapsible API-docs section.
   *
   * Usage from any page:
   *   const renderApiDocs = window.ServerInstallerUI.renderApiDocs;
   *   {renderApiDocs && renderApiDocs(p, apiDocData)}
   *
   * @param {object} p          - The common page props (MUI components, copyText, etc.)
   * @param {object} docData    - { title, color, description, baseUrl, sections }
   */
  ns.renderApiDocs = function renderApiDocs(p, docData) {
    if (!docData || !docData.sections || docData.sections.length === 0) return null;

    const {
      Box, Button, Card, CardContent, Typography, Stack, Paper, Chip, Tooltip, Grid,
      copyText,
    } = p;

    const [open, setOpen] = React.useState(false);
    const [expanded, setExpanded] = React.useState(() => {
      const init = {};
      docData.sections.forEach((_, i) => { init[i] = true; });
      return init;
    });
    const toggle = (i) => setExpanded((prev) => ({ ...prev, [i]: !prev[i] }));

    const copy = (text, label) => {
      if (copyText) copyText(text, label);
      else if (navigator.clipboard) navigator.clipboard.writeText(text);
    };

    const curl = (ep) => {
      let c = "curl -X " + ep.method + ' "' + ep.path + '"';
      if (ep.body && !ep.body.startsWith("multipart") && !ep.body.startsWith("Form")) {
        c += " \\\n  -H \"Content-Type: application/json\" \\\n  -d '" + ep.body + "'";
      }
      return c;
    };

    const mc = (m) => MC[m] || { bg: "#f3f4f6", color: "#374151", border: "#d1d5db" };

    if (!open) {
      return (
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid " + (docData.color || "#6d28d9") + "33" }}>
            <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ flexGrow: 1, color: docData.color || "#6d28d9" }}>
                  {docData.title || "API Documentation"}
                </Typography>
                <Chip
                  label={docData.sections.reduce((n, s) => n + s.endpoints.length, 0) + " endpoints"}
                  size="small" variant="outlined"
                  sx={{ fontSize: 10, height: 20, borderColor: docData.color || "#6d28d9", color: docData.color || "#6d28d9" }}
                />
                <Button
                  variant="outlined" size="small"
                  onClick={() => setOpen(true)}
                  sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, borderColor: docData.color, color: docData.color }}
                >
                  Show API Documents
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      );
    }

    return (
      <Grid item xs={12}>
        <Card sx={{ borderRadius: 3, border: "1.5px solid " + (docData.color || "#6d28d9") + "33" }}>
          <CardContent>
            {/* Header */}
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Typography variant="h6" fontWeight={900} sx={{ color: docData.color, flexGrow: 1 }}>
                {docData.title}
              </Typography>
              {docData.baseUrl && (
                <Chip
                  label={"Base: " + docData.baseUrl}
                  size="small"
                  sx={{ fontFamily: "monospace", fontWeight: 600, fontSize: 11, bgcolor: (docData.color || "#6d28d9") + "11", color: docData.color, border: "1px solid " + (docData.color || "#6d28d9") + "33" }}
                />
              )}
              <Button
                variant="text" size="small"
                onClick={() => setOpen(false)}
                sx={{ textTransform: "none", fontWeight: 700, color: "#94a3b8" }}
              >
                Hide
              </Button>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {docData.description}
            </Typography>

            {/* Sections */}
            {docData.sections.map((section, si) => (
              <Box key={si} sx={{ mb: 2 }}>
                <Stack
                  direction="row" alignItems="center" spacing={1}
                  sx={{ cursor: "pointer", userSelect: "none", mb: 0.5 }}
                  onClick={() => toggle(si)}
                >
                  <Typography variant="subtitle1" fontWeight={800} sx={{ color: docData.color, flexGrow: 1 }}>
                    {section.name}
                  </Typography>
                  <Chip label={section.endpoints.length + " endpoint" + (section.endpoints.length > 1 ? "s" : "")} size="small" variant="outlined" sx={{ fontSize: 10, height: 18 }} />
                  <Typography variant="body2" sx={{ color: "text.secondary", fontSize: 16 }}>
                    {expanded[si] ? "\u25BE" : "\u25B8"}
                  </Typography>
                </Stack>

                {expanded[si] && section.endpoints.map((ep, ei) => {
                  const m = mc(ep.method);
                  return (
                    <Paper key={ei} variant="outlined" sx={{ p: 1.5, mb: 0.75, borderRadius: 2, borderColor: "#e2e8f0" }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "flex-start", md: "center" }}>
                        <Chip
                          label={ep.method}
                          size="small"
                          sx={{ bgcolor: m.bg, color: m.color, border: "1px solid " + m.border, fontWeight: 800, fontFamily: "monospace", minWidth: 65, justifyContent: "center" }}
                        />
                        <Typography variant="body2" sx={{ fontFamily: "monospace", fontWeight: 600, wordBreak: "break-all", flexGrow: 1 }}>
                          {ep.path}
                        </Typography>
                        <Tooltip title="Copy cURL command">
                          <Button size="small" variant="text" sx={{ textTransform: "none", minWidth: 0, px: 1, fontSize: 11 }} onClick={() => copy(curl(ep), "cURL")}>
                            cURL
                          </Button>
                        </Tooltip>
                      </Stack>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        {ep.description}
                      </Typography>
                      {ep.body && (
                        <Box sx={{ mt: 0.75 }}>
                          <Typography variant="caption" fontWeight={700} sx={{ color: "#64748b" }}>Body:</Typography>
                          <Paper elevation={0} sx={{ mt: 0.25, p: 0.75, bgcolor: "#f8fafc", borderRadius: 1, fontFamily: "monospace", fontSize: 11, wordBreak: "break-all", border: "1px solid #e2e8f0" }}>
                            {ep.body}
                          </Paper>
                        </Box>
                      )}
                      {ep.response && (
                        <Box sx={{ mt: 0.75 }}>
                          <Typography variant="caption" fontWeight={700} sx={{ color: "#64748b" }}>Response:</Typography>
                          <Paper elevation={0} sx={{ mt: 0.25, p: 0.75, bgcolor: "#f0fdf4", borderRadius: 1, fontFamily: "monospace", fontSize: 11, wordBreak: "break-all", border: "1px solid #dcfce7" }}>
                            {ep.response}
                          </Paper>
                        </Box>
                      )}
                    </Paper>
                  );
                })}
              </Box>
            ))}
          </CardContent>
        </Card>
      </Grid>
    );
  };

  // ── Per-service API documentation data ──────────────────────────────────────
  // Exported so each page can import its own docs.
  ns.apiDocs = {
    s3: {
      title: "S3 Storage (MinIO) API",
      color: "#0f766e",
      description: "MinIO S3-compatible API. Use any S3 SDK (AWS SDK, boto3, mc CLI) or these dashboard endpoints.",
      baseUrl: "/api/s3",
      sections: [
        { name: "Bucket Operations", endpoints: [
          { method: "GET", path: "/api/s3/buckets", description: "List all buckets", response: '{ "ok": true, "buckets": [{ "name": "my-bucket", "creation_date": "..." }] }' },
          { method: "POST", path: "/api/s3/buckets", description: "Create a new bucket", body: '{ "name": "my-bucket" }', response: '{ "ok": true, "message": "Bucket created" }' },
          { method: "DELETE", path: "/api/s3/buckets/{name}", description: "Delete a bucket (must be empty)", response: '{ "ok": true, "message": "Bucket deleted" }' },
        ]},
        { name: "Object Operations", endpoints: [
          { method: "GET", path: "/api/s3/objects?bucket={name}&prefix={prefix}", description: "List objects in a bucket", response: '{ "ok": true, "objects": [{ "key": "file.txt", "size": 1024, "last_modified": "..." }] }' },
          { method: "POST", path: "/api/s3/upload", description: "Upload a file (multipart: bucket, key, file)", body: "multipart/form-data: bucket, key, file", response: '{ "ok": true, "key": "file.txt", "size": 1024 }' },
          { method: "GET", path: "/api/s3/download?bucket={name}&key={key}", description: "Download an object", response: "Binary file content" },
          { method: "DELETE", path: "/api/s3/objects/{bucket}/{key}", description: "Delete an object", response: '{ "ok": true, "message": "Object deleted" }' },
          { method: "POST", path: "/api/s3/presign", description: "Generate a pre-signed URL", body: '{ "bucket": "my-bucket", "key": "file.txt", "expires": 3600 }', response: '{ "ok": true, "url": "https://...", "expires_in": 3600 }' },
        ]},
        { name: "Info & Health", endpoints: [
          { method: "GET", path: "/api/s3/info", description: "Get S3 endpoint, access key, region", response: '{ "ok": true, "endpoint": "http://...", "access_key": "admin", "region": "us-east-1" }' },
          { method: "GET", path: "/api/s3/health", description: "Health check", response: '{ "ok": true, "status": "healthy" }' },
        ]},
      ],
    },

    mongo: {
      title: "MongoDB API",
      color: "#15803d",
      description: "Manage MongoDB databases, collections, and documents through the dashboard API.",
      baseUrl: "/api/mongo",
      sections: [
        { name: "Database Operations", endpoints: [
          { method: "GET", path: "/api/mongo/databases", description: "List all databases with size info", response: '{ "ok": true, "databases": [{ "name": "mydb", "sizeOnDisk": 8192 }] }' },
          { method: "POST", path: "/api/mongo/databases", description: "Create a new database", body: '{ "name": "mydb" }', response: '{ "ok": true, "message": "Database created" }' },
          { method: "DELETE", path: "/api/mongo/databases/{name}", description: "Drop a database", response: '{ "ok": true, "message": "Database dropped" }' },
        ]},
        { name: "Collection Operations", endpoints: [
          { method: "GET", path: "/api/mongo/native/collections?db={dbname}", description: "List collections", response: '{ "ok": true, "collections": [{ "name": "users", "type": "collection" }] }' },
          { method: "POST", path: "/api/mongo/collections", description: "Create a collection", body: '{ "db": "mydb", "name": "users" }', response: '{ "ok": true, "message": "Collection created" }' },
          { method: "DELETE", path: "/api/mongo/collections/{db}/{name}", description: "Drop a collection", response: '{ "ok": true }' },
        ]},
        { name: "Document Operations", endpoints: [
          { method: "GET", path: "/api/mongo/native/documents?db={db}&collection={col}&limit=50", description: "Query documents", response: '{ "ok": true, "documents": [...], "total": 100 }' },
          { method: "POST", path: "/api/mongo/documents", description: "Insert documents", body: '{ "db": "mydb", "collection": "users", "documents": [{ "name": "John" }] }', response: '{ "ok": true, "inserted_count": 1 }' },
          { method: "PUT", path: "/api/mongo/documents", description: "Update documents", body: '{ "db": "mydb", "collection": "users", "filter": { "name": "John" }, "update": { "$set": { "age": 30 } } }', response: '{ "ok": true, "modified_count": 1 }' },
          { method: "DELETE", path: "/api/mongo/documents", description: "Delete documents", body: '{ "db": "mydb", "collection": "users", "filter": { "name": "John" } }', response: '{ "ok": true, "deleted_count": 1 }' },
        ]},
        { name: "Commands & Health", endpoints: [
          { method: "POST", path: "/api/mongo/native/command", description: "Run a raw MongoDB command", body: '{ "db": "mydb", "script": "db.users.count()" }', response: '{ "ok": true, "result": ... }' },
          { method: "GET", path: "/api/mongo/native/overview", description: "Server overview (version, databases)", response: '{ "ok": true, "version": "7.0", "databases": [...] }' },
          { method: "GET", path: "/api/mongo/health", description: "Health check", response: '{ "ok": true, "status": "healthy", "connections": 5 }' },
        ]},
      ],
    },

    proxy: {
      title: "Proxy / VPN API",
      color: "#1d4ed8",
      description: "Manage multi-layer proxy stack: users, layers, services.",
      baseUrl: "/api/proxy",
      sections: [
        { name: "User Management", endpoints: [
          { method: "GET", path: "/api/proxy/users", description: "List all proxy users with connection status", response: '{ "ok": true, "users": [{ "username": "user1", "connected": true }] }' },
          { method: "POST", path: "/api/proxy/users", description: "Add a new proxy user", body: '{ "username": "user1", "password": "pass123" }', response: '{ "ok": true, "message": "User created" }' },
          { method: "PUT", path: "/api/proxy/users/{username}/password", description: "Update user password", body: '{ "password": "newpass" }', response: '{ "ok": true }' },
          { method: "DELETE", path: "/api/proxy/users/{username}", description: "Remove a proxy user", response: '{ "ok": true }' },
        ]},
        { name: "Layer & Service", endpoints: [
          { method: "GET", path: "/api/proxy/info", description: "Get proxy system info (layer, service, OS)", response: '{ "ok": true, "layer": "layer7-v2ray-vless", "service": "xray" }' },
          { method: "GET", path: "/api/proxy/status", description: "Get proxy service statuses", response: '{ "ok": true, "services": { "xray": "running" } }' },
          { method: "POST", path: "/api/proxy/service/restart", description: "Restart the proxy service", response: '{ "ok": true }' },
          { method: "POST", path: "/api/proxy/layer/switch", description: "Switch proxy layer", body: '{ "layer": "layer7-v2ray-vmess" }', response: '{ "ok": true }' },
        ]},
        { name: "Connection & Health", endpoints: [
          { method: "GET", path: "/api/proxy/users/{username}/config", description: "Get user connection config (V2Ray URI, QR)", response: '{ "ok": true, "config": "vless://..." }' },
          { method: "GET", path: "/api/proxy/health", description: "Health check", response: '{ "ok": true, "status": "healthy" }' },
        ]},
      ],
    },

    sam3: {
      title: "SAM3 - Segment Anything API",
      color: "#7c3aed",
      description: "AI-powered object detection and segmentation. Upload images, run detection, track objects in video, export results.",
      baseUrl: "http://{sam3_host}:{sam3_port}",
      sections: [
        { name: "Image Detection", endpoints: [
          { method: "POST", path: "/detect", description: "Detect objects with text prompts", body: 'multipart: image (file), prompt ("person,car"), threshold (0.3)', response: '{ "detections": [{ "label": "person", "confidence": 0.95, "bbox": [...] }] }' },
          { method: "POST", path: "/detect-point", description: "Detect at specific point coordinates", body: "multipart: image, points (JSON [[x,y]]), labels ([1])", response: '{ "detections": [{ "mask": "base64...", "score": 0.98 }] }' },
          { method: "POST", path: "/detect-box", description: "Detect within bounding box", body: "multipart: image, box (JSON [x1,y1,x2,y2])", response: '{ "detections": [...] }' },
          { method: "POST", path: "/detect-exemplar", description: "Detect using a visual example", body: "multipart: image, exemplar (cropped image)", response: '{ "detections": [...] }' },
          { method: "POST", path: "/detect-live", description: "Real-time detection for camera frames", body: "multipart: image, prompt, threshold", response: '{ "detections": [...], "processing_time_ms": 45 }' },
        ]},
        { name: "Video Processing", endpoints: [
          { method: "POST", path: "/upload-video", description: "Upload a video for processing", body: "multipart: video (file)", response: '{ "video_id": "abc123", "frames": 300, "fps": 30 }' },
          { method: "GET", path: "/process-video/{video_id}?prompt={text}", description: "Process video with detection (SSE stream)", response: "text/event-stream: frame-by-frame results" },
          { method: "GET", path: "/get-video/{video_id}", description: "Download processed video", response: "video/mp4" },
          { method: "GET", path: "/get-frame/{video_id}/{frame}", description: "Get a specific frame", response: "image/jpeg" },
          { method: "GET", path: "/track-object/{video_id}?x={x}&y={y}&frame={n}", description: "Track object across frames (SSE)", response: "text/event-stream" },
        ]},
        { name: "Export", endpoints: [
          { method: "POST", path: "/export/mask", description: "Export detection masks as PNG", response: "image/png" },
          { method: "POST", path: "/export/masks-zip", description: "Export all masks as ZIP", response: "application/zip" },
          { method: "POST", path: "/export/json", description: "Export detections as JSON", response: "application/json" },
          { method: "POST", path: "/export/coco", description: "Export in COCO format", response: "application/json" },
        ]},
        { name: "Model Info", endpoints: [
          { method: "GET", path: "/model-info", description: "Get model status (name, device, loaded)", response: '{ "model": "sam3", "device": "cuda", "loaded": true }' },
        ]},
      ],
    },

    ollama: {
      title: "Ollama LLM API",
      color: "#1e40af",
      description: "Run LLMs locally with OpenAI-compatible API. Chat, generate, embed, manage models.",
      baseUrl: "http://{ollama_host}:11434",
      sections: [
        { name: "Chat & Generate", endpoints: [
          { method: "POST", path: "/api/chat", description: "Chat with a model", body: '{ "model": "llama3", "messages": [{ "role": "user", "content": "Hello!" }], "stream": false }', response: '{ "message": { "role": "assistant", "content": "Hi!" }, "done": true }' },
          { method: "POST", path: "/api/generate", description: "Generate text completion", body: '{ "model": "llama3", "prompt": "Write a poem", "stream": false }', response: '{ "response": "...", "done": true }' },
          { method: "POST", path: "/api/embeddings", description: "Generate embeddings", body: '{ "model": "llama3", "prompt": "Hello world" }', response: '{ "embedding": [0.123, -0.456, ...] }' },
        ]},
        { name: "Model Management", endpoints: [
          { method: "GET", path: "/api/tags", description: "List downloaded models", response: '{ "models": [{ "name": "llama3:latest", "size": 4700000000 }] }' },
          { method: "POST", path: "/api/pull", description: "Download a model", body: '{ "name": "llama3" }', response: '{ "status": "success" }' },
          { method: "DELETE", path: "/api/delete", description: "Delete a model", body: '{ "name": "llama3" }', response: '{ "status": "success" }' },
          { method: "POST", path: "/api/show", description: "Show model details", body: '{ "name": "llama3" }', response: '{ "modelfile": "...", "parameters": "..." }' },
          { method: "GET", path: "/api/ps", description: "List running models", response: '{ "models": [{ "name": "llama3", "size": ... }] }' },
        ]},
        { name: "OpenAI-Compatible (v1)", endpoints: [
          { method: "POST", path: "/v1/chat/completions", description: "OpenAI chat completions", body: '{ "model": "llama3", "messages": [{ "role": "user", "content": "Hello" }] }', response: '{ "choices": [{ "message": { "content": "Hi!" } }] }' },
          { method: "GET", path: "/v1/models", description: "List models (OpenAI format)", response: '{ "data": [{ "id": "llama3" }] }' },
        ]},
      ],
    },

    dotnet: {
      title: "DotNet Service Management API",
      color: "#6d28d9",
      description: "Control your deployed .NET Core / ASP.NET APIs. Each deployed API exposes its own Swagger endpoints.",
      baseUrl: "/api",
      sections: [
        { name: "Service Management", endpoints: [
          { method: "GET", path: "/api/system/services?scope=dotnet", description: "List all .NET API services", response: '{ "ok": true, "services": [{ "name": "MyApi", "status": "running", "ports": [5000] }] }' },
          { method: "POST", path: "/api/system/service", description: "Control a service (start/stop/restart/delete)", body: '{ "name": "MyApi", "action": "restart", "kind": "iis" }', response: '{ "ok": true, "message": "Service restarted" }' },
        ]},
        { name: "Your Deployed API", endpoints: [
          { method: "GET", path: "http://{host}:{port}/swagger", description: "Swagger UI (if enabled in your API)" },
          { method: "GET", path: "http://{host}:{port}/health", description: "Health check (if configured)" },
          { method: "GET", path: "http://{host}:{port}/api/*", description: "Your custom endpoints" },
        ]},
      ],
    },

    python: {
      title: "Python Service Management API",
      color: "#0d9488",
      description: "Control your deployed Python APIs (Flask, FastAPI, Django). FastAPI auto-generates docs at /docs.",
      baseUrl: "/api",
      sections: [
        { name: "Service Management", endpoints: [
          { method: "GET", path: "/api/system/services?scope=python", description: "List all Python API services", response: '{ "ok": true, "services": [{ "name": "my-flask", "status": "running" }] }' },
          { method: "POST", path: "/api/system/service", description: "Control a service (start/stop/restart/delete)", body: '{ "name": "my-flask", "action": "restart" }', response: '{ "ok": true }' },
        ]},
        { name: "Your Deployed API", endpoints: [
          { method: "GET", path: "http://{host}:{port}/docs", description: "FastAPI auto-generated Swagger docs" },
          { method: "GET", path: "http://{host}:{port}/redoc", description: "FastAPI ReDoc documentation" },
          { method: "GET", path: "http://{host}:{port}/api/*", description: "Your custom endpoints" },
        ]},
      ],
    },
  };
})();
