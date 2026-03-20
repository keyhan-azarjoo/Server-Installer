(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  const { Box, Button, Card, CardContent, Chip, Paper, Stack, Typography, Alert } = MaterialUI;
  const { isServiceRunningStatus, formatServiceState, IconOnlyAction } = ns.actions || {};

  // ── PageDescription ────────────────────────────────────────────────────
  // A Card that shows a page explanation section.
  function PageDescription({ title, children }) {
    return (
      <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
        <CardContent>
          <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>{title}</Typography>
          {children}
        </CardContent>
      </Card>
    );
  }

  // ── ServiceListCard ────────────────────────────────────────────────────
  // A Card wrapper with the standard header (title, refresh button,
  // optional extra action buttons) that shows children (service rows)
  // or empty text when the list is empty.
  function ServiceListCard({
    title,
    services,
    emptyText,
    loading,
    onRefresh,
    extraActions,
    serviceBusy,
    children,
  }) {
    const svcs = services || [];
    const empty = emptyText || "No services found.";

    return (
      <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
        <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
            <Typography variant="h6" fontWeight={800}>{title}</Typography>
            <Box sx={{ flexGrow: 1 }} />
            {extraActions}
            {onRefresh && (
              <Button
                variant="outlined"
                disabled={!!loading}
                onClick={onRefresh}
                sx={{ textTransform: "none" }}
              >
                Refresh
              </Button>
            )}
          </Stack>
          <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
            {svcs.length === 0 && (
              <Typography variant="body2" color="text.secondary">{empty}</Typography>
            )}
            {children}
          </Box>
        </CardContent>
      </Card>
    );
  }

  // ── ServiceRow ─────────────────────────────────────────────────────────
  // A Paper row with the standard layout: name + kind chip, status dot,
  // URLs, ports, spacer, folder icon, edit icon, start/stop, restart,
  // delete, and optional extra buttons.
  function ServiceRow({
    svc,
    serviceBusy,
    onServiceAction,
    renderServiceUrls,
    renderServicePorts,
    renderServiceStatus,
    renderFolderIcon,
    renderEditServiceIcon,
    showRestart = true,
    showDelete = true,
    extraButtons,
  }) {
    if (!svc) return null;
    const running = isServiceRunningStatus(svc.status, svc.sub_status);
    const kindLabel = svc.kind || "service";

    return (
      <Paper key={`svc-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
          {/* ── Name + Kind ── */}
          <Box sx={{ minWidth: 250 }}>
            <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
              <Typography variant="body2"><b>{svc.form_name || svc.name}</b></Typography>
              <Chip label={kindLabel} size="small" variant="outlined" sx={{ fontSize: 11, height: 20 }} />
            </Stack>
            {svc.image && (
              <Typography variant="caption" color="text.secondary">Image: {svc.image}</Typography>
            )}
            {typeof renderServiceUrls === "function" && renderServiceUrls(svc)}
            {typeof renderServicePorts === "function" && renderServicePorts(svc)}
          </Box>

          {/* ── Status dot ── */}
          {typeof renderServiceStatus === "function" && renderServiceStatus(svc)}

          <Box sx={{ flexGrow: 1 }} />

          {/* ── Folder icon ── */}
          {typeof renderFolderIcon === "function" && renderFolderIcon(svc)}

          {/* ── Edit icon ── */}
          {typeof renderEditServiceIcon === "function" && renderEditServiceIcon(svc)}

          {/* ── Extra buttons (e.g. "Update Files" for websites) ── */}
          {extraButtons}

          {/* ── Start / Stop ── */}
          <Button
            size="small"
            variant="outlined"
            color={running ? "error" : "success"}
            disabled={!!serviceBusy}
            onClick={() => onServiceAction(running ? "stop" : "start", svc)}
            sx={{ textTransform: "none" }}
          >
            {running ? "Stop" : "Start"}
          </Button>

          {/* ── Restart ── */}
          {showRestart && (
            <Button
              size="small"
              variant="outlined"
              disabled={!!serviceBusy}
              onClick={() => onServiceAction("restart", svc)}
              sx={{ textTransform: "none" }}
            >
              Restart
            </Button>
          )}

          {/* ── Delete ── */}
          {showDelete && (
            <Button
              size="small"
              variant="outlined"
              color="error"
              disabled={!!serviceBusy}
              onClick={() => onServiceAction("delete", svc)}
              sx={{ textTransform: "none" }}
            >
              Delete
            </Button>
          )}
        </Stack>
      </Paper>
    );
  }

  // ── Register on namespace ──────────────────────────────────────────────
  ns.shared = { ServiceListCard, ServiceRow, PageDescription };
})();
