(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  // ── Platform Services page ────────────────────────────────────────────────
  ns.pages["platform-services"] = function renderPlatformServicesPage(p) {
    const { Grid, Card, CardContent, Typography, Divider, NavCard, setPage, startNewWebsiteDeployment, setFileManagerData } = p;
    return (
      <Grid container spacing={2}>
        {/* ── Page description ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>Platform Services</Typography>
              <Typography variant="body2" color="text.secondary">
                Install, deploy, and manage all server services from one place. Choose a service category below to get started.
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Section 1: Running Services ── */}
        <Grid item xs={12}>
          <Typography variant="overline" fontWeight={700} sx={{ ml: 0.5, letterSpacing: 1, color: "#475569" }}>Running Services</Typography>
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="DotNet APIs" text="Deploy ASP.NET / .NET Core APIs via Docker, OS service, or IIS." onClick={() => setPage("dotnet")} />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Python APIs" text="Deploy Python APIs via Docker, OS service, or IIS." onClick={() => setPage("python-api")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="S3 Storage" text="Install MinIO S3-compatible object storage via Docker, OS service, or IIS." onClick={() => setPage("s3")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="MongoDB" text="Install MongoDB with a Compass-style web admin UI via Docker or OS service." onClick={() => setPage("mongo")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Python & Jupyter" text="Install Python runtime and Jupyter notebooks. Manage kernels and runtime services." onClick={() => setPage("python")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Websites" text="Deploy static sites, Flutter web, Next.js exports via Docker, OS service, or IIS." onClick={() => startNewWebsiteDeployment()} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Proxy" text="Install and manage the multi-layer proxy/VPN stack." onClick={() => setPage("proxy")} outlined />
        </Grid>

        {/* ── Section 2: Tools & Infrastructure ── */}
        <Grid item xs={12} sx={{ mt: 1 }}>
          <Typography variant="overline" fontWeight={700} sx={{ ml: 0.5, letterSpacing: 1, color: "#475569" }}>Tools & Infrastructure</Typography>
        </Grid>
        <Grid item xs={12} md={4}>
          <NavCard title="Files" text="Browse, upload, edit, and manage server files." onClick={() => { setPage("files"); setFileManagerData(null); }} outlined />
        </Grid>
        <Grid item xs={12} md={4}>
          <NavCard title="Docker" text="Install Docker and manage containers, images, and logs." onClick={() => setPage("docker")} outlined />
        </Grid>
        <Grid item xs={12} md={4}>
          <NavCard title="SSL & Certificates" text="Manage TLS certificates: Let's Encrypt, custom certs, and service assignment." onClick={() => setPage("ssl")} outlined />
        </Grid>
      </Grid>
    );
  };

  // ── AI & ML Services page ─────────────────────────────────────────────────
  ns.pages["ai-ml"] = function renderAiMlPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Alert, Chip, Paper,
      NavCard, cfg, setPage, isScopeLoading,
    } = p;

    const [activeCategory, setActiveCategory] = React.useState("all");

    const categories = [
      {
        id: "llm",
        label: "LLMs",
        color: "#1e40af",
        bg: "#eff6ff",
        border: "#bfdbfe",
        description: "Large Language Models for text generation, chat, code, and reasoning.",
        services: [
          { title: "Ollama", text: "Run LLMs locally (Llama 3, Mistral, Gemma, Phi, etc.). OpenAI-compatible API with GPU acceleration.", page: "ai-ollama", hasApi: true },
          { title: "Text Generation WebUI", text: "Full-featured web UI for LLMs with GPTQ, GGUF, AWQ, and EXL2 backends.", page: "ai-tgwui" },
          { title: "vLLM", text: "High-throughput LLM serving engine with PagedAttention. Production-grade OpenAI-compatible API.", page: "ai-vllm" },
          { title: "llama.cpp", text: "Lightweight C++ LLM inference. Runs GGUF models on CPU and GPU with minimal dependencies.", page: "ai-llamacpp" },
          { title: "DeepSeek", text: "Deploy DeepSeek models locally via Ollama or vLLM. Optimized for code and reasoning tasks.", page: "ai-deepseek" },
          { title: "LocalAI", text: "OpenAI-compatible local API supporting LLMs, image generation, audio, and embeddings.", page: "ai-localai" },
        ],
      },
      {
        id: "image-video",
        label: "Image & Video",
        color: "#7c3aed",
        bg: "#f5f3ff",
        border: "#c4b5fd",
        description: "Image generation, editing, video processing, and visual AI models.",
        services: [
          { title: "ComfyUI", text: "Node-based Stable Diffusion workflow editor. Supports SDXL, ControlNet, LoRA, and custom pipelines.", page: "ai-comfyui" },
          { title: "Stable Diffusion WebUI", text: "AUTOMATIC1111's web UI for Stable Diffusion image generation with extensions ecosystem.", page: "ai-sdwebui" },
          { title: "SAM3 - Segment Anything", text: "Meta's advanced object detection & segmentation. Text/point/box prompts, video tracking, live camera.", page: "ai-sam3", hasApi: true },
          { title: "Fooocus", text: "Simplified Stable Diffusion with Midjourney-like quality. Minimal configuration needed.", page: "ai-fooocus" },
        ],
      },
      {
        id: "voice",
        label: "Voice & Audio",
        color: "#0d9488",
        bg: "#f0fdfa",
        border: "#99f6e4",
        description: "Text-to-Speech, Speech-to-Text, voice cloning, and audio processing.",
        services: [
          { title: "Whisper", text: "OpenAI's speech recognition model. Transcribe and translate audio in 99+ languages.", page: "ai-whisper" },
          { title: "Piper TTS", text: "Fast local text-to-speech with natural voices. Supports 30+ languages, runs on CPU.", page: "ai-piper" },
          { title: "Coqui TTS", text: "Deep learning text-to-speech with voice cloning. Multiple models and languages.", page: "ai-coqui" },
          { title: "Bark", text: "Suno's text-to-audio model. Generate speech, music, and sound effects from text prompts.", page: "ai-bark" },
          { title: "RVC (Voice Changer)", text: "Real-time voice conversion using AI. Clone voices with minimal training data.", page: "ai-rvc" },
        ],
      },
      {
        id: "tools",
        label: "AI Tools",
        color: "#b45309",
        bg: "#fffbeb",
        border: "#fde68a",
        description: "Embeddings, vector databases, RAG pipelines, and general-purpose AI tools.",
        services: [
          { title: "Custom Model", text: "Deploy any AI model as a managed service with custom Docker or OS configuration.", page: "ai-custom" },
          { title: "Open WebUI", text: "ChatGPT-style web interface for Ollama and OpenAI-compatible APIs with RAG support.", page: "ai-openwebui" },
          { title: "ChromaDB", text: "Open-source vector database for AI embeddings. Build RAG and semantic search pipelines.", page: "ai-chromadb" },
        ],
      },
    ];

    const visibleCategories = activeCategory === "all" ? categories : categories.filter((c) => c.id === activeCategory);

    return (
      <Grid container spacing={2}>
        {/* ── Header ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#6d28d9" }}>
                AI & ML Services
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Deploy and manage AI models, inference servers, and machine learning workloads on your server.
                Services are grouped by their nature — select a category or browse all.
              </Typography>
              <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                Most AI/ML workloads benefit from a dedicated GPU. CPU-only inference is supported but will be significantly slower for large models.
                Ensure your server meets the VRAM/RAM requirements for the models you plan to deploy.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Category filter buttons ── */}
        <Grid item xs={12}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              variant={activeCategory === "all" ? "contained" : "outlined"}
              size="small"
              onClick={() => setActiveCategory("all")}
              sx={{
                textTransform: "none", borderRadius: 2, fontWeight: 700, px: 2,
                ...(activeCategory === "all" ? { bgcolor: "#6d28d9", "&:hover": { bgcolor: "#5b21b6" } } : { borderColor: "#6d28d9", color: "#6d28d9" }),
              }}
            >
              All Services
            </Button>
            {categories.map((cat) => (
              <Button
                key={cat.id}
                variant={activeCategory === cat.id ? "contained" : "outlined"}
                size="small"
                onClick={() => setActiveCategory(cat.id)}
                sx={{
                  textTransform: "none", borderRadius: 2, fontWeight: 700, px: 2,
                  ...(activeCategory === cat.id ? { bgcolor: cat.color, "&:hover": { bgcolor: cat.color, filter: "brightness(0.9)" } } : { borderColor: cat.color, color: cat.color }),
                }}
              >
                {cat.label}
              </Button>
            ))}
          </Stack>
        </Grid>

        {/* ── Category sections with service cards ── */}
        {visibleCategories.map((cat) => (
          <Grid item xs={12} key={cat.id}>
            <Card sx={{ borderRadius: 3, border: `1.5px solid ${cat.border}`, background: `linear-gradient(135deg, ${cat.bg} 0%, #ffffff 100%)` }}>
              <CardContent>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                  <Chip label={cat.label} size="small" sx={{ bgcolor: cat.color, color: "#fff", fontWeight: 700 }} />
                  <Typography variant="h6" fontWeight={800} sx={{ color: cat.color, flexGrow: 1 }}>
                    {cat.label}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {cat.services.length} service{cat.services.length !== 1 ? "s" : ""}
                  </Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                  {cat.description}
                </Typography>
                <Grid container spacing={1.5}>
                  {cat.services.map((svc) => (
                    <Grid item xs={12} sm={6} md={4} key={svc.page}>
                      <Paper
                        variant="outlined"
                        sx={{
                          p: 1.5, borderRadius: 2, cursor: "pointer", height: "100%",
                          transition: "all 0.15s ease",
                          "&:hover": { borderColor: cat.color, boxShadow: `0 2px 8px ${cat.color}22`, transform: "translateY(-1px)" },
                        }}
                        onClick={() => setPage(svc.page)}
                      >
                        <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
                          <Typography variant="subtitle2" fontWeight={800}>{svc.title}</Typography>
                          {svc.hasApi && <Chip label="API" size="small" variant="outlined" sx={{ fontSize: 10, height: 18, color: cat.color, borderColor: cat.color }} />}
                        </Stack>
                        <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.4 }}>
                          {svc.text}
                        </Typography>
                      </Paper>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>
          </Grid>
        ))}

        {/* ── Deployed Services List ── */}
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Deployed AI Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading && isScopeLoading("ai")} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}>
                  {isScopeLoading && isScopeLoading("ai") ? "Refreshing..." : "Refresh"}
                </Button>
              </Stack>
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: 200, overflow: "auto" }}>
                <Typography variant="body2" color="text.secondary">No AI services deployed yet. Select a service above to get started.</Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  // ── OS Agents page ──────────────────────────────────────────────────────────
  ns.pages["os-agents"] = function renderOsAgentsPage(p) {
    var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
    var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
    var Box = p.Box, Paper = p.Paper, Chip = p.Chip, Alert = p.Alert;
    var setPage = p.setPage;

    var _ac = React.useState("all");
    var activeCategory = _ac[0], setActiveCategory = _ac[1];

    var categories = [
      {
        id: "agents",
        label: "AI Agents",
        color: "#b45309",
        bg: "#fffbeb",
        border: "#fde68a",
        description: "Autonomous AI agents that can execute tasks, write code, browse the web, and interact with your OS.",
        services: [
          { title: "Open Interpreter", text: "Natural language interface to your computer. Runs code, manages files, browses web. Supports GPT-4, Claude, Llama.", page: "agent-openinterpreter" },
          { title: "OpenHands (OpenDevin)", text: "Autonomous AI software developer. Plans, writes code, runs tests, and deploys. Full dev environment in sandbox.", page: "agent-openhands" },
          { title: "AutoGPT", text: "Autonomous GPT-4 agent. Chains prompts to achieve complex goals. Web search, file I/O, code execution.", page: "agent-autogpt" },
          { title: "CrewAI", text: "Framework for orchestrating multiple AI agents working together. Define roles, goals, and tasks for a team of agents.", page: "agent-crewai" },
          { title: "MetaGPT", text: "Multi-agent framework that simulates a software company. Agents play PM, architect, engineer, QA roles.", page: "agent-metagpt" },
        ],
      },
      {
        id: "frameworks",
        label: "Agent Frameworks",
        color: "#0f766e",
        bg: "#f0fdfa",
        border: "#99f6e4",
        description: "Frameworks and tools for building, orchestrating, and deploying AI agent workflows.",
        services: [
          { title: "LangChain", text: "Build LLM-powered applications with chains, agents, RAG, and tool use. Python and JS SDKs.", page: "agent-langchain" },
          { title: "LangGraph", text: "Build stateful, multi-actor LLM applications with graph-based workflows. By LangChain team.", page: "agent-langgraph" },
          { title: "LlamaIndex", text: "Data framework for LLM applications. Connect your data to LLMs with RAG pipelines and agents.", page: "agent-llamaindex" },
          { title: "Haystack", text: "End-to-end NLP framework. Build search, QA, and conversational AI pipelines with any LLM.", page: "agent-haystack" },
        ],
      },
      {
        id: "tools",
        label: "Agent Tools & UIs",
        color: "#7c3aed",
        bg: "#f5f3ff",
        border: "#c4b5fd",
        description: "Web UIs, dashboards, and tools for managing and interacting with AI agents.",
        services: [
          { title: "Dify", text: "Visual AI workflow builder. Create chatbots, agents, and RAG apps with drag-and-drop. Self-hosted.", page: "agent-dify" },
          { title: "Flowise", text: "Drag-and-drop UI for building LLM flows. Visual LangChain/LlamaIndex builder. Self-hosted.", page: "agent-flowise" },
          { title: "n8n", text: "Workflow automation platform with AI capabilities. Connect 400+ services with LLM-powered nodes.", page: "agent-n8n" },
          { title: "Activepieces", text: "Open-source automation platform. Build AI-powered workflows with no-code builder.", page: "agent-activepieces" },
        ],
      },
    ];

    var visibleCategories = activeCategory === "all" ? categories : categories.filter(function(c) { return c.id === activeCategory; });

    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#b45309" }}>
                OS Agents & Automation
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Deploy autonomous AI agents that can browse the web, write code, execute commands, manage files, and automate complex tasks on your server.
              </Typography>
              <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                Most agents require an LLM backend (Ollama, OpenAI API, or Claude API). Install Ollama first for fully local operation.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button variant={activeCategory === "all" ? "contained" : "outlined"} size="small" onClick={function() { setActiveCategory("all"); }}
              sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, px: 2, ...(activeCategory === "all" ? { bgcolor: "#b45309", "&:hover": { bgcolor: "#92400e" } } : { borderColor: "#b45309", color: "#b45309" }) }}>
              All
            </Button>
            {categories.map(function(cat) {
              return (
                <Button key={cat.id} variant={activeCategory === cat.id ? "contained" : "outlined"} size="small" onClick={function() { setActiveCategory(cat.id); }}
                  sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, px: 2, ...(activeCategory === cat.id ? { bgcolor: cat.color, "&:hover": { bgcolor: cat.color, filter: "brightness(0.9)" } } : { borderColor: cat.color, color: cat.color }) }}>
                  {cat.label}
                </Button>
              );
            })}
          </Stack>
        </Grid>

        {visibleCategories.map(function(cat) {
          return (
            <Grid item xs={12} key={cat.id}>
              <Card sx={{ borderRadius: 3, border: "1.5px solid " + cat.border, background: "linear-gradient(135deg, " + cat.bg + " 0%, #ffffff 100%)" }}>
                <CardContent>
                  <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                    <Chip label={cat.label} size="small" sx={{ bgcolor: cat.color, color: "#fff", fontWeight: 700 }} />
                    <Typography variant="h6" fontWeight={800} sx={{ color: cat.color, flexGrow: 1 }}>{cat.label}</Typography>
                    <Typography variant="body2" color="text.secondary">{cat.services.length} services</Typography>
                  </Stack>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{cat.description}</Typography>
                  <Grid container spacing={1.5}>
                    {cat.services.map(function(svc) {
                      return (
                        <Grid item xs={12} sm={6} md={4} key={svc.page}>
                          <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, cursor: "pointer", height: "100%", transition: "all 0.15s ease", "&:hover": { borderColor: cat.color, boxShadow: "0 2px 8px " + cat.color + "22", transform: "translateY(-1px)" } }}
                            onClick={function() { setPage(svc.page); }}>
                            <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 0.5 }}>{svc.title}</Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.4 }}>{svc.text}</Typography>
                          </Paper>
                        </Grid>
                      );
                    })}
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>
    );
  };

  // ── Logs page ───────────────────────────────────────────────────────────────
  function LogsPageInner(p) {
    const { Box, Button, Card, CardContent, Typography, Stack, Paper, Tooltip, termText, copyText } = p;
    const [autoScroll, setAutoScroll] = React.useState(true);
    const [cleared, setCleared] = React.useState(false);
    const [clearedAt, setClearedAt] = React.useState("");
    const scrollRef = React.useRef(null);
    const displayText = cleared ? "" : (termText || "");

    React.useEffect(() => {
      if (cleared && termText !== clearedAt) setCleared(false);
    }, [termText, cleared, clearedAt]);

    React.useEffect(() => {
      if (autoScroll && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [displayText, autoScroll]);

    const isEmpty = !displayText || displayText.trim() === "" || displayText.trim() === "Ready. Click Start to run and stream output.";

    return (
      <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
        <CardContent sx={{ p: 3 }}>
          <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2, flexWrap: "wrap" }}>
            <Typography variant="h6" fontWeight={800} sx={{ flexGrow: 1 }}>System Logs</Typography>
            <Tooltip title={autoScroll ? "Auto-scroll is ON" : "Auto-scroll is OFF"}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: "0.85rem", userSelect: "none" }}>
                <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} style={{ accentColor: "#2563eb", width: 16, height: 16, cursor: "pointer" }} />
                Auto-scroll
              </label>
            </Tooltip>
            <Button size="small" variant="outlined" disabled={isEmpty} onClick={() => { if (copyText) copyText(displayText, "Logs"); else navigator.clipboard?.writeText(displayText); }} sx={{ textTransform: "none" }}>Copy</Button>
            <Button size="small" variant="outlined" color="error" disabled={isEmpty} onClick={() => { setCleared(true); setClearedAt(termText || ""); }} sx={{ textTransform: "none" }}>Clear</Button>
          </Stack>
          <Paper ref={scrollRef} elevation={0} sx={{
            bgcolor: "#0d1117", borderRadius: 2, border: "1px solid #30363d", p: 2,
            minHeight: "calc(100vh - 340px)", maxHeight: "calc(100vh - 340px)",
            overflowY: "auto", overflowX: "auto",
            fontFamily: "'Cascadia Code','Fira Code','Consolas','Monaco',monospace",
            fontSize: "0.85rem", lineHeight: 1.6, color: "#c9d1d9",
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {isEmpty
              ? <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "calc(100vh - 400px)", color: "#484f58" }}>
                  <Typography variant="h6" sx={{ color: "#8b949e", mb: 1, fontWeight: 600 }}>No logs captured yet</Typography>
                  <Typography variant="body2" sx={{ color: "#484f58" }}>Logs will appear here when you run services or commands.</Typography>
                </Box>
              : displayText
            }
          </Paper>
        </CardContent>
      </Card>
    );
  }
  ns.pages.logs = function renderLogsPage(p) {
    return React.createElement(LogsPageInner, p);
  };

  // ── Home page ─────────────────────────────────────────────────────────────
  ns.pages.home = function renderHomePage(p) {
    const { Card, CardContent, Typography, Grid, Button, Box, setPage } = p;

    const categories = [
      {
        title: "Platform Services",
        subtitle: "Infrastructure & Deployment",
        description: "Install and manage APIs, Docker, S3 storage, MongoDB, Proxy, Python, Websites, SSL certificates, and file management tools.",
        page: "platform-services",
        color: "#1e40af",
        bg: "linear-gradient(135deg,#eff6ff 0%,#dbeafe 100%)",
        border: "#bfdbfe",
      },
      {
        title: "AI & ML Services",
        subtitle: "Machine Learning & Intelligence",
        description: "Deploy and manage AI models, machine learning pipelines, inference servers, and data science workloads.",
        page: "ai-ml",
        color: "#6d28d9",
        bg: "linear-gradient(135deg,#f5f3ff 0%,#ede9fe 100%)",
        border: "#c4b5fd",
      },
      {
        title: "OS Agents",
        subtitle: "Autonomous AI Agents & Automation",
        description: "Deploy autonomous AI agents that can browse the web, write code, execute commands, and automate tasks on your server.",
        page: "os-agents",
        color: "#b45309",
        bg: "linear-gradient(135deg,#fffbeb 0%,#fef3c7 100%)",
        border: "#fde68a",
      },
    ];

    return (
      <Grid container spacing={3} sx={{ mt: 1 }}>
        {categories.map((cat) => (
          <Grid item xs={12} md={4} key={cat.page}>
            <Card
              sx={{
                borderRadius: 4,
                border: `1.5px solid ${cat.border}`,
                background: cat.bg,
                height: "100%",
                display: "flex",
                flexDirection: "column",
                boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
                transition: "box-shadow 0.2s",
                "&:hover": { boxShadow: "0 6px 24px rgba(0,0,0,0.12)" },
              }}
            >
              <CardContent sx={{ flexGrow: 1, p: 3, display: "flex", flexDirection: "column" }}>
                <Typography variant="overline" fontWeight={800} sx={{ color: cat.color, letterSpacing: 1.2, fontSize: 11 }}>
                  {cat.subtitle}
                </Typography>
                <Typography variant="h5" fontWeight={900} sx={{ color: cat.color, mt: 0.5, mb: 1.5 }}>
                  {cat.title}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1, mb: 3, lineHeight: 1.7 }}>
                  {cat.description}
                </Typography>
                <Button
                  variant="contained"
                  fullWidth
                  onClick={() => setPage(cat.page)}
                  sx={{
                    textTransform: "none",
                    fontWeight: 800,
                    borderRadius: 2.5,
                    py: 1.2,
                    fontSize: 15,
                    bgcolor: cat.color,
                    "&:hover": { bgcolor: cat.color, filter: "brightness(1.1)" },
                  }}
                >
                  Open {cat.title}
                </Button>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  };
})();
