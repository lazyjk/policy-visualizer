import { useState } from "react";
import {
  connectClearPass,
  fetchClearPassElements,
} from "../../api/builderApi";
import type {
  BuilderPlatform,
  BuilderElements,
  ClearPassCredentials,
  ISECredentials,
} from "../../api/builderApi";

interface Props {
  onConnect: (platform: BuilderPlatform, elements: BuilderElements, creds: ClearPassCredentials | ISECredentials) => void;
  onDisconnect: () => void;
}

const PANEL: React.CSSProperties = {
  borderBottom: "1px solid #e5e7eb",
  background: "#fff",
  display: "flex",
  flexDirection: "column",
  fontFamily: "Helvetica, Arial, sans-serif",
  fontSize: 13,
};

const LABEL: React.CSSProperties = {
  display: "block",
  marginBottom: 4,
  fontWeight: 600,
  color: "#374151",
  fontSize: 12,
};

const INPUT: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: "6px 8px",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  fontSize: 13,
  marginBottom: 10,
  fontFamily: "inherit",
};

const BTN_PRIMARY: React.CSSProperties = {
  width: "100%",
  padding: "8px 0",
  background: "#2563eb",
  color: "#fff",
  border: "none",
  borderRadius: 5,
  fontFamily: "inherit",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
  marginTop: 4,
};

const BTN_GHOST: React.CSSProperties = {
  width: "100%",
  padding: "7px 0",
  background: "none",
  color: "#6b7280",
  border: "1px solid #d1d5db",
  borderRadius: 5,
  fontFamily: "inherit",
  fontSize: 13,
  cursor: "pointer",
  marginTop: 8,
};

export default function ConnectionPanel({ onConnect, onDisconnect }: Props) {
  const [serverUrl, setServerUrl] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [verifySsl, setVerifySsl] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [connectedInfo, setConnectedInfo] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  async function handleConnect() {
    setError(null);
    setLoading(true);
    try {
      const creds: ClearPassCredentials = {
        serverUrl,
        clientId,
        clientSecret,
        verifySsl,
      };
      const [connectResult, elements] = await Promise.all([
        connectClearPass(creds),
        fetchClearPassElements(creds),
      ]);
      const label = connectResult.version
        ? `ClearPass ${connectResult.version}`
        : "ClearPass";
      setConnectedInfo(label);
      setConnected(true);
      onConnect("clearpass", elements, creds);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function handleDisconnect() {
    setConnected(false);
    setConnectedInfo(null);
    setError(null);
    onDisconnect();
  }

  return (
    <div style={PANEL}>
      {/* Header row with collapse toggle */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          width: "100%",
          padding: "12px 16px",
          background: "none",
          border: "none",
          cursor: "pointer",
          fontFamily: "inherit",
          textAlign: "left",
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 14, color: "#111827" }}>Connection</span>
        <span style={{
          fontSize: 11,
          color: "#9ca3af",
          transform: collapsed ? "rotate(-90deg)" : "rotate(0deg)",
          transition: "transform 0.15s ease",
          display: "inline-block",
          lineHeight: 1,
        }}>▼</span>
      </button>

      {!collapsed && <div style={{ padding: "0 16px 16px" }}>

      {/* Server URL */}
      <label style={LABEL}>Server URL</label>
      <input
        style={INPUT}
        placeholder="https://clearpass.example.com"
        value={serverUrl}
        disabled={connected}
        onChange={(e) => setServerUrl(e.target.value)}
      />

      {/* ClearPass credentials */}
      <label style={LABEL}>Client ID</label>
      <input
        style={INPUT}
        placeholder="API client ID"
        value={clientId}
        disabled={connected}
        onChange={(e) => setClientId(e.target.value)}
      />
      <label style={LABEL}>Client Secret</label>
      <input
        style={INPUT}
        type="password"
        placeholder="Client secret"
        value={clientSecret}
        disabled={connected}
        onChange={(e) => setClientSecret(e.target.value)}
      />

      {/* SSL toggle */}
      <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 14, color: "#6b7280", cursor: connected ? "default" : "pointer" }}>
        <input
          type="checkbox"
          checked={!verifySsl}
          disabled={connected}
          onChange={(e) => setVerifySsl(!e.target.checked)}
        />
        Ignore SSL certificate errors
      </label>

      {/* Error */}
      {error && (
        <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 4, padding: "8px 10px", color: "#991b1b", fontSize: 12, marginBottom: 10 }}>
          {error}
        </div>
      )}

      {/* Status */}
      {connected && connectedInfo && (
        <div style={{ background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 4, padding: "8px 10px", color: "#166534", fontSize: 12, marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 10 }}>●</span>
          Connected — {connectedInfo}
        </div>
      )}

      {/* Actions */}
      {!connected ? (
        <button
          style={{ ...BTN_PRIMARY, opacity: loading ? 0.7 : 1 }}
          disabled={loading || !serverUrl}
          onClick={handleConnect}
        >
          {loading ? "Connecting…" : "Connect"}
        </button>
      ) : (
        <button style={BTN_GHOST} onClick={handleDisconnect}>
          Disconnect
        </button>
      )}
      </div>}
    </div>
  );
}
