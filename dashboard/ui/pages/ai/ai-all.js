(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  // ── All AI service definitions ────────────────────────────────────────────
  // Each entry creates a full install/manage page automatically.
  const AI_SERVICES = {
    "ai-vllm": {
      title: "vLLM",
      subtitle: "High-Throughput LLM Serving",
      color: "#1e40af",
      defaultPort: "8000",
      prefix: "VLLM",
      description: "vLLM is a fast and easy-to-use library for LLM inference and serving. Features PagedAttention for efficient memory management, continuous batching, and OpenAI-compatible API server.",
      gpuRequired: true,
      gpuNote: "vLLM requires a GPU with 8+ GB VRAM for most models. NVIDIA GPUs with CUDA are required.",
      website: "https://docs.vllm.ai/",
      dockerImage: "vllm/vllm-openai:latest",
      dockerPort: "8000",
      installCmds: {
        pip: "pip install vllm",
        docker: "docker run -d --gpus all -p 8000:8000 vllm/vllm-openai:latest --model meta-llama/Llama-3-8b",
      },
      links: [
        { label: "Documentation", url: "https://docs.vllm.ai/" },
        { label: "GitHub", url: "https://github.com/vllm-project/vllm" },
        { label: "Models (HuggingFace)", url: "https://huggingface.co/models?library=vllm" },
      ],
      apiDocs: {
        title: "vLLM API (OpenAI-Compatible)", baseUrl: "http://{host}:8000",
        sections: [
          { name: "Chat & Completions", endpoints: [
            { m: "POST", p: "/v1/chat/completions", d: "Chat completions (OpenAI-compatible).", body: '{ "model": "meta-llama/Llama-3-8b", "messages": [{"role": "user", "content": "Hello"}] }', res: '{ "choices": [{"message": {"content": "Hi!"}}] }' },
            { m: "POST", p: "/v1/completions", d: "Text completions.", body: '{ "model": "meta-llama/Llama-3-8b", "prompt": "Hello" }', res: '{ "choices": [{"text": "..."}] }' },
            { m: "GET", p: "/v1/models", d: "List available models.", res: '{ "data": [{"id": "meta-llama/Llama-3-8b"}] }' },
          ]},
        ],
      },
    },
    "ai-llamacpp": {
      title: "llama.cpp",
      subtitle: "Lightweight C++ LLM Inference",
      color: "#059669",
      defaultPort: "8080",
      prefix: "LLAMACPP",
      description: "llama.cpp provides efficient LLM inference in C/C++ with minimal dependencies. Run GGUF models on CPU and GPU. Supports quantized models for low-memory systems.",
      gpuRequired: false,
      gpuNote: "Runs on CPU by default. GPU acceleration available with CUDA, Metal (macOS), or Vulkan.",
      website: "https://github.com/ggerganov/llama.cpp",
      dockerImage: "ghcr.io/ggerganov/llama.cpp:server",
      dockerPort: "8080",
      installCmds: {
        git: "git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp && make -j",
        docker: "docker run -d -p 8080:8080 -v models:/models ghcr.io/ggerganov/llama.cpp:server -m /models/model.gguf --host 0.0.0.0 --port 8080",
      },
      links: [
        { label: "GitHub", url: "https://github.com/ggerganov/llama.cpp" },
        { label: "GGUF Models", url: "https://huggingface.co/models?sort=trending&search=gguf" },
        { label: "Server Docs", url: "https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md" },
      ],
      apiDocs: {
        title: "llama.cpp Server API", baseUrl: "http://{host}:8080",
        sections: [
          { name: "Inference", endpoints: [
            { m: "POST", p: "/completion", d: "Generate text completion.", body: '{ "prompt": "Hello", "n_predict": 128 }', res: '{ "content": "..." }' },
            { m: "POST", p: "/v1/chat/completions", d: "OpenAI-compatible chat.", body: '{ "messages": [{"role": "user", "content": "Hi"}] }', res: '{ "choices": [...] }' },
            { m: "GET", p: "/health", d: "Health check.", res: '{ "status": "ok" }' },
          ]},
        ],
      },
    },
    "ai-deepseek": {
      title: "DeepSeek",
      subtitle: "Code & Reasoning LLM",
      color: "#2563eb",
      defaultPort: "11434",
      prefix: "DEEPSEEK",
      description: "DeepSeek models excel at code generation, mathematical reasoning, and general tasks. Deploy locally via Ollama for the easiest setup, or use vLLM for production throughput.",
      gpuRequired: false,
      gpuNote: "DeepSeek-Coder-V2-Lite runs on 8 GB VRAM. Larger models need 16+ GB.",
      website: "https://www.deepseek.com/",
      dockerImage: "ollama/ollama:latest",
      dockerPort: "11434",
      installCmds: {
        ollama: "ollama pull deepseek-coder-v2:lite",
        docker: "docker run -d -p 11434:11434 ollama/ollama && docker exec -it $(docker ps -q -f ancestor=ollama/ollama) ollama pull deepseek-coder-v2:lite",
      },
      links: [
        { label: "DeepSeek Website", url: "https://www.deepseek.com/" },
        { label: "Ollama: deepseek-coder-v2", url: "https://ollama.com/library/deepseek-coder-v2" },
        { label: "HuggingFace Models", url: "https://huggingface.co/deepseek-ai" },
      ],
      models: [
        { name: "deepseek-coder-v2:lite", size: "8.9 GB", desc: "Code generation (16B, lite)" },
        { name: "deepseek-r1:7b", size: "4.7 GB", desc: "Reasoning model (7B)" },
        { name: "deepseek-r1:14b", size: "9.0 GB", desc: "Reasoning model (14B)" },
      ],
      apiDocs: {
        title: "DeepSeek via Ollama API", baseUrl: "http://{host}:11434",
        sections: [
          { name: "Chat & Generate", endpoints: [
            { m: "POST", p: "/api/chat", d: "Chat with DeepSeek.", body: '{ "model": "deepseek-coder-v2:lite", "messages": [{"role": "user", "content": "Write a Python sort function"}] }', res: '{ "message": {"content": "def sort..."} }' },
            { m: "POST", p: "/api/generate", d: "Generate completion.", body: '{ "model": "deepseek-r1:7b", "prompt": "Explain quantum computing" }', res: '{ "response": "..." }' },
          ]},
        ],
      },
    },
    "ai-localai": {
      title: "LocalAI",
      subtitle: "OpenAI-Compatible Local API",
      color: "#7c3aed",
      defaultPort: "8080",
      prefix: "LOCALAI",
      description: "LocalAI is a drop-in replacement for the OpenAI API. Run LLMs, generate images, audio, and embeddings locally without GPU. Supports GGUF, GPTQ, and more.",
      gpuRequired: false,
      gpuNote: "Runs on CPU by default. GPU acceleration optional.",
      website: "https://localai.io/",
      dockerImage: "localai/localai:latest-aio-cpu",
      dockerPort: "8080",
      installCmds: {
        docker: "docker run -d -p 8080:8080 localai/localai:latest-aio-cpu",
        dockerGpu: "docker run -d --gpus all -p 8080:8080 localai/localai:latest-aio-gpu-nvidia-cuda-12",
      },
      links: [
        { label: "Documentation", url: "https://localai.io/basics/getting_started/" },
        { label: "GitHub", url: "https://github.com/mudler/LocalAI" },
        { label: "Model Gallery", url: "https://localai.io/models/" },
      ],
      apiDocs: {
        title: "LocalAI API (OpenAI-Compatible)", baseUrl: "http://{host}:8080",
        sections: [
          { name: "OpenAI Endpoints", endpoints: [
            { m: "POST", p: "/v1/chat/completions", d: "Chat completions.", body: '{ "model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}] }', res: '{ "choices": [...] }' },
            { m: "POST", p: "/v1/images/generations", d: "Image generation.", body: '{ "prompt": "A cat", "size": "512x512" }', res: '{ "data": [{"url": "..."}] }' },
            { m: "POST", p: "/v1/audio/transcriptions", d: "Speech to text.", body: "multipart: file (audio)", res: '{ "text": "..." }' },
            { m: "POST", p: "/v1/embeddings", d: "Generate embeddings.", body: '{ "input": "Hello", "model": "bert" }', res: '{ "data": [{"embedding": [...]}] }' },
          ]},
        ],
      },
    },
    "ai-sdwebui": {
      title: "Stable Diffusion WebUI",
      subtitle: "AUTOMATIC1111 Image Generation",
      color: "#dc2626",
      defaultPort: "7860",
      prefix: "SDWEBUI",
      description: "AUTOMATIC1111's Stable Diffusion Web UI. Full-featured image generation with txt2img, img2img, inpainting, ControlNet, LoRA, textual inversion, and hundreds of extensions.",
      gpuRequired: true,
      gpuNote: "Requires GPU with 4+ GB VRAM (6+ GB recommended for SDXL). NVIDIA CUDA required.",
      website: "https://github.com/AUTOMATIC1111/stable-diffusion-webui",
      dockerImage: "universonic/stable-diffusion-webui:latest",
      dockerPort: "7860",
      installCmds: {
        git: "git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui && cd stable-diffusion-webui && ./webui.sh --listen --api",
        docker: "docker run -d --gpus all -p 7860:7860 universonic/stable-diffusion-webui:latest --listen --api",
      },
      links: [
        { label: "GitHub", url: "https://github.com/AUTOMATIC1111/stable-diffusion-webui" },
        { label: "Wiki", url: "https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki" },
        { label: "Extensions", url: "https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/Extensions" },
        { label: "Models (Civitai)", url: "https://civitai.com/models" },
      ],
      apiDocs: {
        title: "SD WebUI API", baseUrl: "http://{host}:7860",
        sections: [
          { name: "Image Generation", endpoints: [
            { m: "POST", p: "/sdapi/v1/txt2img", d: "Text to image generation.", body: '{ "prompt": "a cat", "steps": 20, "width": 512, "height": 512 }', res: '{ "images": ["base64..."] }' },
            { m: "POST", p: "/sdapi/v1/img2img", d: "Image to image.", body: '{ "init_images": ["base64..."], "prompt": "oil painting" }', res: '{ "images": ["base64..."] }' },
            { m: "GET", p: "/sdapi/v1/sd-models", d: "List available models.", res: '[{"title": "v1-5-pruned.safetensors", ...}]' },
          ]},
        ],
      },
    },
    "ai-fooocus": {
      title: "Fooocus",
      subtitle: "Simplified Stable Diffusion",
      color: "#ea580c",
      defaultPort: "7865",
      prefix: "FOOOCUS",
      description: "Fooocus is a Stable Diffusion image generation tool focused on simplicity. Produces Midjourney-quality images with minimal configuration. Just type a prompt and generate.",
      gpuRequired: true,
      gpuNote: "Requires NVIDIA GPU with 4+ GB VRAM.",
      website: "https://github.com/lllyasviel/Fooocus",
      dockerImage: "ashleykza/fooocus:latest",
      dockerPort: "7865",
      installCmds: {
        git: "git clone https://github.com/lllyasviel/Fooocus && cd Fooocus && python -m venv venv && venv/bin/pip install -r requirements_versions.txt && venv/bin/python entry_with_update.py --listen",
        docker: "docker run -d --gpus all -p 7865:7865 ashleykza/fooocus:latest",
      },
      links: [
        { label: "GitHub", url: "https://github.com/lllyasviel/Fooocus" },
      ],
    },
    "ai-coqui": {
      title: "Coqui TTS",
      subtitle: "Deep Learning Text-to-Speech",
      color: "#0d9488",
      defaultPort: "5002",
      prefix: "COQUI",
      description: "Coqui TTS provides deep learning text-to-speech with voice cloning capabilities. Supports multiple languages, models (Tacotron2, VITS, XTTS), and custom voice training.",
      gpuRequired: false,
      gpuNote: "CPU works for inference. GPU recommended for voice cloning/training.",
      website: "https://github.com/idiap/coqui-ai-TTS",
      dockerImage: "ghcr.io/coqui-ai/tts:latest",
      dockerPort: "5002",
      installCmds: {
        pip: "pip install coqui-tts && tts-server --port 5002",
        docker: "docker run -d -p 5002:5002 ghcr.io/coqui-ai/tts:latest",
      },
      links: [
        { label: "GitHub", url: "https://github.com/idiap/coqui-ai-TTS" },
        { label: "Models", url: "https://github.com/idiap/coqui-ai-TTS#released-models" },
      ],
      apiDocs: {
        title: "Coqui TTS API", baseUrl: "http://{host}:5002",
        sections: [
          { name: "Speech Synthesis", endpoints: [
            { m: "GET", p: "/api/tts?text={text}", d: "Convert text to speech audio.", res: "audio/wav binary" },
            { m: "GET", p: "/api/tts?text={text}&speaker_id={id}", d: "TTS with specific speaker voice.", res: "audio/wav binary" },
          ]},
        ],
      },
    },
    "ai-bark": {
      title: "Bark",
      subtitle: "Text-to-Audio Generation",
      color: "#b45309",
      defaultPort: "5005",
      prefix: "BARK",
      description: "Suno's Bark model generates realistic speech, music, and sound effects from text prompts. Supports multiple languages, speaker presets, and non-verbal sounds like laughter.",
      gpuRequired: false,
      gpuNote: "GPU with 4+ GB VRAM recommended. CPU mode is slow but works.",
      website: "https://github.com/suno-ai/bark",
      installCmds: {
        pip: "pip install git+https://github.com/suno-ai/bark.git",
      },
      links: [
        { label: "GitHub", url: "https://github.com/suno-ai/bark" },
        { label: "HuggingFace", url: "https://huggingface.co/suno/bark" },
      ],
    },
    "ai-rvc": {
      title: "RVC",
      subtitle: "Real-time Voice Conversion",
      color: "#be185d",
      defaultPort: "7897",
      prefix: "RVC",
      description: "Retrieval-based Voice Conversion. Clone and convert voices in real-time with minimal training data. Train custom voice models from audio samples.",
      gpuRequired: true,
      gpuNote: "Requires NVIDIA GPU with 4+ GB VRAM for real-time voice conversion.",
      website: "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI",
      dockerImage: "alexta69/rvc-webui:latest",
      dockerPort: "7897",
      installCmds: {
        git: "git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI && cd Retrieval-based-Voice-Conversion-WebUI && pip install -r requirements.txt && python infer-web.py",
        docker: "docker run -d --gpus all -p 7897:7897 alexta69/rvc-webui:latest",
      },
      links: [
        { label: "GitHub", url: "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI" },
        { label: "Voice Models", url: "https://voice-models.com/" },
      ],
    },
    "ai-openwebui": {
      title: "Open WebUI",
      subtitle: "ChatGPT-style Interface for LLMs",
      color: "#1e40af",
      defaultPort: "3000",
      prefix: "OPENWEBUI",
      description: "Open WebUI provides a beautiful ChatGPT-like web interface for Ollama and OpenAI-compatible APIs. Features RAG, web search, multi-model support, user management, and conversation history.",
      gpuRequired: false,
      gpuNote: "Open WebUI itself needs no GPU — it connects to your LLM backend (Ollama, vLLM, etc.).",
      website: "https://openwebui.com/",
      dockerImage: "ghcr.io/open-webui/open-webui:main",
      dockerPort: "8080",
      installCmds: {
        docker: "docker run -d -p 3000:8080 -v open-webui:/app/backend/data --add-host=host.docker.internal:host-gateway ghcr.io/open-webui/open-webui:main",
        pip: "pip install open-webui && open-webui serve --port 3000",
      },
      links: [
        { label: "Website", url: "https://openwebui.com/" },
        { label: "GitHub", url: "https://github.com/open-webui/open-webui" },
        { label: "Documentation", url: "https://docs.openwebui.com/" },
      ],
    },
    "ai-chromadb": {
      title: "ChromaDB",
      subtitle: "Vector Database for AI",
      color: "#7c3aed",
      defaultPort: "8000",
      prefix: "CHROMADB",
      description: "ChromaDB is an open-source vector database for storing and querying AI embeddings. Build RAG pipelines, semantic search, and recommendation systems.",
      gpuRequired: false,
      gpuNote: "No GPU required — ChromaDB runs on CPU.",
      website: "https://www.trychroma.com/",
      dockerImage: "chromadb/chroma:latest",
      dockerPort: "8000",
      installCmds: {
        pip: "pip install chromadb && chroma run --host 0.0.0.0 --port 8000",
        docker: "docker run -d -p 8000:8000 chromadb/chroma:latest",
      },
      links: [
        { label: "Documentation", url: "https://docs.trychroma.com/" },
        { label: "GitHub", url: "https://github.com/chroma-core/chroma" },
      ],
      apiDocs: {
        title: "ChromaDB API", baseUrl: "http://{host}:8000",
        sections: [
          { name: "Collections", endpoints: [
            { m: "POST", p: "/api/v1/collections", d: "Create a collection.", body: '{ "name": "my-docs", "metadata": {} }', res: '{ "id": "...", "name": "my-docs" }' },
            { m: "GET", p: "/api/v1/collections", d: "List all collections.", res: '[{"id": "...", "name": "my-docs"}]' },
            { m: "POST", p: "/api/v1/collections/{id}/add", d: "Add documents/embeddings.", body: '{ "ids": ["1"], "documents": ["Hello"], "embeddings": [[0.1, 0.2]] }', res: 'true' },
            { m: "POST", p: "/api/v1/collections/{id}/query", d: "Query by similarity.", body: '{ "query_texts": ["Hello"], "n_results": 5 }', res: '{ "ids": [["1"]], "distances": [[0.1]] }' },
          ]},
        ],
      },
    },
    "ai-custom": {
      title: "Custom Model",
      subtitle: "Deploy Any AI Model",
      color: "#475569",
      defaultPort: "8080",
      prefix: "CUSTOM",
      description: "Deploy any AI model as a managed service. Provide a Docker image, Python script, or Git repository and the dashboard will install and manage it as a service.",
      gpuRequired: false,
      gpuNote: "Depends on your model requirements.",
      website: "",
      links: [],
    },
  };

  // ── Method badge colors ───────────────────────────────────────────────────
  const MC = { GET: { bg: "#dcfce7", c: "#166534", b: "#86efac" }, POST: { bg: "#dbeafe", c: "#1e40af", b: "#93c5fd" }, PUT: { bg: "#fef9c3", c: "#854d0e", b: "#fde047" }, DELETE: { bg: "#fee2e2", c: "#991b1b", b: "#fca5a5" } };
  const mc = (m) => MC[m] || { bg: "#f3f4f6", c: "#374151", b: "#d1d5db" };

  // ── Generate a page for each service ──────────────────────────────────────
  Object.entries(AI_SERVICES).forEach(function(entry) {
    const pageId = entry[0];
    const svc = entry[1];
    const scope = pageId.replace("ai-", "");

    ns.pages[pageId] = function(p) {
      const { Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Alert, Tooltip,
              ActionCard, cfg, run, selectableIps, serviceBusy,
              isScopeLoading, scopeErrors, setPage,
              isServiceRunningStatus, onServiceAction, renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
              copyText } = p;

      const info = p[scope + "Service"] || {};
      const services = p[scope + "PageServices"] || [];
      const httpPort = String(info.http_port || svc.defaultPort).trim();
      const host = String(info.host || "").trim();
      const installed = !!info.installed;
      const running = !!info.running;
      const bestUrl = String(info.https_url || info.http_url || "").trim() || (installed || running ? "http://" + (host || "127.0.0.1") + ":" + httpPort : "");

      const installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : (cfg.os === "darwin" ? "macOS" : cfg.os_label));

      const commonFields = [
        { name: svc.prefix + "_HOST_IP", label: "Host IP", type: "select", options: selectableIps, defaultValue: selectableIps[0] || "", required: true, placeholder: "Select IP" },
        { name: svc.prefix + "_HTTP_PORT", label: "HTTP Port", defaultValue: httpPort, checkPort: true },
        { name: svc.prefix + "_HTTPS_PORT", label: "HTTPS Port (optional)", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty to skip" },
        { name: svc.prefix + "_DOMAIN", label: "Domain (optional)", defaultValue: "", placeholder: "e.g. " + scope + ".example.com" },
        { name: svc.prefix + "_USERNAME", label: "Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
        { name: svc.prefix + "_PASSWORD", label: "Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
      ];

      return (
        <Grid container spacing={2}>
          {/* Description */}
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: svc.color }}>{svc.title} — {svc.subtitle}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{svc.description}</Typography>
                {svc.gpuNote && (
                  <Alert severity={svc.gpuRequired ? "warning" : "info"} sx={{ mt: 1, borderRadius: 2 }}>{svc.gpuNote}</Alert>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Install — OS */}
          <Grid item xs={12} md={svc.dockerImage ? 6 : 12}>
            <ActionCard
              title={"Install " + svc.title + " \u2014 OS (" + installOsLabel + ")"}
              description={"Install " + svc.title + " as a managed OS service."}
              action={cfg.os === "windows" ? "/run/" + scope + "_windows_os" : "/run/" + scope + "_unix_os"}
              fields={commonFields}
              onRun={run}
              color={svc.color}
            />
          </Grid>

          {/* Install — Docker */}
          {svc.dockerImage && (
            <Grid item xs={12} md={6}>
              <ActionCard
                title={"Install " + svc.title + " \u2014 Docker"}
                description={"Deploy " + svc.title + " as a Docker container." + (svc.dockerImage ? " Image: " + svc.dockerImage : "")}
                action={"/run/" + scope + "_docker"}
                fields={commonFields}
                onRun={run}
                color="#0891b2"
              />
            </Grid>
          )}

          {/* Status + Links */}
          <Grid item xs={12} md={4}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: svc.color }}>{svc.title} Status</Typography>
                <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
                <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>
                <Typography variant="body2">Port: <b>{httpPort}</b></Typography>
                {bestUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>URL: <a href={bestUrl} target="_blank" rel="noopener">{bestUrl}</a></Typography>}
                {bestUrl && (
                  <Button variant="contained" size="small" sx={{ mt: 1.5, textTransform: "none", bgcolor: svc.color, "&:hover": { bgcolor: svc.color, filter: "brightness(0.9)" } }}
                    onClick={() => window.open(bestUrl, "_blank", "noopener,noreferrer")}>
                    Open {svc.title}
                  </Button>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Download Links & Install Commands */}
          <Grid item xs={12} md={8}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Download & Install</Typography>

                {/* Links */}
                {svc.links && svc.links.length > 0 && (
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                    {svc.links.map((lnk) => (
                      <Button key={lnk.url} variant="outlined" size="small" href={lnk.url} target="_blank" rel="noopener"
                        sx={{ textTransform: "none", borderRadius: 2, fontWeight: 600, borderColor: svc.color + "44", color: svc.color }}>
                        {lnk.label}
                      </Button>
                    ))}
                  </Stack>
                )}

                {/* Install commands */}
                {svc.installCmds && Object.entries(svc.installCmds).map(function(cmdEntry) {
                  return (
                    <Box key={cmdEntry[0]} sx={{ mb: 1.5 }}>
                      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.3 }}>
                        <Typography variant="caption" fontWeight={700} sx={{ color: "#475569" }}>Install via {cmdEntry[0]}:</Typography>
                        <Tooltip title="Copy command">
                          <Button size="small" variant="text" sx={{ textTransform: "none", minWidth: 0, px: 1, fontSize: 10 }}
                            onClick={() => { if (copyText) copyText(cmdEntry[1], "install command"); else navigator.clipboard && navigator.clipboard.writeText(cmdEntry[1]); }}>
                            Copy
                          </Button>
                        </Tooltip>
                      </Stack>
                      <Paper elevation={0} sx={{ p: 1, bgcolor: "#0d1117", borderRadius: 1.5, fontFamily: "monospace", fontSize: 12, color: "#c9d1d9", wordBreak: "break-all", whiteSpace: "pre-wrap", border: "1px solid #30363d" }}>
                        {cmdEntry[1]}
                      </Paper>
                    </Box>
                  );
                })}

                {/* Downloadable models */}
                {svc.models && svc.models.length > 0 && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>Available Models:</Typography>
                    {svc.models.map((mdl) => (
                      <Paper key={mdl.name} variant="outlined" sx={{ p: 1, mb: 0.5, borderRadius: 1.5 }}>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Typography variant="body2" sx={{ flexGrow: 1 }}><b>{mdl.name}</b> — {mdl.desc}</Typography>
                          <Chip label={mdl.size} size="small" variant="outlined" sx={{ fontSize: 10, height: 18 }} />
                        </Stack>
                      </Paper>
                    ))}
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Services List */}
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="h6" fontWeight={800}>{svc.title} Services</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  {bestUrl && running && (
                    <Button variant="contained" size="small" onClick={() => window.open(bestUrl, "_blank")}
                      sx={{ textTransform: "none", bgcolor: svc.color, "&:hover": { bgcolor: svc.color, filter: "brightness(0.9)" } }}>
                      Open {svc.title}
                    </Button>
                  )}
                  <Button variant="outlined" size="small" sx={{ textTransform: "none" }}>Refresh</Button>
                </Stack>
                {services.length === 0 && (
                  <Typography variant="body2" color="text.secondary">No {svc.title} services deployed yet. Use an Install card above.</Typography>
                )}
                {services.map((s) => (
                  <Paper key={(s.kind || "") + "-" + s.name} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Typography variant="body2"><b>{s.name}</b> ({s.kind})</Typography>
                        {renderServiceUrls(s)}
                        {renderServicePorts(s)}
                      </Box>
                      {renderServiceStatus(s)}
                      <Box sx={{ flexGrow: 1 }} />
                      {renderFolderIcon(s)}
                      <Button size="small" variant="outlined" color={isServiceRunningStatus(s.status, s.sub_status) ? "error" : "success"} disabled={serviceBusy}
                        onClick={() => onServiceAction(isServiceRunningStatus(s.status, s.sub_status) ? "stop" : "start", s)} sx={{ textTransform: "none" }}>
                        {isServiceRunningStatus(s.status, s.sub_status) ? "Stop" : "Start"}
                      </Button>
                      <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", s)} sx={{ textTransform: "none" }}>Restart</Button>
                      <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", s)} sx={{ textTransform: "none" }}>Delete</Button>
                    </Stack>
                  </Paper>
                ))}
              </CardContent>
            </Card>
          </Grid>

          {/* API Docs Button → separate page */}
          {svc.apiDocs && (
            <Grid item xs={12}>
              <Card sx={{ borderRadius: 3, border: "1.5px solid " + svc.color + "44", background: "linear-gradient(135deg, " + svc.color + "05 0%, #ffffff 100%)" }}>
                <CardContent sx={{ py: 2, "&:last-child": { pb: 2 } }}>
                  <Stack direction="row" alignItems="center" spacing={1.5}>
                    <Box sx={{ width: 6, height: 36, borderRadius: 3, bgcolor: svc.color }} />
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="h6" fontWeight={800} sx={{ color: svc.color }}>{svc.apiDocs.title}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {svc.apiDocs.sections.reduce(function(n, s) { return n + s.endpoints.length; }, 0)} API endpoints
                      </Typography>
                    </Box>
                    <Button variant="contained" size="small" onClick={() => setPage(pageId + "-api")}
                      sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, bgcolor: svc.color, "&:hover": { bgcolor: svc.color, filter: "brightness(0.9)" }, px: 3 }}>
                      API Documents
                    </Button>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          )}
        </Grid>
      );
    };

    // ── API Docs sub-page ─────────────────────────────────────────────────
    if (svc.apiDocs) {
      ns.pages[pageId + "-api"] = function(p) {
        const { Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Tooltip, Alert, setPage, copyText } = p;
        const info = p[scope + "Service"] || {};
        const host = String(info.host || "").trim() || "{host}";
        const httpsPort = String(info.https_port || "").trim();
        const port = httpsPort || String(info.http_port || svc.defaultPort).trim();
        const proto = httpsPort ? "https" : "http";
        const base = svc.apiDocs.baseUrl.replace("http://", proto + "://").replace("{host}", host).replace("{port}", port).replace(/:\d+/, ":" + port);

        const doCopy = function(text) { if (copyText) copyText(text, "cURL"); else if (navigator.clipboard) navigator.clipboard.writeText(text); };

        return (
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Card sx={{ borderRadius: 3, border: "1.5px solid " + svc.color + "44" }}>
                <CardContent>
                  <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
                    <Button variant="outlined" size="small" onClick={() => setPage(pageId)} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, borderColor: svc.color, color: svc.color }}>
                      Back to {svc.title}
                    </Button>
                    <Typography variant="h5" fontWeight={900} sx={{ color: svc.color, flexGrow: 1 }}>{svc.apiDocs.title}</Typography>
                  </Stack>
                  <Alert severity="info" sx={{ borderRadius: 2 }}>
                    <b>Base URL:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{base}</code>
                  </Alert>
                </CardContent>
              </Card>
            </Grid>
            {svc.apiDocs.sections.map(function(sec, si) {
              return (
                <Grid item xs={12} key={si}>
                  <Card sx={{ borderRadius: 3, border: "1px solid " + svc.color + "33" }}>
                    <CardContent>
                      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                        <Box sx={{ width: 5, height: 28, borderRadius: 3, bgcolor: svc.color }} />
                        <Typography variant="h6" fontWeight={800} sx={{ color: svc.color, flexGrow: 1 }}>{sec.name}</Typography>
                        <Chip label={sec.endpoints.length + " endpoints"} size="small" variant="outlined" sx={{ fontSize: 10, height: 20 }} />
                      </Stack>
                      {sec.endpoints.map(function(ep, ei) {
                        var cl = mc(ep.m);
                        var fullUrl = base + ep.p;
                        return (
                          <Paper key={ei} variant="outlined" sx={{ p: 2, mb: 1.5, borderRadius: 2, "&:hover": { borderColor: svc.color + "66" } }}>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "flex-start", md: "center" }}>
                              <Chip label={ep.m} size="small" sx={{ bgcolor: cl.bg, color: cl.c, border: "1px solid " + cl.b, fontWeight: 800, fontFamily: "monospace", minWidth: 70, justifyContent: "center" }} />
                              <Typography sx={{ fontFamily: "monospace", fontWeight: 600, wordBreak: "break-all", flexGrow: 1, fontSize: 14 }}>{fullUrl}</Typography>
                              <Tooltip title="Copy cURL">
                                <Button size="small" variant="outlined" onClick={function() { doCopy("curl -X " + ep.m + ' "' + fullUrl + '"'); }} sx={{ textTransform: "none", minWidth: 0, px: 1.5, fontSize: 11, borderColor: "#e2e8f0" }}>cURL</Button>
                              </Tooltip>
                            </Stack>
                            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{ep.d}</Typography>
                            {ep.body && (
                              <Box sx={{ mt: 1.5 }}>
                                <Typography variant="caption" fontWeight={700} sx={{ color: "#475569" }}>Request Body:</Typography>
                                <Paper elevation={0} sx={{ mt: 0.3, p: 1.5, bgcolor: "#f8fafc", borderRadius: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all", border: "1px solid #e2e8f0" }}>{ep.body}</Paper>
                              </Box>
                            )}
                            {ep.res && (
                              <Box sx={{ mt: 1.5 }}>
                                <Typography variant="caption" fontWeight={700} sx={{ color: "#475569" }}>Response:</Typography>
                                <Paper elevation={0} sx={{ mt: 0.3, p: 1.5, bgcolor: "#f0fdf4", borderRadius: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all", border: "1px solid #dcfce7" }}>{ep.res}</Paper>
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
    }
  });
})();
