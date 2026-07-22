(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  const React = SDK.React;
  const { useEffect, useState, useCallback } = React;

  function fmt(n, digits) {
    if (n == null || Number.isNaN(n)) return "—";
    const x = Number(n);
    if (Math.abs(x) >= 1000) return x.toLocaleString(undefined, { maximumFractionDigits: digits || 0 });
    return x.toLocaleString(undefined, { maximumFractionDigits: digits == null ? 1 : digits });
  }

  function fmtPct(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return fmt(n, 1) + "%";
  }

  function api(path) {
    return SDK.fetchJSON("/api/plugins/ce_observatory" + path);
  }

  function Card({ label, value, hint }) {
    return React.createElement(
      "div",
      { className: "ceo-card" },
      React.createElement("div", { className: "label" }, label),
      React.createElement("div", { className: "value" }, value),
      hint ? React.createElement("div", { className: "hint" }, hint) : null
    );
  }

  function StreamPills({ streams }) {
    if (!streams) return null;
    return React.createElement(
      "div",
      { className: "ceo-pill-row" },
      Object.entries(streams).map(function ([name, meta]) {
        const label = name + (meta && meta.exists ? " ✓" : " —");
        return React.createElement(
          "span",
          { key: name, className: "ceo-pill", title: (meta && meta.mtime) || "missing" },
          label
        );
      })
    );
  }

  function TopSessions({ rows, tokenKey }) {
    if (!rows || !rows.length) return React.createElement("p", { className: "ceo-muted" }, "No session rows yet.");
    return React.createElement(
      "table",
      { className: "ceo-table" },
      React.createElement(
        "thead",
        null,
        React.createElement(
          "tr",
          null,
          React.createElement("th", null, "Session"),
          React.createElement("th", null, "Pins / L4"),
          React.createElement("th", null, "Tokens"),
          React.createElement("th", null, "Save%")
        )
      ),
      React.createElement(
        "tbody",
        null,
        rows.slice(0, 12).map(function (r) {
          return React.createElement(
            "tr",
            { key: r.session_id },
            React.createElement("td", null, (r.session_id || "").slice(0, 22)),
            React.createElement("td", null, fmt(r.pin_count != null ? r.pin_count : r.l4)),
            React.createElement("td", null, fmt(r[tokenKey] != null ? r[tokenKey] : r.pinned_tokens_est || r.legacy)),
            React.createElement("td", null, r.save_pct != null ? fmtPct(r.save_pct) : "—")
          );
        })
      )
    );
  }

  function ObservatoryPage() {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);
    const [loading, setLoading] = useState(true);

    const refresh = useCallback(function () {
      setLoading(true);
      setErr(null);
      api("/summary")
        .then(function (d) {
          setData(d);
          setLoading(false);
        })
        .catch(function (e) {
          setErr(String(e && e.message ? e.message : e));
          setLoading(false);
        });
    }, []);

    useEffect(function () {
      refresh();
      const id = setInterval(refresh, 30000);
      return function () {
        clearInterval(id);
      };
    }, [refresh]);

    const shadow = (data && data.shadow) || {};
    const pins = (data && data.pins) || {};
    const soak = (data && data.soak) || {};
    const assemble = (data && data.assemble) || {};
    const layers = shadow.layers_mean || {};
    const compression = (data && data.compression) || {};

    return React.createElement(
      "div",
      { className: "ceo-root" },
      React.createElement(
        "div",
        { className: "ceo-header" },
        React.createElement(
          "div",
          null,
          React.createElement("h1", null, "Context Engineering Observatory"),
          React.createElement(
            "p",
            { className: "ceo-sub" },
            "Read-only view of existing HERMES_HOME/logs telemetry. Observation mode — no V2 runtime or config changes. PRs #3/#4 remain undeployed."
          ),
          React.createElement(StreamPills, { streams: data && data.streams })
        ),
        React.createElement(
          "div",
          { className: "ceo-actions" },
          React.createElement("span", { className: "ceo-badge" }, "Observation"),
          React.createElement(
            "button",
            { className: "ceo-btn", onClick: refresh, type: "button" },
            loading ? "Refreshing…" : "Refresh"
          )
        )
      ),
      err ? React.createElement("p", { className: "ceo-error" }, err) : null,
      !data && !err
        ? React.createElement("p", { className: "ceo-muted" }, "Loading telemetry…")
        : null,
      data
        ? React.createElement(
            React.Fragment,
            null,
            React.createElement(
              "p",
              { className: "ceo-muted" },
              "Generated ",
              data.generated_at,
              data.telemetry_freshest_mtime
                ? " · freshest log mtime " + data.telemetry_freshest_mtime
                : ""
            ),
            React.createElement(
              "div",
              { className: "ceo-grid" },
              React.createElement(Card, {
                label: "Legacy attended (mean)",
                value: fmt(shadow.legacy_mean),
                hint: "p50 " + fmt(shadow.legacy_p50)
              }),
              React.createElement(Card, {
                label: "Projected layering save",
                value: fmtPct(shadow.savings_pct_of_legacy_mean),
                hint: fmt(shadow.savings_mean) + " tok mean"
              }),
              React.createElement(Card, {
                label: "L4 pinned (mean)",
                value: fmt(layers.l4_pinned_tokens),
                hint: "L3 recent " + fmt(layers.l3_recent_tokens)
              }),
              React.createElement(Card, {
                label: "Open-epoch rate",
                value: fmtPct(pins.open_epoch_rate_pct),
                hint: "pin count mean " + fmt(pins.pin_count_mean)
              }),
              React.createElement(Card, {
                label: "Retrieve mean (soak)",
                value: fmt(soak.retrieve_mean, 2),
                hint: "nonzero " + fmt(soak.retrieve_nonzero, 0)
              }),
              React.createElement(Card, {
                label: "Compress events",
                value: fmt(compression.dones, 0) + " done",
                hint: fmt(compression.skips, 0) + " concurrent skips (agent.log window)"
              })
            ),
            React.createElement(
              "div",
              { className: "ceo-section" },
              React.createElement("h2", null, "Layer means (shadow)"),
              React.createElement(
                "div",
                { className: "ceo-grid" },
                React.createElement(Card, { label: "L1 system", value: fmt(layers.l1_system_tokens) }),
                React.createElement(Card, { label: "L1 tools", value: fmt(layers.l1_tools_tokens) }),
                React.createElement(Card, { label: "L2 WM", value: fmt(layers.l2_working_memory_tokens) }),
                React.createElement(Card, { label: "L3 recent", value: fmt(layers.l3_recent_tokens) }),
                React.createElement(Card, { label: "L4 pins", value: fmt(layers.l4_pinned_tokens) }),
                React.createElement(Card, { label: "L5 summary", value: fmt(layers.l5_summary_tokens) })
              )
            ),
            React.createElement(
              "div",
              { className: "ceo-section" },
              React.createElement("h2", null, "Soak / assemble"),
              React.createElement(
                "div",
                { className: "ceo-grid" },
                React.createElement(Card, {
                  label: "Soak arms",
                  value: soak.arms ? JSON.stringify(soak.arms) : "—",
                  hint: "steps " + (soak.steps ? JSON.stringify(soak.steps) : "—")
                }),
                React.createElement(Card, {
                  label: "Assemble inspect save",
                  value: fmt(assemble.inspect_savings_mean),
                  hint: "mutates_prompt " + fmtPct(assemble.mutates_prompt_rate_pct)
                }),
                React.createElement(Card, {
                  label: "Pin-caps stream",
                  value: (data.pin_caps && data.pin_caps.status) || "—",
                  hint: "requires PR #4 deploy"
                }),
                React.createElement(Card, {
                  label: "Short-bypass stream",
                  value: (data.short_bypass && data.short_bypass.status) || "—",
                  hint: "requires PR #4 deploy"
                })
              )
            ),
            React.createElement(
              "div",
              { className: "ceo-section" },
              React.createElement("h2", null, "Top pinned sessions"),
              React.createElement(TopSessions, {
                rows: pins.top_pinned_sessions,
                tokenKey: "pinned_tokens_est"
              })
            ),
            React.createElement(
              "div",
              { className: "ceo-section" },
              React.createElement("h2", null, "Top shadow sessions"),
              React.createElement(TopSessions, {
                rows: shadow.top_sessions,
                tokenKey: "legacy"
              })
            )
          )
        : null
    );
  }

  window.__HERMES_PLUGINS__.register("ce_observatory", ObservatoryPage);
})();
