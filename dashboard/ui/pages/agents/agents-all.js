(() => {
  var ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  var AGENTS = {
    "agent-openinterpreter": {
      title: "Open Interpreter",
      color: "#b45309",
      defaultPort: "8080",
      prefix: "OPENINTERPRETER",
      description: "Natural language interface to your computer. Run code (Python, JS, Shell), manage files, control browser, and more — all through conversation. Supports GPT-4, Claude, Ollama, and local models.",
      website: "https://openinterpreter.com/",
      dockerImage: "openinterpreter/open-interpreter:latest",
      installCmds: {
        pip: "pip install open-interpreter",
        docker: "docker run -d -p 8080:8080 openinterpreter/open-interpreter:latest --server",
      },
      links: [
        { label: "Website", url: "https://openinterpreter.com/" },
        { label: "GitHub", url: "https://github.com/OpenInterpreter/open-interpreter" },
        { label: "Documentation", url: "https://docs.openinterpreter.com/" },
      ],
    },
    "agent-openhands": {
      title: "OpenHands (OpenDevin)",
      color: "#1e40af",
      defaultPort: "3000",
      prefix: "OPENHANDS",
      description: "Autonomous AI software developer agent. Plans architecture, writes code, runs tests, fixes bugs, and deploys — all in a sandboxed environment. Supports multiple LLM backends.",
      website: "https://www.all-hands.dev/",
      dockerImage: "ghcr.io/all-hands-ai/openhands:latest",
      installCmds: {
        docker: "docker run -d -p 3000:3000 -e SANDBOX_RUNTIME_CONTAINER_IMAGE=ghcr.io/all-hands-ai/runtime:latest ghcr.io/all-hands-ai/openhands:latest",
      },
      links: [
        { label: "Website", url: "https://www.all-hands.dev/" },
        { label: "GitHub", url: "https://github.com/All-Hands-AI/OpenHands" },
        { label: "Documentation", url: "https://docs.all-hands.dev/" },
      ],
    },
    "agent-autogpt": {
      title: "AutoGPT",
      color: "#059669",
      defaultPort: "8000",
      prefix: "AUTOGPT",
      description: "Autonomous GPT-4 agent that chains prompts to achieve complex goals. Web browsing, file management, code execution, and long-term memory. Pioneer of the AI agent movement.",
      website: "https://agpt.co/",
      dockerImage: "",
      installCmds: {
        git: "git clone https://github.com/Significant-Gravitas/AutoGPT.git && cd AutoGPT && docker compose up -d",
        pip: "pip install autogpt-forge",
      },
      links: [
        { label: "Website", url: "https://agpt.co/" },
        { label: "GitHub", url: "https://github.com/Significant-Gravitas/AutoGPT" },
        { label: "Documentation", url: "https://docs.agpt.co/" },
      ],
    },
    "agent-crewai": {
      title: "CrewAI",
      color: "#7c3aed",
      defaultPort: "8080",
      prefix: "CREWAI",
      description: "Framework for orchestrating multiple AI agents as a team. Define roles, goals, and tasks for each agent. Built-in tools for web search, file I/O, and code execution.",
      website: "https://www.crewai.com/",
      installCmds: {
        pip: "pip install crewai crewai-tools",
      },
      links: [
        { label: "Website", url: "https://www.crewai.com/" },
        { label: "GitHub", url: "https://github.com/crewAIInc/crewAI" },
        { label: "Documentation", url: "https://docs.crewai.com/" },
      ],
    },
    "agent-metagpt": {
      title: "MetaGPT",
      color: "#dc2626",
      defaultPort: "8080",
      prefix: "METAGPT",
      description: "Multi-agent framework that simulates a software company. Agents play roles (PM, Architect, Engineer, QA) and collaborate to build software from a single requirement.",
      website: "https://www.deepwisdom.ai/",
      installCmds: {
        pip: "pip install metagpt",
        git: "git clone https://github.com/geekan/MetaGPT.git && cd MetaGPT && pip install -e .",
      },
      links: [
        { label: "GitHub", url: "https://github.com/geekan/MetaGPT" },
        { label: "Documentation", url: "https://docs.deepwisdom.ai/" },
      ],
    },
    "agent-langchain": {
      title: "LangChain + LangServe",
      color: "#0f766e",
      defaultPort: "8000",
      prefix: "LANGCHAIN",
      description: "Build LLM-powered applications with chains, agents, RAG, and tool use. LangServe deploys chains as REST APIs. Python and JavaScript SDKs available.",
      website: "https://www.langchain.com/",
      installCmds: {
        pip: "pip install langchain langchain-community langserve uvicorn",
      },
      links: [
        { label: "Website", url: "https://www.langchain.com/" },
        { label: "GitHub", url: "https://github.com/langchain-ai/langchain" },
        { label: "Documentation", url: "https://python.langchain.com/" },
        { label: "LangSmith", url: "https://smith.langchain.com/" },
      ],
    },
    "agent-langgraph": {
      title: "LangGraph",
      color: "#0f766e",
      defaultPort: "8123",
      prefix: "LANGGRAPH",
      description: "Build stateful, multi-actor LLM applications with graph-based workflows. Supports cycles, branching, persistence, and human-in-the-loop. By the LangChain team.",
      website: "https://www.langchain.com/langgraph",
      installCmds: {
        pip: "pip install langgraph langgraph-cli",
      },
      links: [
        { label: "Documentation", url: "https://langchain-ai.github.io/langgraph/" },
        { label: "GitHub", url: "https://github.com/langchain-ai/langgraph" },
      ],
    },
    "agent-llamaindex": {
      title: "LlamaIndex",
      color: "#7c3aed",
      defaultPort: "8000",
      prefix: "LLAMAINDEX",
      description: "Data framework for LLM applications. Connect your private data to LLMs with RAG pipelines, data agents, and query engines. Supports 100+ data connectors.",
      website: "https://www.llamaindex.ai/",
      installCmds: {
        pip: "pip install llama-index",
      },
      links: [
        { label: "Website", url: "https://www.llamaindex.ai/" },
        { label: "GitHub", url: "https://github.com/run-llama/llama_index" },
        { label: "Documentation", url: "https://docs.llamaindex.ai/" },
      ],
    },
    "agent-haystack": {
      title: "Haystack",
      color: "#1e40af",
      defaultPort: "8000",
      prefix: "HAYSTACK",
      description: "End-to-end NLP framework by deepset. Build production-ready search, QA, and conversational AI pipelines with any LLM. Modular pipeline architecture.",
      website: "https://haystack.deepset.ai/",
      installCmds: {
        pip: "pip install haystack-ai",
      },
      links: [
        { label: "Website", url: "https://haystack.deepset.ai/" },
        { label: "GitHub", url: "https://github.com/deepset-ai/haystack" },
        { label: "Documentation", url: "https://docs.haystack.deepset.ai/" },
      ],
    },
    "agent-dify": {
      title: "Dify",
      color: "#2563eb",
      defaultPort: "3000",
      prefix: "DIFY",
      description: "Visual AI workflow builder. Create chatbots, agents, and RAG applications with drag-and-drop. Self-hosted with beautiful UI. Supports all major LLM providers.",
      dockerImage: "langgenius/dify-api:latest",
      installCmds: {
        docker: "git clone https://github.com/langgenius/dify.git && cd dify/docker && docker compose up -d",
      },
      links: [
        { label: "Website", url: "https://dify.ai/" },
        { label: "GitHub", url: "https://github.com/langgenius/dify" },
        { label: "Documentation", url: "https://docs.dify.ai/" },
      ],
    },
    "agent-flowise": {
      title: "Flowise",
      color: "#059669",
      defaultPort: "3000",
      prefix: "FLOWISE",
      description: "Drag-and-drop UI for building LLM flows and agents. Visual LangChain/LlamaIndex builder. No-code chatbot and RAG pipeline creation. Self-hosted.",
      dockerImage: "flowiseai/flowise:latest",
      installCmds: {
        npm: "npx flowise start",
        docker: "docker run -d -p 3000:3000 flowiseai/flowise:latest",
      },
      links: [
        { label: "Website", url: "https://flowiseai.com/" },
        { label: "GitHub", url: "https://github.com/FlowiseAI/Flowise" },
        { label: "Documentation", url: "https://docs.flowiseai.com/" },
      ],
    },
    "agent-n8n": {
      title: "n8n",
      color: "#ea580c",
      defaultPort: "5678",
      prefix: "N8N",
      description: "Workflow automation platform with AI capabilities. Connect 400+ services with LLM-powered AI nodes. Visual workflow editor. Self-hosted alternative to Zapier.",
      dockerImage: "n8nio/n8n:latest",
      installCmds: {
        npm: "npx n8n start",
        docker: "docker run -d -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n:latest",
      },
      links: [
        { label: "Website", url: "https://n8n.io/" },
        { label: "GitHub", url: "https://github.com/n8n-io/n8n" },
        { label: "Documentation", url: "https://docs.n8n.io/" },
      ],
    },
    "agent-activepieces": {
      title: "Activepieces",
      color: "#7c3aed",
      defaultPort: "8080",
      prefix: "ACTIVEPIECES",
      description: "Open-source automation platform. Build AI-powered workflows with no-code visual builder. 100+ integrations. Self-hosted alternative to Make/Zapier.",
      dockerImage: "activepieces/activepieces:latest",
      installCmds: {
        docker: "docker run -d -p 8080:80 activepieces/activepieces:latest",
      },
      links: [
        { label: "Website", url: "https://www.activepieces.com/" },
        { label: "GitHub", url: "https://github.com/activepieces/activepieces" },
        { label: "Documentation", url: "https://www.activepieces.com/docs" },
      ],
    },
  };

  // Generate pages for each agent
  Object.keys(AGENTS).forEach(function(pageId) {
    var svc = AGENTS[pageId];
    var scope = pageId.replace("agent-", "");

    ns.pages[pageId] = function(p) {
      var Grid = p.Grid, Card = p.Card, CardContent = p.CardContent;
      var Typography = p.Typography, Stack = p.Stack, Button = p.Button;
      var Box = p.Box, Paper = p.Paper, Chip = p.Chip, Alert = p.Alert, Tooltip = p.Tooltip;
      var ActionCard = p.ActionCard, cfg = p.cfg, run = p.run;
      var selectableIps = p.selectableIps, serviceBusy = p.serviceBusy;
      var setPage = p.setPage, copyText = p.copyText;

      var installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : "macOS");

      var commonFields = [
        { name: svc.prefix + "_HOST_IP", label: "Host IP", type: "select", options: selectableIps, defaultValue: selectableIps[0] || "", required: true, placeholder: "Select IP" },
        { name: svc.prefix + "_HTTP_PORT", label: "HTTP Port", defaultValue: svc.defaultPort, checkPort: true },
        { name: svc.prefix + "_HTTPS_PORT", label: "HTTPS Port (optional)", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty" },
        { name: svc.prefix + "_USERNAME", label: "Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
        { name: svc.prefix + "_PASSWORD", label: "Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
      ];

      return (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: svc.color }}>{svc.title}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{svc.description}</Typography>
                <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                  Most agents require an LLM backend. Install Ollama or configure an OpenAI/Claude API key.
                </Alert>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={svc.dockerImage ? 6 : 12}>
            <ActionCard
              title={"Install " + svc.title + " \u2014 OS (" + installOsLabel + ")"}
              description={"Install " + svc.title + " as a managed service."}
              action={cfg.os === "windows" ? "/run/" + scope + "_windows_os" : "/run/" + scope + "_unix_os"}
              fields={commonFields}
              onRun={run}
              color={svc.color}
            />
          </Grid>

          {svc.dockerImage && (
            <Grid item xs={12} md={6}>
              <ActionCard
                title={"Install " + svc.title + " \u2014 Docker"}
                description={"Deploy " + svc.title + " in Docker. Image: " + svc.dockerImage}
                action={"/run/" + scope + "_docker"}
                fields={commonFields}
                onRun={run}
                color="#0891b2"
              />
            </Grid>
          )}

          <Grid item xs={12} md={4}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: svc.color }}>Status</Typography>
                <Typography variant="body2" color="text.secondary">Install {svc.title} using the cards above to see status here.</Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={8}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Download & Install</Typography>
                {svc.links && svc.links.length > 0 && (
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                    {svc.links.map(function(lnk) {
                      return (
                        <Button key={lnk.url} variant="outlined" size="small" href={lnk.url} target="_blank" rel="noopener"
                          sx={{ textTransform: "none", borderRadius: 2, fontWeight: 600, borderColor: svc.color + "44", color: svc.color }}>
                          {lnk.label}
                        </Button>
                      );
                    })}
                  </Stack>
                )}
                {svc.installCmds && Object.keys(svc.installCmds).map(function(key) {
                  return (
                    <Box key={key} sx={{ mb: 1.5 }}>
                      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.3 }}>
                        <Typography variant="caption" fontWeight={700} sx={{ color: "#475569" }}>Install via {key}:</Typography>
                        <Tooltip title="Copy command">
                          <Button size="small" variant="text" sx={{ textTransform: "none", minWidth: 0, px: 1, fontSize: 10 }}
                            onClick={function() { if (copyText) copyText(svc.installCmds[key], "install command"); }}>
                            Copy
                          </Button>
                        </Tooltip>
                      </Stack>
                      <Paper elevation={0} sx={{ p: 1, bgcolor: "#0d1117", borderRadius: 1.5, fontFamily: "monospace", fontSize: 12, color: "#c9d1d9", wordBreak: "break-all", whiteSpace: "pre-wrap", border: "1px solid #30363d" }}>
                        {svc.installCmds[key]}
                      </Paper>
                    </Box>
                  );
                })}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      );
    };
  });
})();
