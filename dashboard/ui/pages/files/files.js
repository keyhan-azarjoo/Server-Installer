(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.files = function renderFilesPage(p) {
    const {
      Typography,
      cfg,
      fileManagerPath, setFileManagerPath,
      fileManagerData, fileManagerLoading, fileManagerError,
      fileManagerTerminalRequest, setFileManagerTerminalRequest,
      fileEditorPath, fileEditorContent, fileEditorMeta, fileEditorDirty,
      fileOpBusy,
      loadFileManager, openFileInEditor, saveFileEditor,
      setFileEditorContent, setFileEditorDirty,
      createFolderInCurrentPath, createFileInCurrentPath,
      renameFileManagerPath, deleteFileManagerPath, uploadIntoCurrentPath,
    } = p;

    const { FileManagerPage } = window.ServerInstallerUI || {};
    if (!FileManagerPage) return <Typography color="error">FileManagerPage component not loaded.</Typography>;
    return (
      <FileManagerPage
        cfg={cfg}
        fileManagerPath={fileManagerPath}
        setFileManagerPath={setFileManagerPath}
        fileManagerData={fileManagerData}
        fileManagerLoading={fileManagerLoading}
        fileManagerError={fileManagerError}
        fileManagerTerminalRequest={fileManagerTerminalRequest}
        setFileManagerTerminalRequest={setFileManagerTerminalRequest}
        fileEditorPath={fileEditorPath}
        fileEditorContent={fileEditorContent}
        fileEditorMeta={fileEditorMeta}
        fileEditorDirty={fileEditorDirty}
        fileOpBusy={fileOpBusy}
        loadFileManager={loadFileManager}
        openFileInEditor={openFileInEditor}
        saveFileEditor={saveFileEditor}
        setFileEditorContent={setFileEditorContent}
        setFileEditorDirty={setFileEditorDirty}
        createFolderInCurrentPath={createFolderInCurrentPath}
        createFileInCurrentPath={createFileInCurrentPath}
        renameFileManagerPath={renameFileManagerPath}
        deleteFileManagerPath={deleteFileManagerPath}
        uploadIntoCurrentPath={uploadIntoCurrentPath}
      />
    );
  };
})();
