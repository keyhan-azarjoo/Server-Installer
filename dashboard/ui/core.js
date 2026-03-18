(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  const cfg = window.__APP_CONFIG__ || { os: "windows", os_label: "Windows", message: "" };
  const MuiIcons = window.MaterialUIIcons || {};

  ns.core = {
    cfg,
    MuiIcons,
    DownloadCompassIcon: MuiIcons.DownloadRounded || MuiIcons.Download || null,
    CopyCompassIcon: MuiIcons.ContentCopyRounded || MuiIcons.ContentCopy || null,
    TryOpenCompassIcon: MuiIcons.OpenInNewRounded || MuiIcons.LaunchRounded || MuiIcons.OpenInNew || MuiIcons.Launch || null,
    OpenCompassStyleIcon: MuiIcons.LanguageRounded || MuiIcons.PublicRounded || MuiIcons.Language || MuiIcons.Public || null,
    RefreshSmallIcon: MuiIcons.RefreshRounded || MuiIcons.SyncRounded || MuiIcons.Refresh || null,
    StartAllIcon: MuiIcons.PlayArrowRounded || MuiIcons.PlayArrow || null,
    StopAllIcon: MuiIcons.StopRounded || MuiIcons.Stop || null,
    FolderIcon: MuiIcons.FolderOpenRounded || MuiIcons.FolderOpen || MuiIcons.FolderRounded || MuiIcons.Folder || null,
    DRAWER_W: 250,
    DRAWER_MIN: 82,
  };
})();
