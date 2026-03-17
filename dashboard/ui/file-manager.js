// Professional File Manager — Cloud view (Google Cloud style) + Tree view (VS Code style)
// Supports drag-and-drop upload and move, breadcrumb nav, lazy tree loading.
(() => {
  const {
    Alert, Box, Button, Chip, CircularProgress,
    Divider, IconButton, LinearProgress, Paper,
    TextField, Tooltip, Typography, InputAdornment,
  } = MaterialUI;
  const MuiIcons = window.MaterialUIIcons || {};

  // ─── Icon helpers (graceful fallbacks) ────────────────────────────────────
  function ic(name) { return MuiIcons[name + "Rounded"] || MuiIcons[name] || null; }
  const FolderIcon        = ic("Folder");
  const FolderOpenIcon    = ic("FolderOpen");
  const FileIcon          = ic("InsertDriveFile");
  const ImageFileIcon     = ic("Image") || ic("Photo");
  const VideoFileIcon     = ic("VideoFile") || ic("Videocam");
  const AudioFileIcon     = ic("AudioFile") || ic("Audiotrack");
  const PdfFileIcon       = ic("PictureAsPdf") || ic("Description");
  const ZipFileIcon       = ic("FolderZip") || ic("Archive");
  const CodeFileIcon      = ic("Code");
  const DataFileIcon      = ic("TableChart") || ic("GridOn");
  const DocFileIcon       = ic("Article") || ic("Description");
  const ShellFileIcon     = ic("Terminal") || ic("Code");
  const ConfigFileIcon    = ic("Settings") || ic("Tune");

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
    return null;
  }

  const ChevronRightIcon  = ic("ChevronRight");
  const ExpandMoreIcon    = ic("ExpandMore");
  const GridViewIcon      = ic("GridView") || ic("Apps");
  const TreeViewIcon      = ic("AccountTree");
  const RefreshIcon       = ic("Refresh");
  const HomeIcon          = ic("Home");
  const DeleteIcon        = ic("Delete");
  const RenameIcon        = ic("DriveFileRenameOutline") || ic("Edit");
  const DownloadIcon      = ic("Download");
  const NewFolderIcon     = ic("CreateNewFolder");
  const NewFileIcon       = ic("NoteAdd");
  const UploadIcon        = ic("CloudUpload");
  const BackIcon          = ic("ArrowBack");
  const StorageIcon       = ic("Storage") || ic("Computer");
  const EditCodeIcon      = ic("Code") || ic("Edit");

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

  // ─── Render a MUI icon safely ───────────────────────────────────────────────
  function Icon({ icon, sx, onClick }) {
    if (!icon) return null;
    return React.createElement(icon, { sx, onClick });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TREE NODE ROW
  // ═══════════════════════════════════════════════════════════════════════════
  function TreeNodeRow({ entry, depth, isExpanded, isLoadingChildren, isSelected, isDragOver,
    onToggle, onSelect, onDragStart, onDragEnter, onDragLeave, onDrop }) {
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
        draggable
        onDragStart={(e) => onDragStart(e, entry)}
        onDragEnter={isDir ? (e) => onDragEnter(e, entry.path) : undefined}
        onDragOver={isDir ? (e) => e.preventDefault() : undefined}
        onDragLeave={isDir ? (e) => onDragLeave(e, entry.path) : undefined}
        onDrop={isDir ? (e) => onDrop(e, entry.path) : undefined}
      >
        {/* Expand/collapse arrow */}
        <Box sx={{ width: 18, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          {isDir && isLoadingChildren && <CircularProgress size={11} />}
          {isDir && !isLoadingChildren && (
            <Box
              component={isExpanded ? (ExpandMoreIcon || "span") : (ChevronRightIcon || "span")}
              sx={{ fontSize: 16, color: "text.secondary", cursor: "pointer" }}
              onClick={(e) => { e.stopPropagation(); onToggle(entry.path); }}
            />
          )}
        </Box>
        {/* Icon */}
        {isDir ? (
          <Box component={(isExpanded && FolderOpenIcon) ? FolderOpenIcon : (FolderIcon || "span")}
            sx={{ fontSize: 16, color: "#f59e0b", mr: 0.6, flexShrink: 0 }} />
        ) : (
          <Box component={getFileTypeIcon(entry.name) || FileIcon || "span"}
            sx={{ fontSize: 15, color: fileExtColor(entry.name), mr: 0.6, flexShrink: 0 }} />
        )}
        {/* Name */}
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
    onToggle, onSelect, onDragStart, onDragEnter, onDragLeave, onDrop }) {
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
              />
              {expanded && entry.is_dir && (
                <FileTree
                  items={children} depth={depth + 1}
                  treeExpanded={treeExpanded} treeChildren={treeChildren}
                  treeLoading={treeLoading} selected={selected} dragOverPath={dragOverPath}
                  onToggle={onToggle} onSelect={onSelect}
                  onDragStart={onDragStart} onDragEnter={onDragEnter}
                  onDragLeave={onDragLeave} onDrop={onDrop}
                />
              )}
            </Box>
          );
        })}
      </Box>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CLOUD ENTRY (Google Cloud / icon grid style)
  // ═══════════════════════════════════════════════════════════════════════════
  function CloudEntry({ entry, isSelected, isDragOver, onClick, onDoubleClick,
    onDragStart, onDragEnter, onDragLeave, onDrop,
    onRename, onDelete, onDownload, onEdit, fileOpBusy }) {
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
        onClick={() => onClick(entry)}
        onDoubleClick={() => onDoubleClick(entry)}
        draggable
        onDragStart={(e) => onDragStart(e, entry)}
        onDragEnter={isDir ? (e) => onDragEnter(e, entry.path) : undefined}
        onDragOver={isDir ? (e) => e.preventDefault() : undefined}
        onDragLeave={isDir ? (e) => onDragLeave(e, entry.path) : undefined}
        onDrop={isDir ? (e) => onDrop(e, entry.path) : undefined}
      >
        {/* Icon */}
        {isDir ? (
          <Box component={FolderIcon || "span"} sx={{ fontSize: 52, color: isDragOver ? "#16a34a" : "#f59e0b" }} />
        ) : (
          <Box sx={{
            width: 40, height: 52, bgcolor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 1.5,
            display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          }}>
            <Typography sx={{ fontSize: 9, fontWeight: 800, color: fileExtColor(entry.name), textTransform: "uppercase", letterSpacing: .5, lineHeight: 1 }}>
              {ext || "FILE"}
            </Typography>
            <Box component={getFileTypeIcon(entry.name) || FileIcon || "span"} sx={{ fontSize: 18, color: fileExtColor(entry.name), mt: 0.25 }} />
          </Box>
        )}
        {/* Name */}
        <Typography variant="caption" align="center"
          sx={{ mt: 0.5, fontSize: 11.5, lineHeight: 1.3, maxWidth: 88, wordBreak: "break-all",
            display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
            fontWeight: isSelected ? 700 : 400 }}>
          {entry.name}
        </Typography>
        {/* Quick action bar — shows on selection */}
        {isSelected && (
          <Box sx={{
            position: "absolute", bottom: -28, left: "50%", transform: "translateX(-50%)",
            display: "flex", gap: 0.25, bgcolor: "#fff", border: "1px solid #dbe5f6",
            borderRadius: 1.5, px: 0.5, py: 0.25, boxShadow: "0 4px 12px rgba(0,0,0,.1)", zIndex: 20,
          }}>
            {!isDir && (
              <Tooltip title="Edit">
                <IconButton size="small" sx={{ p: 0.3 }} onClick={(e) => { e.stopPropagation(); onEdit(entry.path); }}>
                  <Icon icon={EditCodeIcon} sx={{ fontSize: 13, color: "#475569" }} />
                </IconButton>
              </Tooltip>
            )}
            {!isDir && (
              <Tooltip title="Download">
                <IconButton size="small" sx={{ p: 0.3 }} onClick={(e) => { e.stopPropagation(); onDownload(entry.path); }}>
                  <Icon icon={DownloadIcon} sx={{ fontSize: 13, color: "#475569" }} />
                </IconButton>
              </Tooltip>
            )}
            <Tooltip title="Rename">
              <IconButton size="small" sx={{ p: 0.3 }} disabled={fileOpBusy} onClick={(e) => { e.stopPropagation(); onRename(entry.path); }}>
                <Icon icon={RenameIcon} sx={{ fontSize: 13, color: "#475569" }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Delete">
              <IconButton size="small" sx={{ p: 0.3 }} disabled={fileOpBusy} onClick={(e) => { e.stopPropagation(); onDelete(entry.path, entry.is_dir); }}>
                <Icon icon={DeleteIcon} sx={{ fontSize: 13, color: "#ef4444" }} />
              </IconButton>
            </Tooltip>
          </Box>
        )}
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
    const [viewMode, setViewMode]         = React.useState("cloud"); // "cloud" | "tree"
    const [cloudSelected, setCloudSelected] = React.useState(null);

    // ── Tree state ─────────────────────────────────────────────────────────
    const [treeRoots, setTreeRoots]       = React.useState([]);
    const [treeRootsLoaded, setTRL]       = React.useState(false);
    const [treeExpanded, setTreeExpanded] = React.useState(() => new Set());
    const [treeChildren, setTreeChildren] = React.useState({});
    const [treeLoading, setTreeLoading]   = React.useState(() => new Set());
    const [treeSelected, setTreeSelected] = React.useState(null);

    // ── Drag-and-drop state ────────────────────────────────────────────────
    const [dragSrc, setDragSrc]       = React.useState(null);
    const [dragOver, setDragOver]     = React.useState(null);
    const dragEnterCounters           = React.useRef({});    // path → enter count
    const [panelDragActive, setPDA]   = React.useState(false);
    const panelDragCount              = React.useRef(0);

    // ── Op state ──────────────────────────────────────────────────────────
    const [moveError, setMoveError]   = React.useState("");
    const [moveBusy, setMoveBusy]     = React.useState(false);

    // Local path input (for path bar)
    const [pathInput, setPathInput]   = React.useState(fileManagerPath || "");
    React.useEffect(() => { setPathInput(fileManagerPath || ""); }, [fileManagerPath]);

    const entries       = React.useMemo(() => Array.isArray(fileManagerData?.entries) ? fileManagerData.entries : [], [fileManagerData]);
    const breadcrumbs   = React.useMemo(() => buildBreadcrumbs(fileManagerPath, os), [fileManagerPath, os]);
    const folderEntries = React.useMemo(() => entries.filter((e) => e.is_dir), [entries]);
    const fileEntries   = React.useMemo(() => entries.filter((e) => !e.is_dir), [entries]);

    // ── Load tree roots when switching to tree mode ────────────────────────
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

    // ── Tree toggle ────────────────────────────────────────────────────────
    const handleTreeToggle = React.useCallback(async (path) => {
      const next = new Set(treeExpanded);
      if (next.has(path)) { next.delete(path); setTreeExpanded(next); return; }
      next.add(path);
      setTreeExpanded(next);
      if (treeChildren[path]) return;
      setTreeLoading((prev) => { const s = new Set(prev); s.add(path); return s; });
      try {
        const r = await fetch(`/api/files/list?path=${encodeURIComponent(path)}`, { headers: { "X-Requested-With": "fetch" } });
        const j = await r.json();
        if (j.ok) setTreeChildren((p) => ({ ...p, [path]: j.entries || [] }));
      } catch (_) {}
      setTreeLoading((prev) => { const s = new Set(prev); s.delete(path); return s; });
    }, [treeExpanded, treeChildren]);

    // Refresh tree children for a path
    const refreshTreeDir = React.useCallback(async (path) => {
      if (!path) return;
      try {
        const r = await fetch(`/api/files/list?path=${encodeURIComponent(path)}`, { headers: { "X-Requested-With": "fetch" } });
        const j = await r.json();
        if (j.ok) setTreeChildren((p) => ({ ...p, [path]: j.entries || [] }));
      } catch (_) {}
    }, []);

    // ── Tree select ───────────────────────────────────────────────────────
    const handleTreeSelect = React.useCallback((entry) => {
      setTreeSelected(entry.path);
      if (entry.is_dir) {
        loadFileManager(entry.path);
        handleTreeToggle(entry.path);
      } else {
        openFileInEditor(entry.path);
      }
    }, [loadFileManager, openFileInEditor, handleTreeToggle]);

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
      if (dragEnterCounters.current[path] === 0) {
        setDragOver((prev) => (prev === path ? null : prev));
      }
    }, []);

    const handleDrop = React.useCallback(async (e, targetPath) => {
      e.preventDefault();
      e.stopPropagation();
      dragEnterCounters.current[targetPath] = 0;
      setDragOver(null);

      // Determine if this is an upload (external) or a move (internal)
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
        // Invalidate tree nodes
        setTreeChildren((prev) => {
          const next = { ...prev };
          delete next[srcParent]; delete next[targetPath]; return next;
        });
        await refreshTreeDir(targetPath);
      } catch (err) { setMoveError(`Move failed: ${err}`); }
      finally { setMoveBusy(false); setDragSrc(null); }
    }, [dragSrc, fileManagerPath, sep, loadFileManager, refreshTreeDir]);

    // Panel-level drag (for dropping files from desktop into empty space)
    const handlePanelDragEnter = React.useCallback((e) => {
      if (e.dataTransfer.types.includes("Files")) {
        e.preventDefault();
        panelDragCount.current += 1;
        setPDA(true);
      }
    }, []);
    const handlePanelDragOver = React.useCallback((e) => {
      if (e.dataTransfer.types.includes("Files")) e.preventDefault();
    }, []);
    const handlePanelDragLeave = React.useCallback(() => {
      panelDragCount.current = Math.max(0, panelDragCount.current - 1);
      if (panelDragCount.current === 0) setPDA(false);
    }, []);
    const handlePanelDrop = React.useCallback(async (e) => {
      panelDragCount.current = 0; setPDA(false);
      if (!fileManagerPath) return;
      await handleDrop(e, fileManagerPath);
    }, [fileManagerPath, handleDrop]);

    // ─── TOOLBAR ────────────────────────────────────────────────────────────
    const renderToolbar = () => (
      <Box sx={{
        display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap",
        px: 1, py: 0.75, borderBottom: "1px solid #e8eef6", bgcolor: "#f8faff",
      }}>
        {/* View mode toggle */}
        <Box sx={{ display: "flex", border: "1px solid #dbe5f6", borderRadius: 1.5, overflow: "hidden", mr: 0.5 }}>
          {[
            { mode: "cloud", icon: GridViewIcon, label: "Cloud View (Google style)" },
            { mode: "tree",  icon: TreeViewIcon, label: "Tree View (VS Code style)" },
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

        {/* Navigation */}
        <Tooltip title="Home / Computer">
          <IconButton size="small" sx={{ p: 0.8 }} onClick={() => loadFileManager("")}>
            <Icon icon={HomeIcon} sx={{ fontSize: 18, color: "#475569" }} />
          </IconButton>
        </Tooltip>
        <Tooltip title="Go Up">
          <span>
            <IconButton size="small" sx={{ p: 0.8 }} disabled={!fileManagerData?.parent}
              onClick={() => loadFileManager(fileManagerData?.parent || "")}>
              <Icon icon={BackIcon} sx={{ fontSize: 18, color: "#475569" }} />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Refresh">
          <span>
            <IconButton size="small" sx={{ p: 0.8 }} disabled={fileManagerLoading}
              onClick={() => loadFileManager(fileManagerPath)}>
              <Icon icon={RefreshIcon} sx={{ fontSize: 18, color: "#475569" }} />
            </IconButton>
          </span>
        </Tooltip>

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, height: 22, alignSelf: "center" }} />

        {/* File / Folder operations */}
        <Tooltip title="New Folder">
          <span>
            <IconButton size="small" sx={{ p: 0.8 }} disabled={fileOpBusy || !fileManagerPath} onClick={createFolderInCurrentPath}>
              <Icon icon={NewFolderIcon} sx={{ fontSize: 18, color: "#475569" }} />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="New File">
          <span>
            <IconButton size="small" sx={{ p: 0.8 }} disabled={fileOpBusy || !fileManagerPath} onClick={createFileInCurrentPath}>
              <Icon icon={NewFileIcon} sx={{ fontSize: 18, color: "#475569" }} />
            </IconButton>
          </span>
        </Tooltip>

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, height: 22, alignSelf: "center" }} />

        {/* Upload */}
        <Tooltip title="Upload Files (or drag & drop)">
          <span>
            <Button component="label" size="small" variant="outlined" disabled={fileOpBusy || !fileManagerPath}
              startIcon={<Icon icon={UploadIcon} sx={{ fontSize: 15 }} />}
              sx={{ textTransform: "none", fontSize: 12, px: 1.25, py: 0.4, borderColor: "#dbe5f6" }}>
              Upload
              <input hidden multiple type="file" onChange={uploadIntoCurrentPath} />
            </Button>
          </span>
        </Tooltip>
        <Tooltip title="Upload Folder">
          <span>
            <Button component="label" size="small" variant="outlined" disabled={fileOpBusy || !fileManagerPath}
              sx={{ textTransform: "none", fontSize: 12, px: 1.25, py: 0.4, borderColor: "#dbe5f6" }}>
              Folder
              <input hidden multiple type="file" webkitdirectory="" directory="" onChange={uploadIntoCurrentPath} />
            </Button>
          </span>
        </Tooltip>

        {/* Selection actions */}
        {cloudSelected && (() => {
          const selEntry = entries.find((e) => e.path === cloudSelected);
          return selEntry ? (
            <>
              <Divider orientation="vertical" flexItem sx={{ mx: 0.5, height: 22, alignSelf: "center" }} />
              <Tooltip title="Rename">
                <span>
                  <IconButton size="small" sx={{ p: 0.8 }} disabled={fileOpBusy} onClick={() => renameFileManagerPath(cloudSelected)}>
                    <Icon icon={RenameIcon} sx={{ fontSize: 18, color: "#475569" }} />
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title="Delete">
                <span>
                  <IconButton size="small" sx={{ p: 0.8 }} disabled={fileOpBusy}
                    onClick={() => deleteFileManagerPath(selEntry.path, selEntry.is_dir)}>
                    <Icon icon={DeleteIcon} sx={{ fontSize: 18, color: "#ef4444" }} />
                  </IconButton>
                </span>
              </Tooltip>
            </>
          ) : null;
        })()}

        {/* Busy spinners */}
        {(fileManagerLoading || fileOpBusy || moveBusy) && (
          <CircularProgress size={15} sx={{ ml: 0.5, color: "#1d4ed8" }} />
        )}
      </Box>
    );

    // ─── BREADCRUMB ──────────────────────────────────────────────────────────
    const renderBreadcrumb = () => (
      <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 0.25, px: 1.5, py: 0.6, bgcolor: "#f8faff", borderBottom: "1px solid #e8eef6" }}>
        {breadcrumbs.map((crumb, i) => (
          <React.Fragment key={crumb.path + "-" + i}>
            {i > 0 && <Box component={ChevronRightIcon || "span"} sx={{ fontSize: 14, color: "#cbd5e1" }} />}
            <Typography variant="caption"
              sx={{
                fontSize: 12, px: 0.75, py: 0.2, borderRadius: 1, cursor: "pointer",
                fontWeight: i === breadcrumbs.length - 1 ? 700 : 400,
                color: i === breadcrumbs.length - 1 ? "#1d4ed8" : "#64748b",
                display: "inline-flex", alignItems: "center", gap: 0.4,
                "&:hover": { bgcolor: "rgba(29,78,216,.07)", color: "#1d4ed8" },
              }}
              onClick={() => loadFileManager(crumb.path)}>
              {i === 0 && StorageIcon && <Box component={StorageIcon} sx={{ fontSize: 13 }} />}
              {crumb.label}
            </Typography>
          </React.Fragment>
        ))}
      </Box>
    );

    // ─── PATH BAR (tree mode) ────────────────────────────────────────────────
    const renderPathBar = () => (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.75, bgcolor: "#fff", borderBottom: "1px solid #e8eef6" }}>
        <TextField size="small" fullWidth
          value={pathInput}
          onChange={(e) => setPathInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { if (setFileManagerPath) setFileManagerPath(pathInput); loadFileManager(pathInput); } }}
          placeholder={os === "windows" ? "C:\\" : "/"}
          sx={{ "& .MuiOutlinedInput-input": { fontSize: 12, py: 0.6, fontFamily: "Consolas, monospace" }, "& .MuiOutlinedInput-root": { borderRadius: 1.5 } }}
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <Tooltip title="Navigate">
                  <IconButton size="small" onClick={() => { if (setFileManagerPath) setFileManagerPath(pathInput); loadFileManager(pathInput); }}>
                    <Icon icon={RefreshIcon} sx={{ fontSize: 15 }} />
                  </IconButton>
                </Tooltip>
              </InputAdornment>
            ),
          }}
        />
      </Box>
    );

    // ─── CLOUD VIEW ──────────────────────────────────────────────────────────
    const renderCloudView = () => (
      <Box
        sx={{
          flexGrow: 1, overflow: "auto", p: 2, minHeight: 400, position: "relative",
          bgcolor: panelDragActive ? "rgba(29,78,216,.03)" : "#fff",
          outline: panelDragActive ? "3px dashed #1d4ed8" : "none",
          outlineOffset: -4, transition: "background-color .15s, outline .15s",
        }}
        onDragEnter={handlePanelDragEnter} onDragOver={handlePanelDragOver}
        onDragLeave={handlePanelDragLeave} onDrop={handlePanelDrop}
        onClick={() => setCloudSelected(null)}
      >
        {/* Drop-to-upload overlay */}
        {panelDragActive && fileManagerPath && (
          <Box sx={{
            position: "absolute", inset: 0, display: "flex", alignItems: "center",
            justifyContent: "center", zIndex: 10, pointerEvents: "none",
          }}>
            <Paper sx={{ px: 5, py: 3, border: "2px dashed #1d4ed8", bgcolor: "rgba(255,255,255,.95)", borderRadius: 3, textAlign: "center" }}>
              <Icon icon={UploadIcon} sx={{ fontSize: 40, color: "#1d4ed8", mb: 1 }} />
              <Typography fontWeight={700} color="#1d4ed8" variant="h6">Drop files to upload</Typography>
              <Typography variant="caption" color="text.secondary">Files will be added to the current folder</Typography>
            </Paper>
          </Box>
        )}

        {fileManagerLoading && <LinearProgress sx={{ mb: 1.5, borderRadius: 1 }} />}
        {fileManagerError && <Alert severity="error" sx={{ mb: 1.5 }}>{fileManagerError}</Alert>}
        {moveError && <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setMoveError("")}>{moveError}</Alert>}

        {entries.length === 0 && !fileManagerLoading && (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", py: 8, color: "#94a3b8" }}>
            <Box component={FolderOpenIcon || "span"} sx={{ fontSize: 72, opacity: 0.25, mb: 1.5 }} />
            <Typography variant="body2" color="text.secondary">
              {fileManagerPath ? "This folder is empty." : "Select a drive or folder to start browsing."}
            </Typography>
            {fileManagerPath && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                Drag & drop files here to upload them.
              </Typography>
            )}
          </Box>
        )}

        {/* Folders section */}
        {folderEntries.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption"
              sx={{ color: "#94a3b8", fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: .08, px: 0.5 }}>
              Folders ({folderEntries.length})
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.75, pb: 3.5 }}>
              {folderEntries.map((entry) => (
                <CloudEntry key={entry.path} entry={entry}
                  isSelected={cloudSelected === entry.path} isDragOver={dragOver === entry.path}
                  onClick={(e) => { e.stopPropagation && e.stopPropagation(); setCloudSelected(entry.path); }}
                  onDoubleClick={(entry) => { loadFileManager(entry.path); setCloudSelected(null); }}
                  onDragStart={handleDragStart} onDragEnter={handleDragEnter}
                  onDragLeave={handleDragLeave} onDrop={handleDrop}
                  onRename={renameFileManagerPath} onDelete={deleteFileManagerPath}
                  onDownload={(p) => window.open(`/api/files/download?path=${encodeURIComponent(p)}`, "_blank", "noopener,noreferrer")}
                  onEdit={openFileInEditor} fileOpBusy={fileOpBusy} />
              ))}
            </Box>
          </Box>
        )}

        {/* Files section */}
        {fileEntries.length > 0 && (
          <Box>
            <Typography variant="caption"
              sx={{ color: "#94a3b8", fontWeight: 700, fontSize: 10.5, textTransform: "uppercase", letterSpacing: .08, px: 0.5 }}>
              Files ({fileEntries.length})
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.75, pb: 2 }}>
              {fileEntries.map((entry) => (
                <CloudEntry key={entry.path} entry={entry}
                  isSelected={cloudSelected === entry.path} isDragOver={false}
                  onClick={(e) => { e.stopPropagation && e.stopPropagation(); setCloudSelected(entry.path); }}
                  onDoubleClick={(entry) => { openFileInEditor(entry.path); }}
                  onDragStart={handleDragStart} onDragEnter={handleDragEnter}
                  onDragLeave={handleDragLeave} onDrop={handleDrop}
                  onRename={renameFileManagerPath} onDelete={deleteFileManagerPath}
                  onDownload={(p) => window.open(`/api/files/download?path=${encodeURIComponent(p)}`, "_blank", "noopener,noreferrer")}
                  onEdit={openFileInEditor} fileOpBusy={fileOpBusy} />
              ))}
            </Box>
          </Box>
        )}
      </Box>
    );

    // ─── TREE VIEW ────────────────────────────────────────────────────────────
    const renderTreeView = () => (
      <Box sx={{ display: "flex", flexGrow: 1, overflow: "hidden", minHeight: 400 }}>
        {/* Left: tree panel */}
        <Box sx={{ width: 256, minWidth: 160, flexShrink: 0, borderRight: "1px solid #e8eef6", overflow: "auto", bgcolor: "#f8faff", py: 0.75 }}>
          {!treeRootsLoaded && (
            <Box sx={{ display: "flex", justifyContent: "center", pt: 3 }}>
              <CircularProgress size={20} />
            </Box>
          )}
          <FileTree
            items={treeRoots} depth={0}
            treeExpanded={treeExpanded} treeChildren={treeChildren}
            treeLoading={treeLoading} selected={treeSelected} dragOverPath={dragOver}
            onToggle={handleTreeToggle} onSelect={handleTreeSelect}
            onDragStart={handleDragStart} onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave} onDrop={handleDrop}
          />
        </Box>

        {/* Right: directory contents */}
        <Box sx={{ flexGrow: 1, overflow: "auto", bgcolor: "#fff", position: "relative" }}
          onDragEnter={handlePanelDragEnter} onDragOver={handlePanelDragOver}
          onDragLeave={handlePanelDragLeave} onDrop={handlePanelDrop}>

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
              <Typography variant="body2" color="text.secondary">
                {fileManagerPath ? "Empty folder." : "Select a folder in the tree."}
              </Typography>
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
              onClick={() => { if (!entry.is_dir) openFileInEditor(entry.path); else loadFileManager(entry.path); }}
              onDoubleClick={() => { if (entry.is_dir) { loadFileManager(entry.path); handleTreeToggle(entry.path); } }}
            >
              {entry.is_dir
                ? <Box component={FolderIcon || "span"} sx={{ fontSize: 18, color: "#f59e0b", flexShrink: 0 }} />
                : <Box component={getFileTypeIcon(entry.name) || FileIcon || "span"} sx={{ fontSize: 16, color: fileExtColor(entry.name), flexShrink: 0 }} />
              }
              <Typography variant="body2" noWrap sx={{ flexGrow: 1, fontSize: 13, minWidth: 0 }}>{entry.name}</Typography>
              <Typography variant="caption" sx={{ color: "#94a3b8", fontSize: 11, flexShrink: 0, minWidth: 56, textAlign: "right" }}>
                {entry.is_dir ? "" : fmtBytes(entry.size)}
              </Typography>
              <Typography variant="caption" sx={{ color: "#cbd5e1", fontSize: 11, flexShrink: 0, minWidth: 80, textAlign: "right", display: { xs: "none", md: "block" } }}>
                {fmtDate(entry.modified_ts)}
              </Typography>
              <Box sx={{ display: "flex", gap: 0.25, flexShrink: 0, ml: 0.5 }}>
                {!entry.is_dir && (
                  <Tooltip title="Download">
                    <IconButton size="small" sx={{ p: 0.3 }} onClick={(e) => { e.stopPropagation(); window.open(`/api/files/download?path=${encodeURIComponent(entry.path)}`, "_blank", "noopener,noreferrer"); }}>
                      <Icon icon={DownloadIcon} sx={{ fontSize: 14, color: "#64748b" }} />
                    </IconButton>
                  </Tooltip>
                )}
                <Tooltip title="Rename">
                  <IconButton size="small" sx={{ p: 0.3 }} disabled={fileOpBusy} onClick={(e) => { e.stopPropagation(); renameFileManagerPath(entry.path); }}>
                    <Icon icon={RenameIcon} sx={{ fontSize: 14, color: "#64748b" }} />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Delete">
                  <IconButton size="small" sx={{ p: 0.3 }} disabled={fileOpBusy} onClick={(e) => { e.stopPropagation(); deleteFileManagerPath(entry.path, entry.is_dir); }}>
                    <Icon icon={DeleteIcon} sx={{ fontSize: 14, color: "#ef4444" }} />
                  </IconButton>
                </Tooltip>
              </Box>
            </Box>
          ))}
        </Box>
      </Box>
    );

    // ─── EDITOR PANEL ────────────────────────────────────────────────────────
    const renderEditor = () => (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 500 }}>
        {/* Editor header */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, py: 0.9, borderBottom: "1px solid #e8eef6", bgcolor: "#f8faff" }}>
          <Box component={EditCodeIcon || "span"} sx={{ fontSize: 16, color: "#475569" }} />
          <Typography variant="body2" fontWeight={700} noWrap sx={{ flexGrow: 1, fontSize: 13, minWidth: 0, color: "#0f172a" }}>
            {fileEditorPath ? fileEditorPath.split(/[\\/]/).pop() : "Editor"}
          </Typography>
          {fileEditorDirty && (
            <Chip size="small" label="unsaved" sx={{ height: 18, fontSize: 10.5, bgcolor: "#fef9c3", color: "#854d0e", border: "1px solid #fde047" }} />
          )}
          <Button size="small" variant="contained" disabled={fileOpBusy || !fileEditorPath || !fileEditorDirty}
            onClick={saveFileEditor}
            sx={{ textTransform: "none", fontSize: 12, px: 1.5, py: 0.35, minWidth: 0, bgcolor: "#1d4ed8", "&:hover": { bgcolor: "#1e40af" } }}>
            Save
          </Button>
        </Box>

        {/* Editor path/meta strip */}
        {fileEditorPath && (
          <Box sx={{ px: 1.5, py: 0.4, bgcolor: "#fafbff", borderBottom: "1px solid #f1f5f9" }}>
            <Typography variant="caption" sx={{ color: "#64748b", fontSize: 11, fontFamily: "Consolas, monospace" }} noWrap>
              {fileEditorPath}
              {fileEditorMeta?.encoding ? ` · ${fileEditorMeta.encoding}` : ""}
              {fileEditorMeta?.size ? ` · ${fmtBytes(fileEditorMeta.size)}` : ""}
            </Typography>
          </Box>
        )}

        {/* Editor body */}
        {!fileEditorPath ? (
          <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", p: 3, color: "#94a3b8" }}>
            <Box component={FileIcon || "span"} sx={{ fontSize: 52, opacity: 0.2, mb: 1.5 }} />
            <Typography variant="body2" color="text.secondary" align="center">
              Open a text file to edit it here.
            </Typography>
            <Typography variant="caption" color="text.secondary" align="center" sx={{ mt: 0.5, display: "block" }}>
              Double-click a file in Cloud view, or click in Tree view.
            </Typography>
          </Box>
        ) : (
          <Box sx={{ flexGrow: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <TextField
              multiline fullWidth
              minRows={22} maxRows={32}
              value={fileEditorContent}
              onChange={(e) => { setFileEditorContent(e.target.value); setFileEditorDirty(true); }}
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
        )}
      </Box>
    );

    // ─── ROOT RENDER ─────────────────────────────────────────────────────────
    return (
      <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start", flexWrap: { xs: "wrap", lg: "nowrap" } }}>
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

        {/* RIGHT: Editor */}
        <Box sx={{
          width: { xs: "100%", lg: 400 }, flexShrink: 0,
          border: "1px solid #dbe5f6", borderRadius: 2.5, overflow: "hidden", bgcolor: "#fff",
          boxShadow: "0 4px 18px rgba(15,23,42,.07)",
        }}>
          {renderEditor()}
        </Box>
      </Box>
    );
  }

  window.ServerInstallerUI = window.ServerInstallerUI || {};
  window.ServerInstallerUI.FileManagerPage = FileManagerPage;
})();
