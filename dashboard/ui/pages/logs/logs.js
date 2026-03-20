(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  function LogsPageInner(p) {
    const {
      Box, Button, Card, CardContent, Typography, Stack, Paper, Chip, Tooltip,
      termText, copyText,
    } = p;

    const [autoScroll, setAutoScroll] = React.useState(true);
    const [cleared, setCleared] = React.useState(false);
    const [clearedAt, setClearedAt] = React.useState("");
    const scrollRef = React.useRef(null);

    const displayText = cleared ? "" : (termText || "");

    React.useEffect(() => {
      if (cleared && termText !== clearedAt) {
        setCleared(false);
      }
    }, [termText, cleared, clearedAt]);

    React.useEffect(() => {
      if (autoScroll && scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, [displayText, autoScroll]);

    function handleCopy() {
      if (copyText) {
        copyText(displayText);
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(displayText).catch(() => {});
      }
    }

    function handleClear() {
      setCleared(true);
      setClearedAt(termText || "");
    }

    const isEmpty = !displayText || displayText.trim() === "" || displayText.trim() === "$ ";

    return React.createElement(Box, { sx: { p: 0 } },
      React.createElement(Card, { sx: { borderRadius: 3, border: "1px solid #dbe5f6", overflow: "visible" } },
        React.createElement(CardContent, { sx: { p: 3 } },

          /* ── Controls bar ── */
          React.createElement(Stack, {
            direction: "row",
            alignItems: "center",
            spacing: 2,
            sx: { mb: 2, flexWrap: "wrap" },
          },
            React.createElement(Typography, {
              variant: "h5",
              fontWeight: 800,
              sx: { flexGrow: 1 },
            }, "System Logs"),

            React.createElement(Tooltip, { title: autoScroll ? "Auto-scroll is ON" : "Auto-scroll is OFF" },
              React.createElement("label", {
                style: {
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  cursor: "pointer",
                  fontSize: "0.875rem",
                  color: "#8b949e",
                  userSelect: "none",
                },
              },
                React.createElement("input", {
                  type: "checkbox",
                  checked: autoScroll,
                  onChange: function (e) { setAutoScroll(e.target.checked); },
                  style: { accentColor: "#58a6ff", width: 16, height: 16, cursor: "pointer" },
                }),
                "Auto-scroll"
              )
            ),

            React.createElement(Button, {
              size: "small",
              variant: "outlined",
              onClick: handleCopy,
              disabled: isEmpty,
              sx: {
                textTransform: "none",
                borderColor: "#30363d",
                color: "#c9d1d9",
                "&:hover": { borderColor: "#58a6ff", color: "#58a6ff" },
              },
            }, "Copy"),

            React.createElement(Button, {
              size: "small",
              variant: "outlined",
              onClick: handleClear,
              disabled: isEmpty,
              sx: {
                textTransform: "none",
                borderColor: "#30363d",
                color: "#c9d1d9",
                "&:hover": { borderColor: "#f85149", color: "#f85149" },
              },
            }, "Clear")
          ),

          /* ── Log display area ── */
          React.createElement(Paper, {
            ref: scrollRef,
            elevation: 0,
            sx: {
              bgcolor: "#0d1117",
              borderRadius: 2,
              border: "1px solid #30363d",
              p: 2,
              minHeight: "calc(100vh - 300px)",
              maxHeight: "calc(100vh - 300px)",
              overflowY: "auto",
              overflowX: "auto",
              fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', 'Monaco', monospace",
              fontSize: "0.85rem",
              lineHeight: 1.6,
              color: "#c9d1d9",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              "&::-webkit-scrollbar": { width: 8 },
              "&::-webkit-scrollbar-track": { bgcolor: "#0d1117" },
              "&::-webkit-scrollbar-thumb": { bgcolor: "#30363d", borderRadius: 4 },
            },
          },
            isEmpty
              ? React.createElement(Box, {
                  sx: {
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    minHeight: "calc(100vh - 360px)",
                    textAlign: "center",
                    color: "#484f58",
                  },
                },
                  React.createElement(Typography, {
                    variant: "h6",
                    sx: { color: "#8b949e", mb: 1, fontWeight: 600 },
                  }, "No logs captured yet"),
                  React.createElement(Typography, {
                    variant: "body2",
                    sx: { color: "#484f58" },
                  }, "Logs will appear here when you run services or commands.")
                )
              : displayText
          )
        )
      )
    );
  }

  ns.pages.logs = function renderLogsPage(p) {
    return React.createElement(LogsPageInner, p);
  };
})();
