// Professional File Manager — Cloud view + Tree view + Multi-tab editor + Context menu
(() => {
  const {
    Alert, Box, Button, Chip, CircularProgress,
    Divider, IconButton, LinearProgress, Paper,
    TextField, Tooltip, Typography, InputAdornment,
  } = MaterialUI;

  // ─── Inline SVG icon system ────────────────────────────────────────────────
  function mkI(d, d2) {
    return function SvgIcon({ sx = {}, onClick }) {
      const sz = typeof sx.fontSize === "number" ? sx.fontSize : 20;
      return (
        <svg viewBox="0 0 24 24" width={sz} height={sz}
          style={{
            display: "inline-block", flexShrink: sx.flexShrink !== undefined ? sx.flexShrink : 0,
            verticalAlign: "middle", fill: sx.color || "currentColor",
            marginRight: sx.mr ? sx.mr * 8 : undefined,
            marginLeft: sx.ml ? sx.ml * 8 : undefined,
            opacity: sx.opacity, cursor: onClick ? "pointer" : sx.cursor,
          }}
          onClick={onClick}>
          <path d={d} />{d2 && <path d={d2} />}
        </svg>
      );
    };
  }

  const FolderIcon       = mkI("M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z");
  const FolderOpenIcon   = mkI("M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z");
  const FileIcon         = mkI("M6 2c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6H6zm7 7V3.5L18.5 9H13z");
  const ImageFileIcon    = mkI("M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z");
  const VideoFileIcon    = mkI("M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4h-4zm-4 11l-5-3 5-3v6z");
  const AudioFileIcon    = mkI("M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6zm-2 16c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z");
  const PdfFileIcon      = mkI("M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-8.5 7.5c0 .83-.67 1.5-1.5 1.5H9v2H7.5V7H10c.83 0 1.5.67 1.5 1.5v1zm5 2c0 .83-.67 1.5-1.5 1.5h-2.5V7H15c.83 0 1.5.67 1.5 1.5v3zm4-3H19v1h1.5V11H19v2h-1.5V7h3v1.5zM9 9.5h1v-1H9v1zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm10 5.5h1v-3h-1v3z");
  const ZipFileIcon      = mkI("M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-4 6h-2v2h2v2h-2v2h-2v-2h2v-2h-2v-2h2v-2h-2V8h2v2h2v2z");
  const CodeFileIcon     = mkI("M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z");
  const DataFileIcon     = mkI("M3 3h18v2H3V3zm0 4h18v2H3V7zm0 4h18v2H3v-2zm0 4h18v2H3v-2zm0 4h18v2H3v-2z");
  const DocFileIcon      = mkI("M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z");
  const ShellFileIcon    = mkI("M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H4V8h16v10zm-2-1H6v-2h12v2zM8.83 12l-1.42 1.41L10.83 16l-3.41 3.41L8.83 21 14 16l-5.17-4zm6.34 1H10v2h5.17l-1.42 1.41L15.17 18 18 15.17 15.17 13z");
  const ConfigFileIcon   = mkI("M19.43 12.98c.04-.32.07-.64.07-.98 0-.34-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1c-.23-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98 0 .33.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.58 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.65zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z");
  const ChevronRightIcon = mkI("M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z");
  const ExpandMoreIcon   = mkI("M16.59 8.59L12 13.17 7.41 8.59 6 10l6 6 6-6z");
  const GridViewIcon     = mkI("M3 3v8h8V3H3zm6 6H5V5h4v4zm-6 4v8h8v-8H3zm6 6H5v-4h4v4zm4-16v8h8V3h-8zm6 6h-4V5h4v4zm-6 4v8h8v-8h-8zm6 6h-4v-4h4v4z");
  const TreeViewIcon     = mkI("M22 11V3h-7v3H9V3H2v8h7V8h2v10h4v3h7v-8h-7v3h-2V8h2v3z");
  const RefreshIcon      = mkI("M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z");
  const HomeIcon         = mkI("M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z");
  const DeleteIcon       = mkI("M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z");
  const RenameIcon       = mkI("M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1.003 1.003 0 0 0 0-1.41l-2.34-2.34a1.003 1.003 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z");
  const DownloadIcon     = mkI("M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z");
  const NewFolderIcon    = mkI("M20 6h-8l-2-2H4c-1.11 0-1.99.89-1.99 2L2 18c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-1 8h-3v3h-2v-3h-3v-2h3V9h2v3h3v2z");
  const NewFileIcon      = mkI("M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 14h-3v3h-2v-3H8v-2h3v-3h2v3h3v2zm-3-7V3.5L18.5 9H13z");
  const UploadIcon       = mkI("M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z");
  const BackIcon         = mkI("M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z");
  const StorageIcon      = mkI("M2 20h20v-4H2v4zm2-3h2v2H4v-2zM2 4v4h20V4H2zm4 3H4V5h4v2H6zm-4 7h20v-4H2v4zm2-3h2v2H4v-2z");
  const EditCodeIcon     = mkI("M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z");
  const MinimizeIcon     = mkI("M6 19h12v2H6z");
  const RestoreIcon      = mkI("M18 4H6c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H6V6h12v12z");
  const CloseIcon        = mkI("M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z");
  const CopyIcon         = mkI("M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z");
  const CutIcon          = mkI("M9.64 7.64c.23-.5.36-1.05.36-1.64 0-2.21-1.79-4-4-4S2 3.79 2 6s1.79 4 4 4c.59 0 1.14-.13 1.64-.36L10 12l-2.36 2.36C7.14 14.13 6.59 14 6 14c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4c0-.59-.13-1.14-.36-1.64L12 14l7 7h3v-1L9.64 7.64zM6 8c-1.1 0-2-.89-2-2s.9-2 2-2 2 .89 2 2-.9 2-2 2zm0 12c-1.1 0-2-.89-2-2s.9-2 2-2 2 .89 2 2-.9 2-2 2zm6-7.5c-.28 0-.5-.22-.5-.5s.22-.5.5-.5.5.22.5.5-.22.5-.5.5zM19 3l-6 6 2 2 7-7V3z");
  const PasteIcon        = mkI("M19 2h-4.18C14.4.84 13.3 0 12 0c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm7 18H5V4h2v3h10V4h2v16z");
  const OpenFolderIcon   = mkI("M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z");
  const OpenFileIcon     = mkI("M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm-1 2 5 5h-5V4zM6 20V4h6v6h6v10H6z");
  const TerminalIcon = mkI("M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H4V6h16v12zM6.41 15.59L5 17l5-5-5-5 1.41-1.41L9.17 9H19v2H9.17l-2.76 2.59z");

  function getFileTypeIcon(name) {
    const ext = (name || "").split(".").pop().toLowerCase();
    if (["png","jpg","jpeg","gif","svg","webp","bmp","ico","tiff"].includes(ext)) return ImageFileIcon;
    if (["mp4","mkv","avi","mov","wmv","webm","flv"].includes(ext)) return VideoFileIcon;
    if (["mp3","wav","ogg","flac","aac","m4a"].includes(ext)) return AudioFileIcon;
    if (ext === "pdf") return PdfFileIcon;
    if (["zip","tar","gz","bz2","rar","7z","xz"].includes(ext)) return ZipFileIcon;
    if (["js","ts","jsx","tsx","py","cs","go","rs","cpp","c","java","php","rb","swift","kt","dart"].includes(ext)) return CodeFileIcon;
    if (["csv","xlsx","xls","ods","parquet"].includes(ext)) return DataFileIcon;
    if (["doc","docx","odt","rtf","md","txt","log"].includes(ext)) return DocFileIcon;
    if (["sh","bash","zsh","ps1","bat","cmd"].includes(ext)) return ShellFileIcon;
    if (["json","yaml","yml","toml","xml","env","ini","cfg","conf"].includes(ext)) return ConfigFileIcon;
    return FileIcon;
  }

  // ─── Utilities ─────────────────────────────────────────────────────────────
  function fmtBytes(b) {
    if (!b) return "0 B";
    const k = 1024, u = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.min(Math.floor(Math.log(b) / Math.log(k)), u.length - 1);
    return `${+(b / k ** i).toFixed(1)} ${u[i]}`;
  }
  function fmtDate(ts) {
    if (!ts) return "";
    return new Date(ts * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }
  function fileExtColor(name) {
    const ext = (name || "").split(".").pop().toLowerCase();
    const m = {
      js:"#f7df1e",ts:"#3178c6",jsx:"#61dafb",tsx:"#61dafb",
      json:"#f59e0b",py:"#3b82f6",html:"#e44d26",css:"#1572b6",
      md:"#083fa1",txt:"#64748b",xml:"#f97316",sh:"#22c55e",
      ps1:"#5b21b6",bat:"#374151",sql:"#0ea5e9",cs:"#7c3aed",
      java:"#ef4444",go:"#00acd7",rs:"#b7470a",cpp:"#0066b8",
      c:"#a8b9cc",php:"#8892be",rb:"#cc342d",yaml:"#e11d48",
      yml:"#e11d48",toml:"#9ca3af",log:"#94a3b8",zip:"#6366f1",
      tar:"#6366f1",gz:"#6366f1",png:"#10b981",jpg:"#10b981",
      jpeg:"#10b981",svg:"#f97316",gif:"#ec4899",pdf:"#ef4444",
      csv:"#22c55e",xlsx:"#16a34a",docx:"#2563eb",env:"#fbbf24",
    };
    return m[ext] || "#64748b";
  }
  function buildBreadcrumbs(path, os) {
    const label0 = os === "windows" ? "Computer" : "Root";
    const crumbs = [{ label: label0, path: "" }];
    if (!path) return crumbs;
    if (os === "windows") {
      const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
      let cur = "";
      for (const p of parts) {
        cur = cur ? `${cur.replace(/[\\/]+$/, "")}\\${p}` : (p.endsWith(":") ? `${p}\\` : p);
        crumbs.push({ label: p.replace(/[\\/]+$/, "") || p, path: cur });
      }
    } else {
      const parts = path.split("/").filter(Boolean);
      let cur = "";
      for (const p of parts) { cur += `/${p}`; crumbs.push({ label: p, path: cur }); }
    }
    return crumbs;
  }

  // ─── Icon renderer ──────────────────────────────────────────────────────────
  function Icon({ icon, sx, onClick }) {
    if (!icon) return null;
    return React.createElement(icon, { sx, onClick });
  }

  // ─── Terminal tab view ──────────────────────────────────────────────────────
  function TerminalView({ cwd, isActive, initialInput }) {
    const containerRef = React.useRef(null);
    const termRef      = React.useRef(null);
    const wsRef        = React.useRef(null);
    const fitRef       = React.useRef(null);
    const initialSentRef = React.useRef(false);

    React.useEffect(() => {
      const el = containerRef.current;
      if (!el) return;
      const T = window.Terminal;
      if (!T) {
        el.style.cssText = "display:flex;align-items:center;justify-content:center;background:#fff;color:#333;font-family:monospace;font-size:13px;padding:24px;";
        el.textContent = "Terminal unavailable: xterm.js could not be loaded. Check server internet access or CDN connectivity.";
        return;
      }
      const term = new T({
        cursorBlink: true,
        fontFamily: "'SF Mono', Monaco, Menlo, Consolas, 'Courier New', monospace",
        fontSize: 13,
        theme: {
          background: "#ffffff", foreground: "#1d1d1d", cursor: "#333333",
          selectionBackground: "#b3d5ff",
          black: "#000000", red: "#c41a16", green: "#007400", yellow: "#836c28",
          blue: "#0000ff", magenta: "#a90d91", cyan: "#318495", white: "#898989",
          brightBlack: "#5c5c5c", brightRed: "#c41a16", brightGreen: "#007400",
          brightYellow: "#836c28", brightBlue: "#0000ff", brightMagenta: "#a90d91",
          brightCyan: "#318495", brightWhite: "#ffffff",
        },
      });
      const FA = window.FitAddon;
      let fitAddon = null;
      if (FA && FA.FitAddon) { fitAddon = new FA.FitAddon(); term.loadAddon(fitAddon); }
      term.open(el);
      if (fitAddon) { try { fitAddon.fit(); } catch (_) {} }
      termRef.current = term;
      fitRef.current  = fitAddon;

      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const cols  = term.cols || 80;
      const rows  = term.rows || 24;
      const ws = new WebSocket(`${proto}//${location.host}/ws/pty?cwd=${encodeURIComponent(cwd || "")}&cols=${cols}&rows=${rows}`);
      ws.binaryType = "arraybuffer";
      wsRef.current  = ws;

      ws.onopen    = () => {
        if (fitAddon) try { fitAddon.fit(); } catch (_) {}
        if (!initialSentRef.current && initialInput) {
          initialSentRef.current = true;
          setTimeout(() => {
            if (ws.readyState === WebSocket.OPEN) ws.send(initialInput);
          }, 80);
        }
      };
      ws.onmessage = (e) => {
        if (e.data instanceof ArrayBuffer) term.write(new Uint8Array(e.data));
        else term.write(e.data);
      };
      ws.onclose = () => term.write("\r\n\x1b[33m[Terminal disconnected]\x1b[0m\r\n");
      ws.onerror = () => term.write("\r\n\x1b[31m[Connection failed]\x1b[0m\r\n");

      term.onData((data) => { if (ws.readyState === WebSocket.OPEN) ws.send(data); });

      const sendResize = () => {
        if (fitAddon) try { fitAddon.fit(); } catch (_) {}
        if (ws.readyState === WebSocket.OPEN)
          ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      };
      const observer = new ResizeObserver(sendResize);
      observer.observe(el);

      return () => {
        observer.disconnect();
        ws.close();
        term.dispose();
        termRef.current = wsRef.current = fitRef.current = null;
      };
    }, []);

    React.useEffect(() => {
      if (!isActive) return;
      const id = setTimeout(() => {
        const fa = fitRef.current;
        const ws = wsRef.current;
        const t  = termRef.current;
        if (fa) try { fa.fit(); } catch (_) {}
        if (ws && ws.readyState === WebSocket.OPEN && t)
          ws.send(JSON.stringify({ type: "resize", cols: t.cols, rows: t.rows }));
      }, 60);
      return () => clearTimeout(id);
    }, [isActive]);

    return (
      <Box ref={containerRef} sx={{
        width:"100%", height:"100%", flexGrow:1, bgcolor:"#ffffff", overflow:"hidden",
        "& .xterm": { height:"100%", padding:"4px" },
        "& .xterm-viewport": { overflowY:"auto !important" },
      }} />
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CONTEXT MENU
  // ═══════════════════════════════════════════════════════════════════════════
  function ContextMenu({ x, y, items, onClose }) {
    React.useEffect(() => {
      const close = () => onClose();
      // close on next tick so the triggering click doesn't immediately dismiss
      const tid = setTimeout(() => {
        document.addEventListener("mousedown", close);
        document.addEventListener("contextmenu", close);
      }, 0);
      return () => {
        clearTimeout(tid);
        document.removeEventListener("mousedown", close);
        document.removeEventListener("contextmenu", close);
      };
    }, [onClose]);

    // Clamp to viewport
    const [pos, setPos] = React.useState({ left: x, top: y });
    const ref = React.useRef(null);
    React.useEffect(() => {
      if (!ref.current) return;
      const r = ref.current.getBoundingClientRect();
      const vw = window.innerWidth, vh = window.innerHeight;
      setPos({
        left: r.right > vw ? Math.max(0, x - r.width) : x,
        top:  r.bottom > vh ? Math.max(0, y - r.height) : y,
      });
    }, [x, y]);

    return ReactDOM.createPortal(
      <Paper ref={ref} onMouseDown={(e) => e.stopPropagation()}
        sx={{
          position: "fixed", left: pos.left, top: pos.top, zIndex: 9999,
          minWidth: 192, py: 0.5,
          boxShadow: "0 8px 28px rgba(0,0,0,.22)",
          borderRadius: 1.5, border: "1px solid #e2e8f0",
        }}>
        {items.map((item, i) =>
          item === "---" ? <Divider key={i} sx={{ my: 0.5 }} /> : (
            <Box key={i}
              sx={{
                px: 1.75, py: 0.7, cursor: item.disabled ? "default" : "pointer",
                opacity: item.disabled ? 0.38 : 1,
                display: "flex", alignItems: "center", gap: 1.25,
                "&:hover": { bgcolor: item.disabled ? undefined : "rgba(29,78,216,.07)" },
                fontSize: 13, color: item.danger ? "#ef4444" : "#0f172a",
                userSelect: "none",
              }}
              onClick={item.disabled ? undefined : () => { item.action(); onClose(); }}>
              {item.icon && <Icon icon={item.icon} sx={{ fontSize: 15, color: item.danger ? "#ef4444" : "#64748b" }} />}
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.shortcut && <Typography variant="caption" sx={{ color: "#94a3b8", fontSize: 11 }}>{item.shortcut}</Typography>}
            </Box>
          )
        )}
      </Paper>,
      document.body
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TREE NODE ROW
  // ═══════════════════════════════════════════════════════════════════════════
  function TreeNodeRow({ entry, depth, isExpanded, isLoadingChildren, isSelected, isDragOver,
    onToggle, onSelect, onDragStart, onDragEnter, onDragLeave, onDrop, onContextMenu }) {
    const pl = 6 + depth * 16;
    const isDir = entry.is_dir;
    return (
      <Box
        sx={{
          display: "flex", alignItems: "center", pl: `${pl}px`, pr: 0.5, py: "3px",
          cursor: "pointer", borderRadius: 1, userSelect: "none",
          bgcolor: isSelected ? "rgba(29,78,216,.13)" : isDragOver ? "rgba(34,197,94,.1)" : "transparent",
          outline: isDragOver ? "1.5px dashed #16a34a" : "none",
          "&:hover": { bgcolor: isSelected ? "rgba(29,78,216,.16)" : "rgba(0,0,0,.04)" },
          transition: "background-color .1s",
        }}
        onClick={() => onSelect(entry)}
        onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); onContextMenu(e, entry); }}
        draggable
        onDragStart={(e) => onDragStart(e, entry)}
        onDragEnter={isDir ? (e) => onDragEnter(e, entry.path) : undefined}
        onDragOver={isDir ? (e) => e.preventDefault() : undefined}
        onDragLeave={isDir ? (e) => onDragLeave(e, entry.path) : undefined}
        onDrop={isDir ? (e) => onDrop(e, entry.path) : undefined}
      >
        <Box sx={{ width: 18, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          {isDir && isLoadingChildren && <CircularProgress size={11} />}
          {isDir && !isLoadingChildren && (
            <Icon
              icon={isExpanded ? ExpandMoreIcon : ChevronRightIcon}
              sx={{ fontSize: 16, color: "#64748b", cursor: "pointer" }}
              onClick={(e) => { e.stopPropagation(); onToggle(entry.path); }}
            />
          )}
        </Box>
        {isDir ? (
          <Icon icon={isExpanded ? FolderOpenIcon : FolderIcon}
            sx={{ fontSize: 16, color: "#f59e0b", mr: 0.6, flexShrink: 0 }} />
        ) : (
          <Icon icon={getFileTypeIcon(entry.name)}
            sx={{ fontSize: 15, color: fileExtColor(entry.name), mr: 0.6, flexShrink: 0 }} />
        )}
        <Typography noWrap variant="body2"
          sx={{ fontSize: 12.5, fontWeight: isSelected ? 700 : 400,
            color: isSelected ? "#1d4ed8" : "#0f172a", flexGrow: 1, minWidth: 0 }}>
          {entry.name}
        </Typography>
      </Box>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RECURSIVE TREE
  // ═══════════════════════════════════════════════════════════════════════════
  function FileTree({ items, depth, treeExpanded, treeChildren, treeLoading, selected, dragOverPath,
    onToggle, onSelect, onDragStart, onDragEnter, onDragLeave, onDrop, onContextMenu }) {
    if (!items || items.length === 0) return null;
    return (
      <Box>
        {items.map((entry) => {
          const expanded = treeExpanded.has(entry.path);
          const loading  = treeLoading.has(entry.path);
          const children = treeChildren[entry.path] || [];
          return (
            <Box key={entry.path}>
              <TreeNodeRow
                entry={entry} depth={depth}
                isExpanded={expanded} isLoadingChildren={loading}
                isSelected={selected === entry.path} isDragOver={dragOverPath === entry.path}
                onToggle={onToggle} onSelect={onSelect}
                onDragStart={onDragStart} onDragEnter={onDragEnter}
                onDragLeave={onDragLeave} onDrop={onDrop}
                onContextMenu={onContextMenu}
              />
              {expanded && entry.is_dir && (
                <FileTree
                  items={children} depth={depth + 1}
                  treeExpanded={treeExpanded} treeChildren={treeChildren}
                  treeLoading={treeLoading} selected={selected} dragOverPath={dragOverPath}
                  onToggle={onToggle} onSelect={onSelect}
                  onDragStart={onDragStart} onDragEnter={onDragEnter}
                  onDragLeave={onDragLeave} onDrop={onDrop}
                  onContextMenu={onContextMenu}
                />
              )}
            </Box>
          );
        })}
      </Box>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CLOUD ENTRY
  // ═══════════════════════════════════════════════════════════════════════════
  function CloudEntry({ entry, isSelected, isDragOver, onClick, onDoubleClick,
    onDragStart, onDragEnter, onDragLeave, onDrop,
    onRename, onDelete, onDownload, onOpenTab, fileOpBusy, onContextMenu }) {
    const isDir = entry.is_dir;
    const ext = (entry.name || "").split(".").pop().slice(0, 4).toUpperCase();
    return (
      <Box
        sx={{
          position: "relative", display: "flex", flexDirection: "column", alignItems: "center",
          width: 96, p: 1, borderRadius: 2, cursor: "pointer", userSelect: "none",
          bgcolor: isSelected ? "rgba(29,78,216,.1)" : isDragOver ? "rgba(34,197,94,.08)" : "transparent",
          outline: isDragOver ? "2px dashed #16a34a" : isSelected ? "2px solid rgba(29,78,216,.4)" : "2px solid transparent",
          "&:hover": { bgcolor: isSelected ? "rgba(29,78,216,.13)" : "rgba(0,0,0,.05)" },
          transition: "background-color .12s, outline-color .12s",
        }}
        onClick={(e) => { e.stopPropagation(); onClick(entry); }}
        onDoubleClick={() => onDoubleClick(entry)}
        onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); onContextMenu(e, entry); }}
        draggable
        onDragStart={(e) => onDragStart(e, entry)}
        onDragEnter={isDir ? (e) => onDragEnter(e, entry.path) : undefined}
        onDragOver={isDir ? (e) => e.preventDefault() : undefined}
        onDragLeave={isDir ? (e) => onDragLeave(e, entry.path) : undefined}
        onDrop={isDir ? (e) => onDrop(e, entry.path) : undefined}
      >
        {isDir ? (
          <Icon icon={isDragOver ? FolderOpenIcon : FolderIcon} sx={{ fontSize: 52, color: isDragOver ? "#16a34a" : "#f59e0b" }} />
        ) : (
          <Box sx={{
            width: 48, height: 56, bgcolor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 1.5,
            display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "2px",
          }}>
            <Icon icon={getFileTypeIcon(entry.name)} sx={{ fontSize: 26, color: fileExtColor(entry.name) }} />
            <Typography sx={{ fontSize: 8.5, fontWeight: 800, color: fileExtColor(entry.name), textTransform: "uppercase", letterSpacing: .3, lineHeight: 1 }}>
              {ext || "FILE"}
            </Typography>
          </Box>
        )}
        <Typography variant="caption" align="center"
          sx={{ mt: 0.5, fontSize: 11.5, lineHeight: 1.3, maxWidth: 88, wordBreak: "break-all",
            display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
            fontWeight: isSelected ? 700 : 400 }}>
          {entry.name}
        </Typography>
      </Box>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // MAIN FILE MANAGER PAGE
  // ═══════════════════════════════════════════════════════════════════════════
  function FileManagerPage({
    cfg,
    fileManagerPath, setFileManagerPath,
    fileManagerData, fileManagerLoading, fileManagerError,
    fileManagerTerminalRequest, setFileManagerTerminalRequest,
    fileEditorPath, fileEditorContent, fileEditorMeta, fileEditorDirty,
    fileOpBusy,
    loadFileManager, openFileInEditor, saveFileEditor,
    setFileEditorContent, setFileEditorDirty,
    createFolderInCurrentPath, createFileInCurrentPath,
    renameFileManagerPath, deleteFileManagerPath,
    uploadIntoCurrentPath,
  }) {
    const os  = (cfg && cfg.os) || "windows";
    const sep = os === "windows" ? "\\" : "/";

    // ── View state ─────────────────────────────────────────────────────────
    const [viewMode, setViewMode]           = React.useState("cloud");
    const [cloudSelected, setCloudSelected] = React.useState(null);

    // ── Multi-tab editor state ──────────────────────────────────────────────
    // tabs: [ { path, content, originalContent, dirty, meta, loading } ]
    const [editorTabs, setEditorTabs]       = React.useState([]);
    const [activeTabPath, setActiveTabPath] = React.useState(null);
    const [minimizedTabs, setMinimizedTabs] = React.useState([]); // ordered list of paths

    // ── Resize state ────────────────────────────────────────────────────────
    const [editorWidth, setEditorWidth]     = React.useState(460);
    const resizeDragging                    = React.useRef(false);
    const resizeStartX                      = React.useRef(0);
    const resizeStartW                      = React.useRef(0);

    // ── Context menu state ──────────────────────────────────────────────────
    const [ctxMenu, setCtxMenu]             = React.useState(null); // { x, y, entry|null }
    const [clipboard, setClipboard]         = React.useState(null); // { op:"copy"|"cut", path, name }

    // ── Properties dialog state ─────────────────────────────────────────────
    const [propsDlg, setPropsDlg]           = React.useState(null); // entry object
    const [propsData, setPropsData]         = React.useState(null); // fetched info
    const [propsLoading, setPropsLoading]   = React.useState(false);

    // ── Op error ────────────────────────────────────────────────────────────
    const [opError, setOpError]             = React.useState("");

    // ── Tree state ─────────────────────────────────────────────────────────
    const [treeRoots, setTreeRoots]       = React.useState([]);
    const [treeRootsLoaded, setTRL]       = React.useState(false);
    const [treeExpanded, setTreeExpanded] = React.useState(() => new Set());
    const [treeChildren, setTreeChildren] = React.useState({});
    const [treeLoading, setTreeLoading]   = React.useState(() => new Set());
    const [treeSelected, setTreeSelected] = React.useState(null);

    // ── Drag state ─────────────────────────────────────────────────────────
    const [dragSrc, setDragSrc]       = React.useState(null);
    const [dragOver, setDragOver]     = React.useState(null);
    const dragEnterCounters           = React.useRef({});
    const [panelDragActive, setPDA]   = React.useState(false);
    const panelDragCount              = React.useRef(0);
    const [moveBusy, setMoveBusy]     = React.useState(false);
    const [moveError, setMoveError]   = React.useState("");
    const [termCounter, setTermCounter] = React.useState(0);

    // Derived
    const [pathInput, setPathInput]   = React.useState(fileManagerPath || "");
    React.useEffect(() => { setPathInput(fileManagerPath || ""); }, [fileManagerPath]);

    const entries       = React.useMemo(() => Array.isArray(fileManagerData?.entries) ? fileManagerData.entries : [], [fileManagerData]);
    const breadcrumbs   = React.useMemo(() => buildBreadcrumbs(fileManagerPath, os), [fileManagerPath, os]);
    const folderEntries = React.useMemo(() => entries.filter((e) => e.is_dir), [entries]);
    const fileEntries   = React.useMemo(() => entries.filter((e) => !e.is_dir), [entries]);

    // The active non-minimized tab for the editor area
    const activeTab = editorTabs.find((t) => t.path === activeTabPath) || null;

    // ── Resize handlers ────────────────────────────────────────────────────
    const startResize = React.useCallback((e) => {
      resizeDragging.current = true;
      resizeStartX.current = e.clientX;
      resizeStartW.current = editorWidth;
      e.preventDefault();
    }, [editorWidth]);

    React.useEffect(() => {
      const onMove = (e) => {
        if (!resizeDragging.current) return;
        const delta = resizeStartX.current - e.clientX; // drag left = wider
        setEditorWidth(Math.max(280, Math.min(900, resizeStartW.current + delta)));
      };
      const onUp = () => { resizeDragging.current = false; };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    }, []);

    // ── Tab helpers ────────────────────────────────────────────────────────
    const openTerminalTab = React.useCallback((options) => {
      const opts = options && typeof options === "object" ? options : {};
      const id = Date.now();
      const termPath = `__term__:${id}`;
      const termCwd = String(opts.cwd || fileManagerPath || "").trim();
      const termTitle = String(opts.title || "").trim();
      const termInitialInput = String(opts.initialInput || "").replace(/\r\n/g, "\n");
      setTermCounter((c) => {
        const n = c + 1;
        setEditorTabs((prev) => [...prev, {
          path: termPath,
          kind: "terminal",
          cwd: termCwd,
          title: termTitle || `Terminal ${n}`,
          initialInput: termInitialInput,
        }]);
        return n;
      });
      setActiveTabPath(termPath);
      setMinimizedTabs((prev) => prev.filter((p) => p !== termPath));
    }, [fileManagerPath]);

    React.useEffect(() => {
      if (!fileManagerTerminalRequest || !fileManagerTerminalRequest.id) return;
      openTerminalTab(fileManagerTerminalRequest);
      if (typeof setFileManagerTerminalRequest === "function") {
        setFileManagerTerminalRequest(null);
      }
    }, [fileManagerTerminalRequest, openTerminalTab, setFileManagerTerminalRequest]);

    const openEditorTab = React.useCallback(async (path) => {
      // If already open, just activate
      const existing = editorTabs.find((t) => t.path === path);
      if (existing) {
        setActiveTabPath(path);
        // if minimized, restore it
        setMinimizedTabs((prev) => prev.filter((p) => p !== path));
        return;
      }
      // Add loading tab
      setEditorTabs((prev) => [...prev, { path, content: "", originalContent: "", dirty: false, meta: {}, loading: true }]);
      setActiveTabPath(path);
      setMinimizedTabs((prev) => prev.filter((p) => p !== path));
      try {
        const fd = new FormData(); fd.append("path", path);
        const r = await fetch("/api/files/read", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
        const j = await r.json();
        if (!j.ok) throw new Error(j.error || "Failed to read file");
        const content = j.content || "";
        setEditorTabs((prev) => prev.map((t) => t.path === path ? { ...t, content, originalContent: content, dirty: false, meta: { encoding: j.encoding, size: j.size }, loading: false } : t));
      } catch (err) {
        setEditorTabs((prev) => prev.map((t) => t.path === path ? { ...t, content: `// Error: ${err.message}`, originalContent: "", loading: false } : t));
      }
    }, [editorTabs]);

    const saveTab = React.useCallback(async (path) => {
      const tab = editorTabs.find((t) => t.path === path);
      if (!tab) return;
      setEditorTabs((prev) => prev.map((t) => t.path === path ? { ...t, loading: true } : t));
      try {
        const fd = new FormData(); fd.append("path", path); fd.append("content", tab.content);
        const r = await fetch("/api/files/write", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
        const j = await r.json();
        if (!j.ok) throw new Error(j.error || "Save failed");
        setEditorTabs((prev) => prev.map((t) => t.path === path ? { ...t, dirty: false, originalContent: tab.content, loading: false } : t));
      } catch (err) {
        setOpError(`Save failed: ${err.message}`);
        setEditorTabs((prev) => prev.map((t) => t.path === path ? { ...t, loading: false } : t));
      }
    }, [editorTabs]);

    const discardTab = React.useCallback((path) => {
      setEditorTabs((prev) => prev.map((t) => t.path === path ? { ...t, content: t.originalContent, dirty: false } : t));
    }, []);

    const closeTab = React.useCallback((path) => {
      setEditorTabs((prev) => {
        const next = prev.filter((t) => t.path !== path);
        if (activeTabPath === path) {
          // Activate next visible tab
          const remaining = next.filter((t) => !minimizedTabs.includes(t.path));
          setActiveTabPath(remaining.length ? remaining[remaining.length - 1].path : (next.length ? next[next.length - 1].path : null));
        }
        return next;
      });
      setMinimizedTabs((prev) => prev.filter((p) => p !== path));
    }, [activeTabPath, minimizedTabs]);

    const minimizeTab = React.useCallback((path) => {
      setMinimizedTabs((prev) => prev.includes(path) ? prev : [...prev, path]);
      if (activeTabPath === path) {
        const nonMin = editorTabs.filter((t) => t.path !== path && !minimizedTabs.includes(t.path));
        setActiveTabPath(nonMin.length ? nonMin[nonMin.length - 1].path : null);
      }
    }, [activeTabPath, editorTabs, minimizedTabs]);

    const restoreTab = React.useCallback((path) => {
      setMinimizedTabs((prev) => prev.filter((p) => p !== path));
      setActiveTabPath(path);
    }, []);

    // ── Tree load ──────────────────────────────────────────────────────────
    React.useEffect(() => {
      if (viewMode !== "tree" || treeRootsLoaded) return;
      (async () => {
        try {
          const r = await fetch("/api/files/list", { headers: { "X-Requested-With": "fetch" } });
          const j = await r.json();
          if (j.ok) { setTreeRoots(j.entries || []); setTRL(true); }
        } catch (_) {}
      })();
    }, [viewMode, treeRootsLoaded]);

    const handleTreeToggle = React.useCallback(async (path) => {
      const next = new Set(treeExpanded);
      if (next.has(path)) { next.delete(path); setTreeExpanded(next); return; }
      next.add(path); setTreeExpanded(next);
      if (treeChildren[path]) return;
      setTreeLoading((prev) => { const s = new Set(prev); s.add(path); return s; });
      try {
        const r = await fetch(`/api/files/list?path=${encodeURIComponent(path)}`, { headers: { "X-Requested-With": "fetch" } });
        const j = await r.json();
        if (j.ok) setTreeChildren((p) => ({ ...p, [path]: j.entries || [] }));
      } catch (_) {}
      setTreeLoading((prev) => { const s = new Set(prev); s.delete(path); return s; });
    }, [treeExpanded, treeChildren]);

    const refreshTreeDir = React.useCallback(async (path) => {
      if (!path) return;
      try {
        const r = await fetch(`/api/files/list?path=${encodeURIComponent(path)}`, { headers: { "X-Requested-With": "fetch" } });
        const j = await r.json();
        if (j.ok) setTreeChildren((p) => ({ ...p, [path]: j.entries || [] }));
      } catch (_) {}
    }, []);

    const handleTreeSelect = React.useCallback((entry) => {
      setTreeSelected(entry.path);
      if (entry.is_dir) { loadFileManager(entry.path); handleTreeToggle(entry.path); }
      else { openEditorTab(entry.path); }
    }, [loadFileManager, openEditorTab, handleTreeToggle]);

    // ── Drag helpers ───────────────────────────────────────────────────────
    const handleDragStart = React.useCallback((e, entry) => {
      e.dataTransfer.setData("text/plain", entry.path);
      e.dataTransfer.effectAllowed = "move";
      setDragSrc(entry.path);
    }, []);
    const handleDragEnter = React.useCallback((e, path) => {
      e.preventDefault();
      dragEnterCounters.current[path] = (dragEnterCounters.current[path] || 0) + 1;
      setDragOver(path);
    }, []);
    const handleDragLeave = React.useCallback((e, path) => {
      dragEnterCounters.current[path] = Math.max(0, (dragEnterCounters.current[path] || 1) - 1);
      if (dragEnterCounters.current[path] === 0) setDragOver((prev) => (prev === path ? null : prev));
    }, []);
    const handleDrop = React.useCallback(async (e, targetPath) => {
      e.preventDefault(); e.stopPropagation();
      dragEnterCounters.current[targetPath] = 0; setDragOver(null);
      const sourcePath = dragSrc || e.dataTransfer.getData("text/plain");
      const isExternalUpload = !sourcePath || e.dataTransfer.files.length > 0;
      if (isExternalUpload && e.dataTransfer.files.length > 0) {
        if (!targetPath) return;
        const files = Array.from(e.dataTransfer.files);
        setMoveBusy(true);
        try {
          const fd = new FormData();
          fd.append("target", targetPath);
          files.forEach((f) => fd.append("files", f, f.name));
          const r = await fetch("/api/files/upload", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
          const j = await r.json();
          if (!j.ok) throw new Error(j.error || "Upload failed");
          loadFileManager(fileManagerPath);
          await refreshTreeDir(targetPath);
        } catch (err) { setMoveError(`Upload failed: ${err}`); }
        finally { setMoveBusy(false); setDragSrc(null); }
        return;
      }
      if (!sourcePath || sourcePath === targetPath) { setDragSrc(null); return; }
      if (targetPath.startsWith(sourcePath + sep) || targetPath === sourcePath) {
        setMoveError("Cannot move a folder into itself."); setDragSrc(null); return;
      }
      const srcName = sourcePath.split(/[\\/]/).pop();
      const newPath = `${targetPath.replace(/[\\/]+$/, "")}${sep}${srcName}`;
      const srcParent = sourcePath.replace(/[\\/][^\\/]+$/, "") || "";
      setMoveBusy(true); setMoveError("");
      try {
        const fd = new FormData();
        fd.append("source", sourcePath); fd.append("target", newPath);
        const r = await fetch("/api/files/rename", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
        const j = await r.json();
        if (!j.ok) throw new Error(j.error || "Move failed");
        loadFileManager(fileManagerPath);
        setTreeChildren((prev) => { const next = { ...prev }; delete next[srcParent]; delete next[targetPath]; return next; });
        await refreshTreeDir(targetPath);
      } catch (err) { setMoveError(`Move failed: ${err}`); }
      finally { setMoveBusy(false); setDragSrc(null); }
    }, [dragSrc, fileManagerPath, sep, loadFileManager, refreshTreeDir]);

    const handlePanelDragEnter = React.useCallback((e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); panelDragCount.current += 1; setPDA(true); } }, []);
    const handlePanelDragOver  = React.useCallback((e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); }, []);
    const handlePanelDragLeave = React.useCallback(() => { panelDragCount.current = Math.max(0, panelDragCount.current - 1); if (panelDragCount.current === 0) setPDA(false); }, []);
    const handlePanelDrop      = React.useCallback(async (e) => { panelDragCount.current = 0; setPDA(false); if (!fileManagerPath) return; await handleDrop(e, fileManagerPath); }, [fileManagerPath, handleDrop]);

    // ── Context menu helpers ───────────────────────────────────────────────
    const openCtxMenu = React.useCallback((e, entry) => {
      e.preventDefault();
      setCtxMenu({ x: e.clientX, y: e.clientY, entry: entry || null });
    }, []);

    const handleBgContextMenu = React.useCallback((e) => {
      if (e.target === e.currentTarget || e.currentTarget.contains(e.target)) {
        e.preventDefault();
        setCtxMenu({ x: e.clientX, y: e.clientY, entry: null });
      }
    }, []);

    const ctxCopy = React.useCallback((path, name) => {
      setClipboard({ op: "copy", path, name });
    }, []);

    const ctxCut = React.useCallback((path, name) => {
      setClipboard({ op: "cut", path, name });
    }, []);

    const ctxPaste = React.useCallback(async (targetDir) => {
      if (!clipboard) return;
      setMoveBusy(true); setMoveError("");
      try {
        if (clipboard.op === "copy") {
          const fd = new FormData(); fd.append("source", clipboard.path); fd.append("target_dir", targetDir);
          const r = await fetch("/api/files/copy", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
          const j = await r.json();
          if (!j.ok) throw new Error(j.error || "Copy failed");
        } else {
          // cut = move
          const srcName = clipboard.path.split(/[\\/]/).pop();
          const newPath = `${targetDir.replace(/[\\/]+$/, "")}${sep}${srcName}`;
          const fd = new FormData(); fd.append("source", clipboard.path); fd.append("target", newPath);
          const r = await fetch("/api/files/rename", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
          const j = await r.json();
          if (!j.ok) throw new Error(j.error || "Move failed");
          setClipboard(null); // cut clears clipboard after paste
        }
        loadFileManager(fileManagerPath);
        await refreshTreeDir(targetDir);
      } catch (err) { setMoveError(`Paste failed: ${err.message}`); }
      finally { setMoveBusy(false); }
    }, [clipboard, fileManagerPath, sep, loadFileManager, refreshTreeDir]);

    // ── Show Properties ─────────────────────────────────────────────────────
    const showProperties = React.useCallback(async (entry) => {
      setPropsDlg(entry);
      setPropsData(null);
      setPropsLoading(true);
      try {
        const body = new URLSearchParams();
        body.set("path", entry.path);
        const r = await fetch("/api/files/info", {
          method: "POST",
          headers: { "X-Requested-With": "fetch", "Content-Type": "application/x-www-form-urlencoded" },
          body: body.toString(),
        });
        const j = await r.json();
        setPropsData(j.ok ? j : { error: j.error || "Failed to load properties." });
      } catch (err) {
        setPropsData({ error: String(err) });
      } finally {
        setPropsLoading(false);
      }
    }, []);

    const buildCtxItems = React.useCallback((entry) => {
      const pasteDir = entry ? (entry.is_dir ? entry.path : (fileManagerPath || "")) : (fileManagerPath || "");
      const items = [];
      if (entry) {
        if (!entry.is_dir) {
          items.push({ label: "Open in Editor", icon: OpenFileIcon, action: () => openEditorTab(entry.path) });
          items.push("---");
        } else {
          items.push({ label: "Open Folder", icon: OpenFolderIcon, action: () => loadFileManager(entry.path) });
          items.push("---");
        }
        items.push({ label: "Copy", icon: CopyIcon, action: () => ctxCopy(entry.path, entry.name) });
        items.push({ label: "Cut",  icon: CutIcon,  action: () => ctxCut(entry.path, entry.name) });
      }
      if (clipboard) {
        items.push({ label: `Paste "${clipboard.name}"`, icon: PasteIcon, action: () => ctxPaste(pasteDir) });
      }
      if (items.length) items.push("---");
      if (entry) {
        items.push({ label: "Rename", icon: RenameIcon, action: () => renameFileManagerPath(entry.path), disabled: fileOpBusy });
        items.push({ label: "Delete", icon: DeleteIcon, danger: true, action: () => deleteFileManagerPath(entry.path, entry.is_dir), disabled: fileOpBusy });
        if (!entry.is_dir) {
          items.push("---");
          items.push({ label: "Download", icon: DownloadIcon, action: () => window.open(`/api/files/download?path=${encodeURIComponent(entry.path)}`, "_blank", "noopener,noreferrer") });
        }
        items.push("---");
        items.push({ label: "Properties", icon: ConfigFileIcon, action: () => showProperties(entry) });
        items.push("---");
      }
      items.push({ label: "New Folder", icon: NewFolderIcon, action: createFolderInCurrentPath, disabled: fileOpBusy || !fileManagerPath });
      items.push({ label: "New File",   icon: NewFileIcon,   action: createFileInCurrentPath,   disabled: fileOpBusy || !fileManagerPath });
      items.push("---");
      items.push({ label: "Refresh", icon: RefreshIcon, action: () => loadFileManager(fileManagerPath) });
      return items;
    }, [clipboard, fileManagerPath, fileOpBusy, openEditorTab, loadFileManager, ctxCopy, ctxCut, ctxPaste, renameFileManagerPath, deleteFileManagerPath, createFolderInCurrentPath, createFileInCurrentPath, showProperties]);

    // ─── TOOLBAR ────────────────────────────────────────────────────────────
    const renderToolbar = () => (
      <Box sx={{
        display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap",
        px: 1, py: 0.75, borderBottom: "1px solid #e8eef6", bgcolor: "#f8faff",
      }}>
        <Box sx={{ display: "flex", border: "1px solid #dbe5f6", borderRadius: 1.5, overflow: "hidden", mr: 0.5 }}>
          {[
            { mode: "cloud", icon: GridViewIcon, label: "Cloud View" },
            { mode: "tree",  icon: TreeViewIcon, label: "Tree View" },
          ].map(({ mode, icon, label }) => (
            <Tooltip key={mode} title={label}>
              <IconButton size="small" onClick={() => setViewMode(mode)}
                sx={{ borderRadius: 0, px: 1.25, py: 0.7,
                  bgcolor: viewMode === mode ? "#1d4ed8" : "transparent",
                  color:   viewMode === mode ? "#fff"    : "#475569",
                  "&:hover": { bgcolor: viewMode === mode ? "#1e40af" : "#f1f5f9" },
                }}>
                <Icon icon={icon} sx={{ fontSize: 17 }} />
              </IconButton>
            </Tooltip>
          ))}
        </Box>
        <Tooltip title="Home"><IconButton size="small" sx={{ p: 0.8 }} onClick={() => loadFileManager("")}><Icon icon={HomeIcon} sx={{ fontSize: 18, color: "#475569" }} /></IconButton></Tooltip>
        <Tooltip title="Go Up"><span><IconButton size="small" sx={{ p: 0.8 }} disabled={!fileManagerData?.parent} onClick={() => loadFileManager(fileManagerData?.parent || "")}><Icon icon={BackIcon} sx={{ fontSize: 18, color: "#475569" }} /></IconButton></span></Tooltip>
        <Tooltip title="Refresh"><span><IconButton size="small" sx={{ p: 0.8 }} disabled={fileManagerLoading} onClick={() => loadFileManager(fileManagerPath)}><Icon icon={RefreshIcon} sx={{ fontSize: 18, color: "#475569" }} /></IconButton></span></Tooltip>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, height: 22, alignSelf: "center" }} />
        <Tooltip title="New Folder"><span><IconButton size="small" sx={{ p: 0.8 }} disabled={fileOpBusy || !fileManagerPath} onClick={createFolderInCurrentPath}><Icon icon={NewFolderIcon} sx={{ fontSize: 18, color: "#475569" }} /></IconButton></span></Tooltip>
        <Tooltip title="New File"><span><IconButton size="small" sx={{ p: 0.8 }} disabled={fileOpBusy || !fileManagerPath} onClick={createFileInCurrentPath}><Icon icon={NewFileIcon} sx={{ fontSize: 18, color: "#475569" }} /></IconButton></span></Tooltip>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, height: 22, alignSelf: "center" }} />
        <Tooltip title="Open Terminal Here">
          <span><IconButton size="small" sx={{ p: 0.8 }} onClick={openTerminalTab}><Icon icon={TerminalIcon} sx={{ fontSize: 18, color: "#475569" }} /></IconButton></span>
        </Tooltip>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, height: 22, alignSelf: "center" }} />
        <Tooltip title="Upload Files">
          <span><Button component="label" size="small" variant="outlined" disabled={fileOpBusy || !fileManagerPath}
            startIcon={<Icon icon={UploadIcon} sx={{ fontSize: 15 }} />}
            sx={{ textTransform: "none", fontSize: 12, px: 1.25, py: 0.4, borderColor: "#dbe5f6" }}>
            Upload<input hidden multiple type="file" onChange={uploadIntoCurrentPath} />
          </Button></span>
        </Tooltip>
        <Tooltip title="Upload Folder">
          <span><Button component="label" size="small" variant="outlined" disabled={fileOpBusy || !fileManagerPath}
            startIcon={<Icon icon={UploadIcon} sx={{ fontSize: 15 }} />}
            sx={{ textTransform: "none", fontSize: 12, px: 1.25, py: 0.4, borderColor: "#dbe5f6" }}>
            Folder<input hidden multiple type="file" webkitdirectory="" directory="" onChange={uploadIntoCurrentPath} />
          </Button></span>
        </Tooltip>
        {cloudSelected && (() => {
          const selEntry = entries.find((e) => e.path === cloudSelected);
          return selEntry ? (
            <>
              <Divider orientation="vertical" flexItem sx={{ mx: 0.5, height: 22, alignSelf: "center" }} />
              <Tooltip title="Rename"><span><IconButton size="small" sx={{ p: 0.8 }} disabled={fileOpBusy} onClick={() => renameFileManagerPath(cloudSelected)}><Icon icon={RenameIcon} sx={{ fontSize: 18, color: "#475569" }} /></IconButton></span></Tooltip>
              <Tooltip title="Delete"><span><IconButton size="small" sx={{ p: 0.8 }} disabled={fileOpBusy} onClick={() => deleteFileManagerPath(selEntry.path, selEntry.is_dir)}><Icon icon={DeleteIcon} sx={{ fontSize: 18, color: "#ef4444" }} /></IconButton></span></Tooltip>
              <Tooltip title="Download">
                <span><IconButton size="small" sx={{ p: 0.8 }} onClick={() => window.open(`/api/files/download?path=${encodeURIComponent(selEntry.path)}`, "_blank", "noopener,noreferrer")}>
                  <Icon icon={DownloadIcon} sx={{ fontSize: 18, color: "#475569" }} />
                </IconButton></span>
              </Tooltip>
            </>
          ) : null;
        })()}
        {(fileManagerLoading || fileOpBusy || moveBusy) && <CircularProgress size={15} sx={{ ml: 0.5, color: "#1d4ed8" }} />}
      </Box>
    );

    // ─── BREADCRUMB ──────────────────────────────────────────────────────────
    const renderBreadcrumb = () => (
      <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 0.25, px: 1.5, py: 0.6, bgcolor: "#f8faff", borderBottom: "1px solid #e8eef6" }}>
        {breadcrumbs.map((crumb, i) => (
          <React.Fragment key={crumb.path + "-" + i}>
            {i > 0 && <Icon icon={ChevronRightIcon} sx={{ fontSize: 14, color: "#cbd5e1" }} />}
            <Typography variant="caption"
              sx={{ fontSize: 12, px: 0.75, py: 0.2, borderRadius: 1, cursor: "pointer",
                fontWeight: i === breadcrumbs.length - 1 ? 700 : 400,
                color: i === breadcrumbs.length - 1 ? "#1d4ed8" : "#64748b",
                display: "inline-flex", alignItems: "center", gap: 0.4,
                "&:hover": { bgcolor: "rgba(29,78,216,.07)", color: "#1d4ed8" },
              }}
              onClick={() => loadFileManager(crumb.path)}>
              {i === 0 && <Icon icon={StorageIcon} sx={{ fontSize: 13 }} />}
              {crumb.label}
            </Typography>
          </React.Fragment>
        ))}
      </Box>
    );

    // ─── PATH BAR ────────────────────────────────────────────────────────────
    const renderPathBar = () => (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.75, bgcolor: "#fff", borderBottom: "1px solid #e8eef6" }}>
        <TextField size="small" fullWidth value={pathInput}
          onChange={(e) => setPathInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { if (setFileManagerPath) setFileManagerPath(pathInput); loadFileManager(pathInput); } }}
          placeholder={os === "windows" ? "C:\\" : "/"}
          sx={{ "& .MuiOutlinedInput-input": { fontSize: 12, py: 0.6, fontFamily: "Consolas, monospace" }, "& .MuiOutlinedInput-root": { borderRadius: 1.5 } }}
          InputProps={{ endAdornment: <InputAdornment position="end"><IconButton size="small" onClick={() => { if (setFileManagerPath) setFileManagerPath(pathInput); loadFileManager(pathInput); }}><Icon icon={RefreshIcon} sx={{ fontSize: 15 }} /></IconButton></InputAdornment> }}
        />
      </Box>
    );

    // ─── CLOUD VIEW ──────────────────────────────────────────────────────────
    const renderCloudView = () => (
      <Box sx={{
          flexGrow: 1, overflow: "auto", p: 2, minHeight: 400, position: "relative",
          bgcolor: panelDragActive ? "rgba(29,78,216,.03)" : "#fff",
          outline: panelDragActive ? "3px dashed #1d4ed8" : "none",
          outlineOffset: -4, transition: "background-color .15s, outline .15s",
        }}
        onDragEnter={handlePanelDragEnter} onDragOver={handlePanelDragOver}
        onDragLeave={handlePanelDragLeave} onDrop={handlePanelDrop}
        onClick={() => setCloudSelected(null)}
        onContextMenu={handleBgContextMenu}
      >
        {panelDragActive && fileManagerPath && (
          <Box sx={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", zIndex: 10, pointerEvents: "none" }}>
            <Paper sx={{ px: 5, py: 3, border: "2px dashed #1d4ed8", bgcolor: "rgba(255,255,255,.95)", borderRadius: 3, textAlign: "center" }}>
              <Icon icon={UploadIcon} sx={{ fontSize: 40, color: "#1d4ed8", mb: 1 }} />
              <Typography fontWeight={700} color="#1d4ed8" variant="h6">Drop files to upload</Typography>
              <Typography variant="caption" color="text.secondary">Files will be added to the current folder</Typography>
            </Paper>
          </Box>
        )}
        {fileManagerLoading && <LinearProgress sx={{ mb: 1.5, borderRadius: 1 }} />}
        {fileManagerError && <Alert severity="error" sx={{ mb: 1.5 }}>{fileManagerError}</Alert>}
        {(moveError || opError) && <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => { setMoveError(""); setOpError(""); }}>{moveError || opError}</Alert>}
        {entries.length === 0 && !fileManagerLoading && (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", py: 8, color: "#94a3b8" }}>
            <Icon icon={FolderOpenIcon} sx={{ fontSize: 72, opacity: 0.25 }} />
            <Typography variant="body2" color="text.secondary">{fileManagerPath ? "This folder is empty." : "Select a drive or folder to start browsing."}</Typography>
            {fileManagerPath && <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>Drag & drop files here to upload them.</Typography>}
          </Box>
        )}
        {folderEntries.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" sx={{ color: "#94a3b8", fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: .08, px: 0.5 }}>Folders ({folderEntries.length})</Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.75, pb: 3.5 }}>
              {folderEntries.map((entry) => (
                <CloudEntry key={entry.path} entry={entry}
                  isSelected={cloudSelected === entry.path} isDragOver={dragOver === entry.path}
                  onClick={(e) => setCloudSelected(e.path)}
                  onDoubleClick={(entry) => { loadFileManager(entry.path); setCloudSelected(null); }}
                  onDragStart={handleDragStart} onDragEnter={handleDragEnter}
                  onDragLeave={handleDragLeave} onDrop={handleDrop}
                  onRename={renameFileManagerPath} onDelete={deleteFileManagerPath}
                  onDownload={(p) => window.open(`/api/files/download?path=${encodeURIComponent(p)}`, "_blank", "noopener,noreferrer")}
                  onOpenTab={openEditorTab} fileOpBusy={fileOpBusy}
                  onContextMenu={openCtxMenu} />
              ))}
            </Box>
          </Box>
        )}
        {fileEntries.length > 0 && (
          <Box>
            <Typography variant="caption" sx={{ color: "#94a3b8", fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: .08, px: 0.5 }}>Files ({fileEntries.length})</Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.75, pb: 2 }}>
              {fileEntries.map((entry) => (
                <CloudEntry key={entry.path} entry={entry}
                  isSelected={cloudSelected === entry.path} isDragOver={false}
                  onClick={(e) => setCloudSelected(e.path)}
                  onDoubleClick={(entry) => openEditorTab(entry.path)}
                  onDragStart={handleDragStart} onDragEnter={handleDragEnter}
                  onDragLeave={handleDragLeave} onDrop={handleDrop}
                  onRename={renameFileManagerPath} onDelete={deleteFileManagerPath}
                  onDownload={(p) => window.open(`/api/files/download?path=${encodeURIComponent(p)}`, "_blank", "noopener,noreferrer")}
                  onOpenTab={openEditorTab} fileOpBusy={fileOpBusy}
                  onContextMenu={openCtxMenu} />
              ))}
            </Box>
          </Box>
        )}
      </Box>
    );

    // ─── TREE VIEW ────────────────────────────────────────────────────────────
    const renderTreeView = () => (
      <Box sx={{ display: "flex", flexGrow: 1, overflow: "hidden", minHeight: 400 }}>
        <Box sx={{ width: 256, minWidth: 160, flexShrink: 0, borderRight: "1px solid #e8eef6", overflow: "auto", bgcolor: "#f8faff", py: 0.75 }}>
          {!treeRootsLoaded && <Box sx={{ display: "flex", justifyContent: "center", pt: 3 }}><CircularProgress size={20} /></Box>}
          <FileTree
            items={treeRoots} depth={0}
            treeExpanded={treeExpanded} treeChildren={treeChildren}
            treeLoading={treeLoading} selected={treeSelected} dragOverPath={dragOver}
            onToggle={handleTreeToggle} onSelect={handleTreeSelect}
            onDragStart={handleDragStart} onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave} onDrop={handleDrop}
            onContextMenu={openCtxMenu}
          />
        </Box>
        <Box sx={{ flexGrow: 1, overflow: "auto", bgcolor: "#fff", position: "relative" }}
          onDragEnter={handlePanelDragEnter} onDragOver={handlePanelDragOver}
          onDragLeave={handlePanelDragLeave} onDrop={handlePanelDrop}
          onContextMenu={handleBgContextMenu}>
          {panelDragActive && fileManagerPath && (
            <Box sx={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", zIndex: 10, pointerEvents: "none" }}>
              <Paper sx={{ px: 4, py: 2.5, border: "2px dashed #1d4ed8", bgcolor: "rgba(255,255,255,.95)", borderRadius: 3, textAlign: "center" }}>
                <Icon icon={UploadIcon} sx={{ fontSize: 32, color: "#1d4ed8", mb: 0.5 }} />
                <Typography fontWeight={700} color="#1d4ed8">Drop files to upload</Typography>
              </Paper>
            </Box>
          )}
          {fileManagerLoading && <LinearProgress sx={{ position: "absolute", top: 0, left: 0, right: 0 }} />}
          {fileManagerError && <Alert severity="error" sx={{ m: 1 }}>{fileManagerError}</Alert>}
          {moveError && <Alert severity="error" sx={{ m: 1 }} onClose={() => setMoveError("")}>{moveError}</Alert>}
          {entries.length === 0 && !fileManagerLoading && (
            <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", py: 6, color: "#94a3b8" }}>
              <Typography variant="body2" color="text.secondary">{fileManagerPath ? "Empty folder." : "Select a folder in the tree."}</Typography>
            </Box>
          )}
          {entries.map((entry) => (
            <Box key={entry.path}
              sx={{
                display: "flex", alignItems: "center", gap: 1, px: 1.5, py: 0.6,
                cursor: "pointer", borderRadius: 1.5, mx: 0.5, my: "1px",
                bgcolor: dragOver === entry.path ? "rgba(34,197,94,.08)" : "transparent",
                outline: dragOver === entry.path ? "1.5px dashed #16a34a" : "none",
                "&:hover": { bgcolor: "rgba(29,78,216,.04)" }, userSelect: "none",
              }}
              draggable
              onDragStart={(e) => handleDragStart(e, entry)}
              onDragEnter={entry.is_dir ? (e) => handleDragEnter(e, entry.path) : undefined}
              onDragOver={entry.is_dir ? (e) => e.preventDefault() : undefined}
              onDragLeave={entry.is_dir ? (e) => handleDragLeave(e, entry.path) : undefined}
              onDrop={entry.is_dir ? (e) => handleDrop(e, entry.path) : undefined}
              onClick={() => { if (!entry.is_dir) openEditorTab(entry.path); else loadFileManager(entry.path); }}
              onDoubleClick={() => { if (entry.is_dir) { loadFileManager(entry.path); handleTreeToggle(entry.path); } }}
              onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); openCtxMenu(e, entry); }}
            >
              {entry.is_dir
                ? <Icon icon={FolderIcon} sx={{ fontSize: 18, color: "#f59e0b", flexShrink: 0 }} />
                : <Icon icon={getFileTypeIcon(entry.name)} sx={{ fontSize: 16, color: fileExtColor(entry.name), flexShrink: 0 }} />
              }
              <Typography variant="body2" noWrap sx={{ flexGrow: 1, fontSize: 13, minWidth: 0 }}>{entry.name}</Typography>
              <Typography variant="caption" sx={{ color: "#94a3b8", fontSize: 11, flexShrink: 0, minWidth: 56, textAlign: "right" }}>{entry.is_dir ? "" : fmtBytes(entry.size)}</Typography>
              <Typography variant="caption" sx={{ color: "#cbd5e1", fontSize: 11, flexShrink: 0, minWidth: 80, textAlign: "right", display: { xs: "none", md: "block" } }}>{fmtDate(entry.modified_ts)}</Typography>
            </Box>
          ))}
        </Box>
      </Box>
    );

    // ─── EDITOR PANEL ─────────────────────────────────────────────────────────
    const renderEditorPanel = () => {
      const hasOpenTabs = editorTabs.length > 0;
      const visibleTabs = editorTabs.filter((t) => !minimizedTabs.includes(t.path));
      const tab = activeTab;

      return (
        <Box sx={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 500 }}>
          {/* Tab bar */}
          {hasOpenTabs && (
            <Box sx={{
              display: "flex", alignItems: "stretch", overflowX: "auto", flexShrink: 0,
              borderBottom: "1px solid #e8eef6", bgcolor: "#f0f4ff",
              "&::-webkit-scrollbar": { height: 4 }, "&::-webkit-scrollbar-thumb": { bgcolor: "#c7d2fe", borderRadius: 2 },
            }}>
              {editorTabs.map((t) => {
                const isMin = minimizedTabs.includes(t.path);
                const isActive = t.path === activeTabPath && !isMin;
                const isTerm = t.kind === "terminal";
                const fname = isTerm ? (t.title || "Terminal") : t.path.split(/[\\/]/).pop();
                return (
                  <Box key={t.path}
                    onDoubleClick={() => isMin ? restoreTab(t.path) : undefined}
                    sx={{
                      display: "flex", alignItems: "center", gap: 0.5, px: 1.25, py: 0.5,
                      cursor: "pointer", flexShrink: 0, maxWidth: 180, minWidth: 90,
                      borderRight: "1px solid #dbe5f6",
                      bgcolor: isActive ? "#fff" : isMin ? "#f8faff" : "#eef2fc",
                      opacity: isMin ? 0.55 : 1,
                      borderBottom: isActive ? "2px solid #1d4ed8" : "2px solid transparent",
                      "&:hover": { bgcolor: isMin ? "#f1f5f9" : "#fff" },
                      transition: "background-color .1s",
                    }}
                    onClick={() => { if (isMin) restoreTab(t.path); else setActiveTabPath(t.path); }}
                  >
                    <Icon icon={isTerm ? TerminalIcon : getFileTypeIcon(fname)} sx={{ fontSize: 13, color: isTerm ? "#22c55e" : fileExtColor(fname), flexShrink: 0 }} />
                    <Typography noWrap sx={{ fontSize: 12, flexGrow: 1, minWidth: 0, fontWeight: isActive ? 700 : 400, fontStyle: isMin ? "italic" : "normal", color: isActive ? "#1d4ed8" : "#374151" }}>
                      {fname}{!isTerm && t.dirty ? " ●" : ""}
                    </Typography>
                    {t.loading && !isTerm && <CircularProgress size={10} sx={{ flexShrink: 0 }} />}
                    <Tooltip title="Close">
                      <Box component="span" onClick={(e) => { e.stopPropagation(); closeTab(t.path); }}
                        sx={{ flexShrink: 0, opacity: 0.45, cursor: "pointer", display: "flex", "&:hover": { opacity: 1 }, lineHeight: 0 }}>
                        <Icon icon={CloseIcon} sx={{ fontSize: 13, color: "#ef4444" }} />
                      </Box>
                    </Tooltip>
                  </Box>
                );
              })}
            </Box>
          )}

          {/* Terminal tabs — always in DOM once opened so the session stays alive */}
          {editorTabs.filter((t) => t.kind === "terminal").map((t) => {
            const isTermActive = t.path === activeTabPath && !minimizedTabs.includes(t.path);
            return (
              <Box key={t.path} sx={{ display: isTermActive ? "flex" : "none", flexGrow: 1, overflow: "hidden", flexDirection: "column" }}>
                <TerminalView cwd={t.cwd} isActive={isTermActive} initialInput={t.initialInput} />
              </Box>
            );
          })}

          {/* Minimized-only message when active tab is minimized or nothing active */}
          {(!tab) && hasOpenTabs && !editorTabs.some((t) => t.kind === "terminal" && t.path === activeTabPath && !minimizedTabs.includes(t.path)) && (
            <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", p: 3, color: "#94a3b8" }}>
              <Icon icon={MinimizeIcon} sx={{ fontSize: 40, opacity: 0.2 }} />
              <Typography variant="body2" color="text.secondary" align="center" sx={{ mt: 1 }}>
                All editors are minimized. Click a tab to restore.
              </Typography>
            </Box>
          )}

          {/* No tabs open */}
          {!hasOpenTabs && (
            <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", p: 3, color: "#94a3b8" }}>
              <Icon icon={FileIcon} sx={{ fontSize: 52, opacity: 0.2 }} />
              <Typography variant="body2" color="text.secondary" align="center">Open a file to edit it here.</Typography>
              <Typography variant="caption" color="text.secondary" align="center" sx={{ mt: 0.5, display: "block" }}>
                Double-click a file in Cloud view, or click in Tree view.
              </Typography>
            </Box>
          )}

          {/* Active editor — file tabs only; terminal tabs are rendered above */}
          {tab && tab.kind !== "terminal" && (
            <>
              {/* Path strip */}
              <Box sx={{ px: 1.5, py: 0.4, bgcolor: "#fafbff", borderBottom: "1px solid #f1f5f9" }}>
                <Typography variant="caption" noWrap sx={{ color: "#64748b", fontSize: 11, fontFamily: "Consolas, monospace" }}>
                  {tab.path}
                  {tab.meta?.encoding ? ` · ${tab.meta.encoding}` : ""}
                  {tab.meta?.size ? ` · ${fmtBytes(tab.meta.size)}` : ""}
                </Typography>
              </Box>

              {/* Textarea */}
              <Box sx={{ flexGrow: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
                <TextField multiline fullWidth
                  minRows={16} maxRows={28}
                  value={tab.content}
                  onChange={(e) => {
                    const newContent = e.target.value;
                    setEditorTabs((prev) => prev.map((t) => t.path === tab.path ? { ...t, content: newContent, dirty: newContent !== t.originalContent } : t));
                  }}
                  disabled={tab.loading}
                  sx={{
                    flexGrow: 1,
                    "& .MuiOutlinedInput-root": {
                      borderRadius: 0, fontFamily: "Consolas, 'Courier New', monospace",
                      fontSize: 12.5, lineHeight: 1.6, bgcolor: "#fff",
                    },
                    "& fieldset": { border: "none" },
                  }}
                />
              </Box>

              {/* Action bar */}
              <Box sx={{
                display: "flex", alignItems: "center", gap: 1, px: 1.5, py: 0.75,
                borderTop: "1px solid #e8eef6", bgcolor: "#f8faff", flexShrink: 0,
              }}>
                {tab.dirty && (
                  <Chip size="small" label="unsaved"
                    sx={{ height: 18, fontSize: 10.5, bgcolor: "#fef9c3", color: "#854d0e", border: "1px solid #fde047" }} />
                )}
                <Box sx={{ flexGrow: 1 }} />
                <Button size="small" variant="outlined" disabled={!tab.dirty || tab.loading}
                  onClick={() => discardTab(tab.path)}
                  sx={{ textTransform: "none", fontSize: 12, px: 1.5, py: 0.35, color: "#64748b", borderColor: "#dbe5f6" }}>
                  Discard
                </Button>
                <Button size="small" variant="contained" disabled={!tab.dirty || tab.loading}
                  onClick={() => saveTab(tab.path)}
                  sx={{ textTransform: "none", fontSize: 12, px: 1.5, py: 0.35, bgcolor: "#1d4ed8", "&:hover": { bgcolor: "#1e40af" } }}>
                  Save
                </Button>
              </Box>
            </>
          )}
        </Box>
      );
    };

    // ─── ROOT RENDER ──────────────────────────────────────────────────────────
    return (
      <Box sx={{ display: "flex", gap: 0, alignItems: "flex-start" }}>
        {/* LEFT: File browser */}
        <Box sx={{
          flexGrow: 1, minWidth: 0, minHeight: 540,
          border: "1px solid #dbe5f6", borderRadius: 2.5, overflow: "hidden", bgcolor: "#fff",
          boxShadow: "0 4px 18px rgba(15,23,42,.07)", display: "flex", flexDirection: "column",
        }}>
          {renderToolbar()}
          {viewMode === "cloud" && renderBreadcrumb()}
          {viewMode === "tree"  && renderPathBar()}
          {viewMode === "cloud" ? renderCloudView() : renderTreeView()}
        </Box>

        {/* Resize handle */}
        <Box
          onMouseDown={startResize}
          sx={{
            width: 8, flexShrink: 0, cursor: "col-resize", alignSelf: "stretch",
            display: "flex", alignItems: "center", justifyContent: "center",
            "&:hover > div, &:active > div": { bgcolor: "#1d4ed8", opacity: 1 },
          }}>
          <Box sx={{ width: 3, height: 40, bgcolor: "#dbe5f6", borderRadius: 2, opacity: 0.7, transition: "background-color .15s, opacity .15s" }} />
        </Box>

        {/* RIGHT: Multi-tab Editor */}
        <Box sx={{
          width: editorWidth, flexShrink: 0,
          border: "1px solid #dbe5f6", borderRadius: 2.5, overflow: "hidden", bgcolor: "#fff",
          boxShadow: "0 4px 18px rgba(15,23,42,.07)",
        }}>
          {renderEditorPanel()}
        </Box>

        {/* Context menu portal */}
        {ctxMenu && (
          <ContextMenu
            x={ctxMenu.x} y={ctxMenu.y}
            items={buildCtxItems(ctxMenu.entry)}
            onClose={() => setCtxMenu(null)}
          />
        )}

        {/* Properties dialog */}
        {propsDlg && (() => {
          const { Dialog, DialogTitle, DialogContent, DialogActions, Button: MuiBtn, Divider: MuiDiv } = MaterialUI;
          if (!Dialog) return null;
          const fmt = (b) => {
            if (b == null) return "—";
            if (b === 0) return "0 B";
            const k = 1024, u = ["B", "KB", "MB", "GB", "TB"];
            const i = Math.min(Math.floor(Math.log(b + 1) / Math.log(k)), u.length - 1);
            return `${+(b / k ** i).toFixed(2)} ${u[i]}`;
          };
          const fmtTs = (ts) => ts ? new Date(ts * 1000).toLocaleString() : "—";
          const d = propsData;
          const rows = d && !d.error ? [
            ["Name",        d.name],
            ["Type",        d.type === "folder" ? "Folder" : `File${d.extension ? ` (.${d.extension})` : ""}`],
            ["Location",    d.path],
            d.type === "folder"
              ? ["Contains", d.item_count != null ? `${d.item_count} item(s)` : "—"]
              : ["Size",     fmt(d.size_bytes)],
            d.type === "folder" && d.dir_size_bytes != null
              ? ["Total Size", fmt(d.dir_size_bytes)]
              : null,
            ["Modified",    fmtTs(d.modified)],
            ["Created",     fmtTs(d.created)],
            ["Permissions", d.permissions || "—"],
          ].filter(Boolean) : [];
          return (
            <Dialog open onClose={() => { setPropsDlg(null); setPropsData(null); }} maxWidth="sm" fullWidth>
              <DialogTitle sx={{ fontWeight: 800, pb: 0.5 }}>
                Properties — {propsDlg.name}
              </DialogTitle>
              <MuiDiv />
              <DialogContent sx={{ pt: 1.5 }}>
                {propsLoading && (
                  <Typography variant="body2" color="text.secondary">Loading…</Typography>
                )}
                {d && d.error && (
                  <Alert severity="error">{d.error}</Alert>
                )}
                {rows.map(([label, val]) => (
                  <Box key={label} sx={{ display: "flex", mb: 1 }}>
                    <Typography variant="body2" fontWeight={700} sx={{ minWidth: 110, color: "text.secondary" }}>{label}</Typography>
                    <Typography variant="body2" sx={{ wordBreak: "break-all" }}>{val}</Typography>
                  </Box>
                ))}
              </DialogContent>
              <DialogActions>
                <MuiBtn onClick={() => { setPropsDlg(null); setPropsData(null); }} sx={{ textTransform: "none" }}>Close</MuiBtn>
              </DialogActions>
            </Dialog>
          );
        })()}
      </Box>
    );
  }

  window.ServerInstallerUI = window.ServerInstallerUI || {};
  window.ServerInstallerUI.FileManagerPage = FileManagerPage;
})();
